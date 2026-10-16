using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Windowing;
using Windows.Graphics;
using Forms = System.Windows.Forms;

namespace BensonMail;

internal static class Program
{
    internal static string[] Args = Array.Empty<string>();
    internal static void Trace(string stage)
    {
        var index = Array.IndexOf(Args, "--self-test");
        if (index >= 0 && index + 1 < Args.Length)
            File.AppendAllText(Args[index + 1] + ".startup.txt", stage + Environment.NewLine);
    }
    [STAThread]
    static void Main(string[] args)
    {
        Args = args;
        Trace("Main");
        WinRT.ComWrappersSupport.InitializeComWrappers();
        using var mutex = new Mutex(false, @"Local\BensonMail-" + Environment.UserName, out var created);
        if (!created) { Forms.MessageBox.Show("邮件小秘书已经运行，请点击任务栏右下角的信封。"); return; }
        try
        {
            Application.Start(initialization =>
            {
                Trace("Application.Start");
                SynchronizationContext.SetSynchronizationContext(
                    new Microsoft.UI.Dispatching.DispatcherQueueSynchronizationContext(
                        Microsoft.UI.Dispatching.DispatcherQueue.GetForCurrentThread()));
                _ = new MailApp();
            });
        }
        catch (Exception e)
        {
            var path = Path.Combine(Path.GetTempPath(), "BensonMail-startup-error.txt");
            File.WriteAllText(path, e.ToString());
            Forms.MessageBox.Show("启动失败，错误详情已保存至：" + path);
        }
    }
}

public sealed partial class MailApp : Application
{
    MainWindow? window;
    public MailApp()
    {
        Program.Trace("App constructor");
        UnhandledException += (_, e) =>
        {
            Program.Trace("Unhandled: " + e.Exception);
            var index = Array.IndexOf(Program.Args, "--self-test");
            if (index >= 0)
            {
                File.WriteAllText(Program.Args[index + 1], JsonSerializer.Serialize(new { ok = false, error = e.Exception.ToString() }));
                e.Handled = true;
                Environment.Exit(1);
            }
        };
        InitializeComponent();
        Program.Trace("Control resources");
    }
    protected override void OnLaunched(LaunchActivatedEventArgs args)
    {
        Program.Trace("OnLaunched");
        window = new MainWindow();
        window.Activate();
        Program.Trace("Activated");
    }
}

sealed class Bridge : IDisposable
{
    readonly Process process;
    readonly Dictionary<long, TaskCompletionSource<JsonElement>> pending = new();
    readonly object gate = new();
    readonly SemaphoreSlim writes = new(1);
    long sequence;
    public event Action<JsonElement>? Event;
    public Bridge(string? fixture)
    {
        var start = new ProcessStartInfo(Path.Combine(AppContext.BaseDirectory, "MailWorker.exe"))
        {
            UseShellExecute = false, CreateNoWindow = true, RedirectStandardInput = true,
            RedirectStandardOutput = true, RedirectStandardError = true,
            StandardInputEncoding = new UTF8Encoding(false), StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8,
            WorkingDirectory = AppContext.BaseDirectory
        };
        start.ArgumentList.Add("--bridge");
        start.ArgumentList.Add("--launcher");
        start.ArgumentList.Add(Environment.ProcessPath!);
        if (fixture != null) { start.ArgumentList.Add("--fixture"); start.ArgumentList.Add(fixture); }
        process = Process.Start(start) ?? throw new InvalidOperationException("后台启动失败。");
        _ = Task.Run(Read);
        // Drain stderr without logging sensitive payloads.
        _ = process.StandardError.ReadToEndAsync();
    }
    async Task Read()
    {
        try
        {
            while (await process.StandardOutput.ReadLineAsync() is string line)
            {
                using var doc = JsonDocument.Parse(line);
                var root = doc.RootElement;
                if (root.TryGetProperty("event", out var ev)) { Event?.Invoke(ev.Clone()); continue; }
                if (!root.TryGetProperty("id", out var id) || !id.TryGetInt64(out var key)) continue;
                TaskCompletionSource<JsonElement>? source;
                lock (gate) { pending.Remove(key, out source); }
                if (root.GetProperty("ok").GetBoolean())
                    source?.TrySetResult(root.GetProperty("result").Clone());
                else source?.TrySetException(new InvalidOperationException(root.GetProperty("error").GetString()));
            }
            throw new IOException("邮件后台已退出，请重新打开程序。");
        }
        catch (Exception e)
        {
            lock (gate)
            {
                foreach (var source in pending.Values) source.TrySetException(e);
                pending.Clear();
            }
            using var error = JsonDocument.Parse(JsonSerializer.Serialize(new { status = "后台已停止", detail = e.Message }));
            Event?.Invoke(error.RootElement.Clone());
        }
    }
    public async Task<JsonElement> Call(string command, object? data = null)
    {
        var id = Interlocked.Increment(ref sequence);
        var source = new TaskCompletionSource<JsonElement>(TaskCreationOptions.RunContinuationsAsynchronously);
        lock (gate) pending.Add(id, source);
        await writes.WaitAsync();
        try
        {
            await process.StandardInput.WriteLineAsync(JsonSerializer.Serialize(new { id, command, data = data ?? new { } }));
            await process.StandardInput.FlushAsync();
        }
        catch { lock (gate) pending.Remove(id); throw; }
        finally { writes.Release(); }
        return await source.Task;
    }
    public void Dispose()
    {
        process.StandardInput.Close();
        process.Dispose();
    }
}

sealed record Report(string path, string title, string sender, string time, bool? attachments)
{
    public override string ToString() => title + "\n" + sender + "  ·  " + time + (attachments == true ? "  ·  有附件" : "");
}

sealed class MainWindow : Window
{
    readonly Grid layout = new() { Padding = new Thickness(22), ColumnSpacing = 22 };
    readonly TextBlock status = new() { Text = "已暂停", FontSize = 23, FontWeight = Microsoft.UI.Text.FontWeights.SemiBold };
    readonly TextBlock detail = new() { Text = "正在加载设置…", TextWrapping = TextWrapping.Wrap };
    readonly TextBox account = new() { Header = "163 邮箱地址", PlaceholderText = "name@163.com" };
    readonly PasswordBox mailSecret = new() { Header = "POP3/IMAP/SMTP 授权码", PlaceholderText = "留空保留已有授权码" };
    readonly TextBox folder = new() { Header = "报告保存文件夹" };
    readonly ToggleSwitch startup = new() { Header = "登录 Windows 后自动启动", OnContent = "开启", OffContent = "关闭" };
    readonly ComboBox provider = new() { Header = "分析方式", HorizontalAlignment = HorizontalAlignment.Stretch };
    readonly TextBox apiBase = new() { Header = "基础地址", PlaceholderText = "https://服务商地址/v1" };
    readonly TextBox model = new() { Header = "模型名", PlaceholderText = "填写服务商提供的模型名" };
    readonly PasswordBox apiKey = new() { Header = "API Key", PlaceholderText = "留空保留此地址已保存的 Key" };
    readonly TextBox interval = new() { Text = "60", Width = 85, Header = "检查间隔（秒）" };
    readonly TextBox search = new() { PlaceholderText = "搜索正文、发件人、附件名", HorizontalAlignment = HorizontalAlignment.Stretch };
    readonly TextBox sender = new() { Header = "发件人", PlaceholderText = "姓名或邮箱" };
    readonly CalendarDatePicker from = new() { Header = "起始日期", PlaceholderText = "不限", HorizontalAlignment = HorizontalAlignment.Stretch };
    readonly CalendarDatePicker to = new() { Header = "结束日期", PlaceholderText = "不限", HorizontalAlignment = HorizontalAlignment.Stretch };
    readonly ComboBox attachment = new() { Header = "附件", HorizontalAlignment = HorizontalAlignment.Stretch };
    readonly ListView reports = new() { SelectionMode = ListViewSelectionMode.Single };
    readonly TextBox preview = new() { IsReadOnly = true, AcceptsReturn = true, TextWrapping = TextWrapping.Wrap,
        PlaceholderText = "选择一封邮件，查看六项报告。", VerticalAlignment = VerticalAlignment.Stretch };
    readonly Button toggle = new() { Content = "开始监听" };
    readonly Button check = new() { Content = "立即检查" };
    readonly Forms.NotifyIcon tray;
    readonly Bridge bridge;
    readonly string? testResult;
    readonly string? fixture;
    readonly HashSet<string> notified = new();
    bool initialized, running, exiting, exitRequested;
    long reportGeneration, previewGeneration;

    public MainWindow()
    {
        Program.Trace("Window constructor");
        Title = "邮件小秘书";
        var args = Program.Args;
        var testIndex = Array.IndexOf(args, "--self-test");
        testResult = testIndex >= 0 && testIndex + 1 < args.Length ? args[testIndex + 1] : null;
        fixture = testResult == null ? null : Path.Combine(Path.GetTempPath(), "BensonMail-native-test-" + Guid.NewGuid());
        AppWindow.Resize(new SizeInt32(1180, 850));
        var area = DisplayArea.GetFromWindowId(AppWindow.Id, DisplayAreaFallback.Primary).WorkArea;
        AppWindow.Resize(new SizeInt32(Math.Min(1180, area.Width - 40), Math.Min(850, area.Height - 40)));
        AppWindow.Move(new PointInt32(area.X + 20, area.Y + 20));
        AppWindow.SetIcon(Path.Combine(AppContext.BaseDirectory, "assets", "mail.ico"));
        SystemBackdrop = new MicaBackdrop();
        Content = layout;
        layout.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(375) });
        layout.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        BuildLeft();
        Program.Trace("Left controls");
        BuildRight();
        Program.Trace("Right controls");
        tray = new Forms.NotifyIcon
        {
            Text = "邮件小秘书", Icon = new System.Drawing.Icon(Path.Combine(AppContext.BaseDirectory, "assets", "mail.ico")),
            Visible = true, ContextMenuStrip = new Forms.ContextMenuStrip()
        };
        tray.ContextMenuStrip.Items.Add("打开窗口", null, (_, _) => DispatcherQueue.TryEnqueue(Restore));
        tray.ContextMenuStrip.Items.Add("开始／暂停监听", null, (_, _) => DispatcherQueue.TryEnqueue(async () => await Guard(ToggleService)));
        tray.ContextMenuStrip.Items.Add("退出邮件小秘书", null, (_, _) => DispatcherQueue.TryEnqueue(async () => await Exit()));
        tray.DoubleClick += (_, _) => DispatcherQueue.TryEnqueue(Restore);
        tray.BalloonTipClicked += (_, _) => DispatcherQueue.TryEnqueue(Restore);
        AppWindow.Closing += (_, e) =>
        {
            if (!exiting) { e.Cancel = true; AppWindow.Hide(); }
        };
        bridge = new Bridge(fixture);
        Program.Trace("Worker started");
        bridge.Event += ev => DispatcherQueue.TryEnqueue(() => HandleEvent(ev));
        layout.Loaded += async (_, _) => await Initialize();
    }
    static TextBlock Note(string text) => new() { Text = text, TextWrapping = TextWrapping.Wrap, Opacity = .7, FontSize = 12 };
    static StackPanel Stack(params UIElement[] children)
    {
        var stack = new StackPanel { Spacing = 10 };
        foreach (var child in children) stack.Children.Add(child);
        return stack;
    }
    Button Action(string text, Func<Task> action)
    {
        var button = new Button { Content = text };
        button.Click += async (_, _) => { button.IsEnabled = false; try { await action(); } catch (Exception e) { detail.Text = e.Message; } finally { button.IsEnabled = true; } };
        return button;
    }
    static StackPanel Row(params UIElement[] children)
    {
        var row = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8 };
        foreach (var child in children) row.Children.Add(child);
        return row;
    }
    static ScrollViewer Scroll(UIElement child) => new() { Content = child,
        VerticalScrollBarVisibility = ScrollBarVisibility.Auto, HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled };
    void BuildLeft()
    {
        var pane = new Grid { RowSpacing = 14 };
        pane.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        pane.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) });
        pane.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        pane.Children.Add(Stack(new TextBlock { Text = "邮件小秘书", FontSize = 30,
            FontWeight = Microsoft.UI.Text.FontWeights.Bold }, Note("新来信自动整理，您决定如何回复。"), status, detail));
        provider.Items.Add("API · 无需安装 Codex"); provider.Items.Add("Codex · 已安装并登录");
        var tabs = new Pivot();
        tabs.Items.Add(new PivotItem { Header = "邮箱", Content = Scroll(Stack(account, mailSecret,
            Note("在163邮箱设置中启用 IMAP。填写授权码，不是邮箱登录密码。"), folder,
            Action("浏览……", PickFolder), startup, Action("保存邮箱设置", SaveMail),
            Action("测试邮箱连接", async () => { await SaveMail(); await Call("test_mail"); }),
            Note("授权码由当前 Windows 用户加密保存。不会自动回复，也不会标记邮件已读。"))) });
        tabs.Items.Add(new PivotItem { Header = "AI 服务", Content = Scroll(Stack(provider, apiBase, model, apiKey,
            Action("保存 AI 设置", SaveAI), Action("测试 AI 连接", async () => { await SaveAI(); await Call("test_ai"); }),
            Row(Action("查找 Codex", async () => await Call("codex")), Action("浏览……", PickCodex)),
            Note("六项总结提示词保持原样。来信和可读取的附件文字会交给所选 AI。无新邮件不调用 AI；测试连接会发送少量文字。"))) });
        Grid.SetRow(tabs, 1); pane.Children.Add(tabs);
        toggle.Click += async (_, _) => await Guard(ToggleService);
        check.Click += async (_, _) => await Guard(async () =>
        {
            check.IsEnabled = false;
            try { await Call("check"); } catch { check.IsEnabled = true; throw; }
        });
        var bottom = Stack(Row(interval, Action("应用间隔", async () =>
        {
            if (!int.TryParse(interval.Text, out var seconds)) throw new InvalidOperationException("请填写整数秒数。");
            await Call("interval", new { seconds });
        })), Row(toggle, check), Row(Action("打开报告文件夹", () =>
        {
            Directory.CreateDirectory(folder.Text); Open(folder.Text); return Task.CompletedTask;
        }), Action("退出", Exit)));
        Grid.SetRow(bottom, 2); pane.Children.Add(bottom);
        layout.Children.Add(pane);
    }
    void BuildRight()
    {
        var pane = new Grid { RowSpacing = 10 };
        Grid.SetColumn(pane, 1);
        pane.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        pane.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) });
        pane.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) });
        attachment.Items.Add("全部"); attachment.Items.Add("有附件"); attachment.Items.Add("无附件"); attachment.SelectedIndex = 0;
        var dates = new Grid { ColumnSpacing = 8 };
        for (int i = 0; i < 3; i++) dates.ColumnDefinitions.Add(new ColumnDefinition());
        dates.Children.Add(from); Grid.SetColumn(to, 1); dates.Children.Add(to); Grid.SetColumn(attachment, 2); dates.Children.Add(attachment);
        pane.Children.Add(Stack(new TextBlock { Text = "邮件报告", FontSize = 25, FontWeight = Microsoft.UI.Text.FontWeights.SemiBold },
            search, sender, dates, Row(Action("筛选 / 刷新", Refresh), Action("重置", async () =>
            { search.Text = sender.Text = ""; from.Date = to.Date = null; attachment.SelectedIndex = 0; await Refresh(); }),
            Action("打开 TXT", () => { if (reports.SelectedItem is Report report) Open(report.path); return Task.CompletedTask; }))));
        Grid.SetRow(reports, 1); pane.Children.Add(reports);
        Grid.SetRow(preview, 2); pane.Children.Add(preview);
        ScrollViewer.SetVerticalScrollBarVisibility(preview, ScrollBarVisibility.Auto);
        reports.SelectionChanged += async (_, _) => await Guard(async () =>
        {
            var generation = ++previewGeneration;
            preview.Text = "";
            if (reports.SelectedItem is Report report)
            {
                var result = await bridge.Call("read_report", new { path = report.path });
                if (generation == previewGeneration) preview.Text = result.GetString() ?? "";
            }
        });
        search.TextChanged += async (_, _) => { if (initialized) await Guard(Refresh); };
        layout.Children.Add(pane);
    }
    static void Open(string path) => Process.Start(new ProcessStartInfo(path) { UseShellExecute = true });
    async Task ToggleService()
    {
        if (!toggle.IsEnabled) return;
        var stopping = running;
        toggle.IsEnabled = false;
        try
        {
            await Call(stopping ? "pause" : "start");
            if (!stopping) { running = true; status.Text = "运行中"; toggle.Content = "暂停监听"; }
        }
        finally { toggle.IsEnabled = true; }
    }
    async Task Guard(Func<Task> work)
    {
        try { await work(); } catch (Exception e) { detail.Text = e.Message; }
    }
    async Task<JsonElement> Call(string name, object? data = null)
    {
        detail.Text = "正在处理…";
        var result = await bridge.Call(name, data);
        if (result.ValueKind == JsonValueKind.String) detail.Text = result.GetString() ?? "";
        return result;
    }
    async Task SaveMail()
    {
        await Call("save_mail", new { account = account.Text, secret = mailSecret.Password,
            output_dir = folder.Text, autostart = startup.IsOn });
        mailSecret.Password = "";
    }
    async Task SaveAI()
    {
        await Call("save_ai", new { ai_provider = provider.SelectedIndex == 1 ? "codex" : "api",
            api_base = apiBase.Text, api_model = model.Text, key = apiKey.Password });
        apiKey.Password = "";
    }
    async Task PickFolder()
    {
        var picker = new Windows.Storage.Pickers.FolderPicker();
        WinRT.Interop.InitializeWithWindow.Initialize(picker, WinRT.Interop.WindowNative.GetWindowHandle(this));
        picker.FileTypeFilter.Add("*");
        var picked = await picker.PickSingleFolderAsync();
        if (picked != null) folder.Text = picked.Path;
    }
    async Task PickCodex()
    {
        var picker = new Windows.Storage.Pickers.FileOpenPicker();
        WinRT.Interop.InitializeWithWindow.Initialize(picker, WinRT.Interop.WindowNative.GetWindowHandle(this));
        picker.FileTypeFilter.Add(".exe"); picker.FileTypeFilter.Add(".cmd");
        var picked = await picker.PickSingleFileAsync();
        if (picked != null) await Call("codex", new { path = picked.Path });
    }
    async Task Refresh()
    {
        var generation = ++reportGeneration;
        var selected = (reports.SelectedItem as Report)?.path;
        var result = await bridge.Call("reports", new { query = search.Text, sender = sender.Text,
            start = from.Date?.ToString("yyyy-MM-dd") ?? "", end = to.Date?.ToString("yyyy-MM-dd") ?? "",
            attachments = attachment.SelectedItem?.ToString() ?? "全部" });
        if (generation != reportGeneration) return;
        reports.Items.Clear();
        foreach (var row in result.EnumerateArray())
        {
            var report = new Report(row.GetProperty("path").GetString()!, row.GetProperty("title").GetString()!,
                row.GetProperty("sender").GetString()!, row.GetProperty("time").GetString()!,
                row.GetProperty("attachments").ValueKind == JsonValueKind.Null ? null : row.GetProperty("attachments").GetBoolean());
            reports.Items.Add(report);
            if (report.path == selected) reports.SelectedItem = report;
        }
    }
    void HandleEvent(JsonElement ev)
    {
        if (ev.TryGetProperty("status", out var state))
        {
            status.Text = state.GetString();
            if (status.Text == "已暂停") { running = false; toggle.Content = "开始监听"; check.IsEnabled = true; }
            else if (status.Text is "正在检查" or "正在分析") check.IsEnabled = false;
        }
        if (ev.TryGetProperty("detail", out var text)) detail.Text = text.GetString();
        if (ev.TryGetProperty("check_done", out _)) check.IsEnabled = true;
        if (ev.TryGetProperty("report", out _)) _ = Guard(Refresh);
        if (ev.TryGetProperty("notification", out var notice) && notified.Add(notice.GetProperty("id").GetString()!))
        {
            try
            {
                var title = notice.GetProperty("title").GetString() ?? "邮件小秘书";
                var message = notice.GetProperty("message").GetString() ?? "收到新邮件";
                tray.ShowBalloonTip(5000, title[..Math.Min(title.Length, 63)],
                    message[..Math.Min(message.Length, 240)], Forms.ToolTipIcon.Info);
            }
            catch { detail.Text = "邮件报告照常保存；系统通知暂不可用，请查看报告列表。"; }
        }
    }
    async Task Initialize()
    {
        Program.Trace("Layout loaded");
        if (initialized) return;
        try
        {
            var config = await bridge.Call("config");
            string Text(string key) => config.TryGetProperty(key, out var value) ? value.GetString() ?? "" : "";
            account.Text = Text("account"); folder.Text = Text("output_dir"); apiBase.Text = Text("api_base"); model.Text = Text("api_model");
            provider.SelectedIndex = Text("ai_provider") == "codex" ? 1 : 0;
            interval.Text = config.GetProperty("interval").ToString();
            startup.IsOn = config.TryGetProperty("autostart", out var auto) && auto.GetBoolean();
            initialized = true;
            detail.Text = "无新邮件不调用 AI。关闭窗口后会继续在托盘运行。";
            await Refresh();
            if (testResult != null) { await SelfTest(); return; }
            if (!config.GetProperty("has_mail_secret").GetBoolean() || account.Text.Length == 0)
                await Onboard();
            else if (config.TryGetProperty("enabled", out var enabled) && enabled.GetBoolean())
            {
                await Call("start"); running = true; toggle.Content = "暂停监听"; status.Text = "运行中";
            }
            if (Array.IndexOf(Program.Args, "--background") >= 0) AppWindow.Hide();
        }
        catch (Exception e)
        {
            detail.Text = e.Message;
            if (testResult != null) { File.WriteAllText(testResult, JsonSerializer.Serialize(new { ok = false, error = e.ToString() })); await Exit(); }
        }
    }
    async Task Onboard(bool testing = false)
    {
        var address = new TextBox { Header = "163 邮箱地址", Text = account.Text };
        var secret = new PasswordBox { Header = "POP3/IMAP/SMTP 授权码" };
        var error = Note("");
        var dialog = new ContentDialog { XamlRoot = layout.XamlRoot, Title = "欢迎使用邮件小秘书",
            PrimaryButtonText = "保存邮箱", CloseButtonText = "稍后填写", Content = Stack(address, secret,
            Note("在163邮箱设置中启用 IMAP，并生成授权码。报告目录可在设置里点“浏览……”选择。"), error) };
        dialog.PrimaryButtonClick += async (_, e) =>
        {
            var deferral = e.GetDeferral();
            try { account.Text = address.Text; mailSecret.Password = secret.Password; await SaveMail(); }
            catch (Exception ex) { e.Cancel = true; error.Text = ex.Message; }
            finally { deferral.Complete(); }
        };
        var showing = dialog.ShowAsync();
        if (testing)
        {
            await Task.Delay(400);
            if (!dialog.IsLoaded) throw new InvalidOperationException("First-run account dialog did not render");
            dialog.Hide();
        }
        await showing;
    }
    void Restore() { AppWindow.Show(); Activate(); }
    async Task Exit()
    {
        if (exiting || exitRequested) return;
        exitRequested = true;
        detail.Text = "正在停止后台，请稍候…";
        toggle.IsEnabled = check.IsEnabled = false;
        try { await bridge.Call("shutdown"); }
        catch (Exception e) { detail.Text = e.Message; }
        exiting = true; tray.Visible = false; tray.Dispose(); bridge.Dispose();
        Close();
    }
    async Task SelfTest()
    {
        var checks = new List<string>();
        void Check(bool ok, string label) { if (!ok) throw new InvalidOperationException(label); checks.Add(label); }
        try
        {
            var localRuntime = false;
            var localWinUI = false;
            foreach (ProcessModule module in Process.GetCurrentProcess().Modules)
            {
                if (module.ModuleName.Equals("coreclr.dll", StringComparison.OrdinalIgnoreCase))
                    localRuntime = module.FileName.StartsWith(AppContext.BaseDirectory, StringComparison.OrdinalIgnoreCase);
                if (module.ModuleName.Equals("Microsoft.UI.Xaml.dll", StringComparison.OrdinalIgnoreCase))
                    localWinUI = module.FileName.StartsWith(AppContext.BaseDirectory, StringComparison.OrdinalIgnoreCase);
            }
            Check(localRuntime && localWinUI, "Uses bundled .NET and WinUI runtimes");
            Check(reports.Items.Count == 1, "Native WinUI 3 window receives synthetic reports through packaged worker");
            var report = (Report)reports.Items[0];
            Check(report.title == "模拟合同检查" && report.time == "2026-10-17 09:15", "Subject and received time are separate");
            search.Text = "合同.pdf"; await Refresh();
            Check(reports.Items.Count == 1, "Attachment filename search");
            search.Text = "不存在"; await Refresh();
            Check(reports.Items.Count == 0, "Search excludes unmatched reports");
            search.Text = ""; attachment.SelectedIndex = 2; await Refresh();
            Check(reports.Items.Count == 0, "Attachment filter");
            attachment.SelectedIndex = 0; from.Date = new DateTimeOffset(2026, 10, 18, 0, 0, 0, TimeSpan.FromHours(8)); await Refresh();
            Check(reports.Items.Count == 0, "Compact date picker filter");
            from.Date = null; sender.Text = "missing"; await Refresh();
            Check(reports.Items.Count == 0, "Sender filter");
            sender.Text = ""; await Refresh();
            var content = await bridge.Call("read_report", new { report.path });
            preview.Text = content.GetString();
            Check(preview.Text.Contains("建议回复") && preview.Text.Contains("附件实际内容"), "Full report preview");
            await bridge.Call("interval", new { seconds = 35 });
            var config = await bridge.Call("config");
            Check(config.GetProperty("interval").GetInt32() == 35, "Custom interval reaches backend");
            try { await bridge.Call("interval", new { seconds = 0 }); throw new Exception("Invalid interval accepted"); }
            catch (InvalidOperationException) { checks.Add("Invalid interval rejected"); }
            AppWindow.Hide(); Restore();
            Check(tray.Visible, "Envelope tray icon and window restore");
            await Task.Delay(1000);
            var bounds = AppWindow.Position; var size = AppWindow.Size;
            var screenArg = Array.IndexOf(Program.Args, "--screenshot");
            if (screenArg >= 0)
            {
                using var image = new System.Drawing.Bitmap(size.Width, size.Height);
                using var graphics = System.Drawing.Graphics.FromImage(image);
                graphics.CopyFromScreen(bounds.X, bounds.Y, 0, 0, image.Size);
                image.Save(Program.Args[screenArg + 1], System.Drawing.Imaging.ImageFormat.Png);
            }
            Check(layout.ActualWidth > 0 && preview.ActualHeight > 100 && reports.ActualHeight > 100,
                "Native window, report list and preview rendered");
            Check(from.ActualHeight < 100 && to.ActualHeight < 100, "Date filters stay compact until opened");
            await Onboard(true);
            checks.Add("First-run native account dialog renders");
            File.WriteAllText(testResult!, JsonSerializer.Serialize(new { ok = true, checks }, new JsonSerializerOptions { WriteIndented = true }));
        }
        catch (Exception e) { File.WriteAllText(testResult!, JsonSerializer.Serialize(new { ok = false, checks, error = e.ToString() })); }
        finally { await Exit(); if (fixture != null) Directory.Delete(fixture, true); }
    }
}

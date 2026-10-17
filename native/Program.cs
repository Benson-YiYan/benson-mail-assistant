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
        Forms.WindowsFormsSynchronizationContext.AutoInstall = false;
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
    volatile bool shuttingDown;
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
            if (shuttingDown) return;
            using var error = JsonDocument.Parse(JsonSerializer.Serialize(new { status = "后台已停止", detail = e.Message }));
            Event?.Invoke(error.RootElement.Clone());
        }
    }
    public async Task<JsonElement> Call(string command, object? data = null)
    {
        if (command == "shutdown") shuttingDown = true;
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

[Microsoft.UI.Xaml.Data.Bindable]
public sealed record Report(string path, string title, string sender, string time, bool? attachments)
{
    public override string ToString() => title + "\n" + sender + "  ·  " + time + (attachments == true ? "  ·  有附件" : "");
}

sealed class MainWindow : Window
{
    readonly Grid layout = new();
    readonly NavigationView navigation = new() { PaneDisplayMode = NavigationViewPaneDisplayMode.Left,
        OpenPaneLength = 200, IsBackButtonVisible = NavigationViewBackButtonVisible.Collapsed,
        IsSettingsVisible = false, IsPaneOpen = true };
    readonly Grid pages = new() { Padding = new Thickness(24, 12, 24, 20) };
    readonly Grid reportPage = new() { RowSpacing = 16 };
    readonly Grid mailPage = new();
    readonly Grid aiPage = new();
    readonly TextBlock pageTitle = new() { Text = "邮件报告", FontSize = 28, FontWeight = Microsoft.UI.Text.FontWeights.SemiBold };
    readonly TextBlock reportCount = new() { Opacity = .65, VerticalAlignment = VerticalAlignment.Center };
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
    readonly TextBox interval = new() { Text = "60", Width = 130, Header = "自定义间隔（秒）" };
    readonly TextBox search = new() { PlaceholderText = "搜索正文、发件人、附件名", HorizontalAlignment = HorizontalAlignment.Stretch };
    readonly TextBox sender = new() { Header = "发件人", PlaceholderText = "姓名或邮箱" };
    readonly CalendarDatePicker from = new() { Header = "起始日期", PlaceholderText = "不限", MinWidth = 0, HorizontalAlignment = HorizontalAlignment.Stretch };
    readonly CalendarDatePicker to = new() { Header = "结束日期", PlaceholderText = "不限", MinWidth = 0, HorizontalAlignment = HorizontalAlignment.Stretch };
    readonly ComboBox attachment = new() { Header = "附件", HorizontalAlignment = HorizontalAlignment.Stretch };
    readonly ListView reports = new() { SelectionMode = ListViewSelectionMode.Single };
    readonly TextBox preview = new() { IsReadOnly = true, AcceptsReturn = true, TextWrapping = TextWrapping.Wrap,
        PlaceholderText = "选择一封邮件，查看六项报告。", VerticalAlignment = VerticalAlignment.Stretch };
    readonly Button toggle = new() { Content = "开始监听" };
    readonly Button check = new() { Content = "立即检查" };
    readonly Forms.NotifyIcon tray;
    readonly Bridge bridge;
    readonly Microsoft.UI.Dispatching.DispatcherQueueTimer searchTimer;
    readonly string? testResult;
    readonly string? fixture;
    readonly HashSet<string> notified = new();
    Button mailSaveButton = null!, aiSaveButton = null!;
    Button filterButton = null!;
    Flyout filters = null!;
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
        searchTimer = DispatcherQueue.CreateTimer();
        searchTimer.Interval = TimeSpan.FromMilliseconds(200);
        searchTimer.IsRepeating = false;
        searchTimer.Tick += async (_, _) => await Guard(Refresh);
        bridge.Event += ev => DispatcherQueue.TryEnqueue(() => { if (!exitRequested) HandleEvent(ev); });
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
        button.Click += async (_, _) => { if (exitRequested) return; button.IsEnabled = false; try { await action(); } catch (Exception e) { if (!exitRequested) detail.Text = e.Message; } finally { if (!exitRequested) button.IsEnabled = true; } };
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
    static Grid SettingsPage(UIElement content, FrameworkElement actions)
    {
        var page = new Grid { RowSpacing = 10 };
        page.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) });
        page.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        page.Children.Add(Scroll(content));
        Grid.SetRow(actions, 1); page.Children.Add(actions);
        return page;
    }
    static Brush ThemeBrush(string key) => (Brush)Application.Current.Resources[key];
    static Border Card(UIElement content, double padding = 18) => new()
    {
        Child = content, Padding = new Thickness(padding), CornerRadius = new CornerRadius(8),
        Background = ThemeBrush("CardBackgroundFillColorDefaultBrush"),
        BorderBrush = ThemeBrush("CardStrokeColorDefaultBrush"), BorderThickness = new Thickness(1)
    };
    static TextBlock Heading(string text) => new() { Text = text, FontSize = 18,
        FontWeight = Microsoft.UI.Text.FontWeights.SemiBold };
    void ShowPage(int index)
    {
        reportPage.Visibility = index == 0 ? Visibility.Visible : Visibility.Collapsed;
        mailPage.Visibility = index == 1 ? Visibility.Visible : Visibility.Collapsed;
        aiPage.Visibility = index == 2 ? Visibility.Visible : Visibility.Collapsed;
        pageTitle.Text = index == 0 ? "邮件报告" : index == 1 ? "邮箱与检查" : "AI 服务";
    }
    void BuildLeft()
    {
        navigation.PaneHeader = Row(new SymbolIcon(Symbol.Mail) { Margin = new Thickness(12, 0, 0, 0) },
            new TextBlock { Text = "邮件小秘书", FontSize = 17, FontWeight = Microsoft.UI.Text.FontWeights.SemiBold,
                VerticalAlignment = VerticalAlignment.Center });
        navigation.MenuItems.Add(new NavigationViewItem { Content = "邮件报告", Icon = new SymbolIcon(Symbol.Mail), Tag = 0 });
        navigation.MenuItems.Add(new NavigationViewItem { Content = "邮箱与检查", Icon = new SymbolIcon(Symbol.Setting), Tag = 1 });
        navigation.MenuItems.Add(new NavigationViewItem { Content = "AI 服务", Icon = new SymbolIcon(Symbol.Message), Tag = 2 });
        navigation.PaneFooter = Stack(Action("打开报告文件夹", () =>
        {
            Directory.CreateDirectory(folder.Text); Open(folder.Text); return Task.CompletedTask;
        }), Action("退出邮件小秘书", Exit), Note("无新邮件，不调用 AI。"));
        navigation.SelectionChanged += (_, e) =>
        {
            if (e.SelectedItem is NavigationViewItem item && item.Tag is int index) ShowPage(index);
        };
        var shell = new Grid { RowSpacing = 16 };
        shell.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        shell.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        shell.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) });
        shell.Children.Add(pageTitle);
        status.FontSize = 16;
        detail.FontSize = 12; detail.Opacity = .7;
        var service = new Grid { ColumnSpacing = 16 };
        service.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        service.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        service.Children.Add(Stack(status, detail));
        toggle.Style = (Style)Application.Current.Resources["AccentButtonStyle"];
        var serviceActions = Row(toggle, check); serviceActions.VerticalAlignment = VerticalAlignment.Center;
        Grid.SetColumn(serviceActions, 1); service.Children.Add(serviceActions);
        var serviceCard = Card(service, 16); Grid.SetRow(serviceCard, 1); shell.Children.Add(serviceCard);
        Grid.SetRow(pages, 2); shell.Children.Add(pages);
        pages.Padding = new Thickness(0);
        pages.Children.Add(reportPage); pages.Children.Add(mailPage); pages.Children.Add(aiPage);
        navigation.Content = new Border { Child = shell, Padding = new Thickness(24, 12, 24, 20) };
        layout.Children.Add(navigation);
        provider.Items.Add("API · 无需安装 Codex"); provider.Items.Add("Codex · 已安装并登录");
        mailSaveButton = Action("保存邮箱设置", SaveMail);
        aiSaveButton = Action("保存 AI 设置", SaveAI);
        mailSaveButton.Style = aiSaveButton.Style = (Style)Application.Current.Resources["AccentButtonStyle"];
        mailPage.Children.Add(SettingsPage(Stack(
            Card(Stack(Heading("邮箱账号"), account, mailSecret,
                Note("在 163 邮箱中启用 IMAP，使用邮箱授权码。授权码由 Windows 加密保存。"))),
            Card(Stack(Heading("报告与后台运行"), folder, Action("浏览……", PickFolder), startup,
                Row(interval, Action("应用间隔", async () =>
                {
                    if (!int.TryParse(interval.Text, out var seconds)) throw new InvalidOperationException("请填写整数秒数。");
                    await Call("interval", new { seconds });
                }))))),
            Row(mailSaveButton, Action("测试邮箱连接", async () => { await SaveMail(); await Call("test_mail"); }))));
        aiPage.Children.Add(SettingsPage(Stack(Card(Stack(Heading("选择您喜欢的 AI"), provider, apiBase, model, apiKey,
            Row(Action("查找 Codex", async () => await Call("codex")), Action("浏览……", PickCodex)),
            Note("来信及可读取的附件文字交给所选 AI，整理为六项报告。测试连接会发送少量文字。")))),
            Row(aiSaveButton, Action("测试 AI 连接", async () => { await SaveAI(); await Call("test_ai"); }))));
        toggle.Click += async (_, _) => await Guard(ToggleService);
        check.Click += async (_, _) => await Guard(async () =>
        {
            check.IsEnabled = false;
            try { await Call("check"); } catch { if (!exitRequested) check.IsEnabled = true; throw; }
        });
        navigation.SelectedItem = navigation.MenuItems[0];
        ShowPage(0);
    }
    void BuildRight()
    {
        var pane = reportPage;
        pane.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        pane.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) });
        attachment.Items.Add("全部"); attachment.Items.Add("有附件"); attachment.Items.Add("无附件"); attachment.SelectedIndex = 0;
        var dates = new Grid { ColumnSpacing = 8 };
        for (int i = 0; i < 4; i++) dates.ColumnDefinitions.Add(new ColumnDefinition());
        dates.Children.Add(sender); Grid.SetColumn(from, 1); dates.Children.Add(from);
        Grid.SetColumn(to, 2); dates.Children.Add(to); Grid.SetColumn(attachment, 3); dates.Children.Add(attachment);
        filters = new Flyout { Content = Stack(new TextBlock { Text = "筛选邮件", FontSize = 18 }, dates,
            Row(Action("应用筛选", async () => { await Refresh(); filters.Hide(); }), Action("重置", async () =>
            { search.Text = sender.Text = ""; from.Date = to.Date = null; attachment.SelectedIndex = 0; await Refresh(); }),
            reportCount)) };
        dates.Width = 600;
        var toolbar = new Grid { ColumnSpacing = 8 };
        toolbar.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        toolbar.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        toolbar.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        toolbar.Children.Add(search);
        filterButton = new Button { Content = Row(new SymbolIcon(Symbol.Filter) { Width = 16 }, new TextBlock { Text = "筛选" }), Flyout = filters };
        Grid.SetColumn(filterButton, 1); toolbar.Children.Add(filterButton);
        var refreshButton = Action("刷新", Refresh); Grid.SetColumn(refreshButton, 2); toolbar.Children.Add(refreshButton);
        pane.Children.Add(toolbar);
        var reading = new Grid { ColumnSpacing = 12 };
        reading.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(300) });
        reading.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        reports.BorderThickness = new Thickness(0);
        reports.ItemTemplate = (DataTemplate)Microsoft.UI.Xaml.Markup.XamlReader.Load(
            """<DataTemplate xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"><StackPanel Padding="4,12" Spacing="6"><TextBlock Text="{Binding title}" FontSize="15" FontWeight="SemiBold" TextTrimming="CharacterEllipsis"/><TextBlock Text="{Binding sender}" FontSize="12" Opacity="0.7" TextTrimming="CharacterEllipsis"/><TextBlock Text="{Binding time}" FontSize="12" Opacity="0.55"/></StackPanel></DataTemplate>""");
        reading.Children.Add(Card(reports, 4));
        var article = new Grid { RowSpacing = 12 };
        article.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        article.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) });
        article.Children.Add(Row(Heading("邮件报告"), Action("打开 TXT", () =>
            { if (reports.SelectedItem is Report report) Open(report.path); return Task.CompletedTask; })));
        preview.BorderThickness = new Thickness(0);
        preview.Background = new SolidColorBrush(Microsoft.UI.Colors.Transparent);
        preview.FontSize = 14;
        Grid.SetRow(preview, 1); article.Children.Add(preview);
        var articleCard = Card(article); Grid.SetColumn(articleCard, 1); reading.Children.Add(articleCard);
        Grid.SetRow(reading, 1); pane.Children.Add(reading);
        ScrollViewer.SetVerticalScrollBarVisibility(preview, ScrollBarVisibility.Auto);
        reports.SelectionChanged += async (_, _) => await Guard(async () =>
        {
            var generation = ++previewGeneration;
            preview.Text = "";
            if (reports.SelectedItem is Report report)
            {
                var result = await bridge.Call("read_report", new { path = report.path });
                if (!exitRequested && generation == previewGeneration) preview.Text = result.GetString() ?? "";
            }
        });
        search.TextChanged += (_, _) =>
        {
            if (initialized && !exitRequested) { searchTimer.Stop(); searchTimer.Start(); }
        };
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
        finally { if (!exitRequested) toggle.IsEnabled = true; }
    }
    async Task Guard(Func<Task> work)
    {
        if (exitRequested) return;
        try { await work(); } catch (Exception e) { if (!exitRequested) detail.Text = e.Message; }
    }
    async Task<JsonElement> Call(string name, object? data = null)
    {
        detail.Text = "正在处理…";
        var result = await bridge.Call(name, data);
        if (!exitRequested && result.ValueKind == JsonValueKind.String) detail.Text = result.GetString() ?? "";
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
        if (picked != null && !exitRequested) folder.Text = picked.Path;
    }
    async Task PickCodex()
    {
        var picker = new Windows.Storage.Pickers.FileOpenPicker();
        WinRT.Interop.InitializeWithWindow.Initialize(picker, WinRT.Interop.WindowNative.GetWindowHandle(this));
        picker.FileTypeFilter.Add(".exe"); picker.FileTypeFilter.Add(".cmd");
        var picked = await picker.PickSingleFileAsync();
        if (picked != null && !exitRequested) await Call("codex", new { path = picked.Path });
    }
    async Task Refresh()
    {
        if (exitRequested) return;
        searchTimer.Stop();
        var generation = ++reportGeneration;
        var selected = (reports.SelectedItem as Report)?.path;
        var result = await bridge.Call("reports", new { query = search.Text, sender = sender.Text,
            start = from.Date?.ToString("yyyy-MM-dd") ?? "", end = to.Date?.ToString("yyyy-MM-dd") ?? "",
            attachments = attachment.SelectedItem?.ToString() ?? "全部" });
        if (exitRequested || generation != reportGeneration) return;
        reports.Items.Clear();
        foreach (var row in result.EnumerateArray())
        {
            var report = new Report(row.GetProperty("path").GetString()!, row.GetProperty("title").GetString()!,
                row.GetProperty("sender").GetString()!, row.GetProperty("time").GetString()!,
                row.GetProperty("attachments").ValueKind == JsonValueKind.Null ? null : row.GetProperty("attachments").GetBoolean());
            reports.Items.Add(report);
            if (report.path == selected) reports.SelectedItem = report;
        }
        reportCount.Text = $"{reports.Items.Count} 封邮件";
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
            if (exitRequested) return;
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
        // Return through the dispatcher after the native dialog callback unwinds.
        await Task.Yield();
    }
    void Restore() { AppWindow.Show(); Activate(); }
    async Task Exit()
    {
        if (exiting || exitRequested) return;
        exitRequested = true;
        searchTimer.Stop();
        Program.Trace("Stopping worker");
        detail.Text = "正在停止后台，请稍候…";
        toggle.IsEnabled = check.IsEnabled = false;
        try { await bridge.Call("shutdown"); }
        catch (Exception e) { detail.Text = e.Message; }
        Program.Trace("Disposing tray and worker pipes");
        exiting = true; tray.Visible = false; tray.Dispose(); bridge.Dispose();
        Program.Trace("Exiting application");
        Application.Current.Exit();
    }
    async Task SelfTest()
    {
        var checks = new List<string>();
        void Check(bool ok, string label) { if (!ok) throw new InvalidOperationException(label); checks.Add(label); }
        async Task ReportsReady(int count)
        {
            await Refresh();
            var deadline = DateTime.UtcNow.AddSeconds(3);
            while (reports.Items.Count != count && DateTime.UtcNow < deadline)
                await Task.Delay(25);
        }
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
            var runtime = await bridge.Call("runtime_info");
            Check(!runtime.GetProperty("console_visible").GetBoolean(), "Packaged mail worker runs without a visible console window");
            Check(reports.Items.Count == 1, "Native WinUI 3 window receives synthetic reports through packaged worker");
            var report = (Report)reports.Items[0];
            Check(report.title == "模拟合同检查" && report.time == "2026-10-17 09:15", "Subject and received time are separate");
            search.Text = "合同.pdf"; await ReportsReady(1);
            Check(reports.Items.Count == 1, "Attachment filename search");
            search.Text = "不存在"; await ReportsReady(0);
            Check(reports.Items.Count == 0, "Search excludes unmatched reports");
            search.Text = ""; attachment.SelectedIndex = 2; await ReportsReady(0);
            Check(reports.Items.Count == 0, "Attachment filter");
            attachment.SelectedIndex = 0; from.Date = new DateTimeOffset(new DateTime(2026, 10, 18, 12, 0, 0)); await ReportsReady(0);
            Check(reports.Items.Count == 0, "Compact date picker filter");
            from.Date = null; sender.Text = "missing"; await ReportsReady(0);
            Check(reports.Items.Count == 0, "Sender filter");
            sender.Text = ""; await ReportsReady(1);
            var content = await bridge.Call("read_report", new { report.path });
            preview.Text = content.GetString() ?? "";
            Check(preview.Text.Contains("建议回复") && preview.Text.Contains("附件实际内容"), "Full report preview");
            await bridge.Call("interval", new { seconds = 35 });
            var config = await bridge.Call("config");
            Check(config.GetProperty("interval").GetInt32() == 35, "Custom interval reaches backend");
            try { await bridge.Call("interval", new { seconds = 0 }); throw new Exception("Invalid interval accepted"); }
            catch (InvalidOperationException) { checks.Add("Invalid interval rejected"); }
            AppWindow.Hide(); Restore();
            Check(tray.Visible, "Envelope tray icon and window restore");
            await Task.Delay(1000);
            var screenArg = Array.IndexOf(Program.Args, "--screenshot");
            void Capture(string path)
            {
                var bounds = AppWindow.Position; var size = AppWindow.Size;
                using var image = new System.Drawing.Bitmap(size.Width, size.Height);
                using var graphics = System.Drawing.Graphics.FromImage(image);
                graphics.CopyFromScreen(bounds.X, bounds.Y, 0, 0, image.Size);
                image.Save(path, System.Drawing.Imaging.ImageFormat.Png);
            }
            if (screenArg >= 0) Capture(Program.Args[screenArg + 1]);
            Check(layout.ActualWidth > 0 && preview.ActualHeight > 100 && reports.ActualHeight > 100,
                "Native window, report list and preview rendered");
            Check(navigation.IsPaneOpen && reportPage.Visibility == Visibility.Visible &&
                reports.ActualHeight > 250 && preview.ActualHeight > 250,
                "Fluent navigation and full height side by side report reader");
            filters.ShowAt(filterButton);
            await Task.Delay(400);
            Check(from.ActualHeight > 0 && from.ActualHeight < 100 && to.ActualHeight > 0 && to.ActualHeight < 100,
                "Filter flyout renders compact date pickers");
            filters.Hide();
            bool Visible(Button button)
            {
                var point = button.TransformToVisual(layout).TransformPoint(new Windows.Foundation.Point(0, 0));
                return button.ActualHeight > 0 && point.Y >= 0 && point.Y + button.ActualHeight <= layout.ActualHeight;
            }
            navigation.SelectedItem = navigation.MenuItems[1];
            await Task.Delay(400);
            layout.UpdateLayout();
            Check(Visible(mailSaveButton), "Mail save button visible without scrolling");
            navigation.SelectedItem = navigation.MenuItems[2];
            await Task.Delay(400);
            layout.UpdateLayout();
            Check(Visible(aiSaveButton), "AI save button visible without scrolling");
            if (screenArg >= 0)
            {
                var path = Program.Args[screenArg + 1];
                Capture(Path.Combine(Path.GetDirectoryName(path)!, Path.GetFileNameWithoutExtension(path) + "-settings.png"));
            }
            navigation.SelectedItem = navigation.MenuItems[0];
            await Onboard(true);
            checks.Add("First-run native account dialog renders");
            File.WriteAllText(testResult!, JsonSerializer.Serialize(new { ok = true, checks }, new JsonSerializerOptions { WriteIndented = true }));
        }
        catch (Exception e) { File.WriteAllText(testResult!, JsonSerializer.Serialize(new { ok = false, checks, error = e.ToString() })); }
        finally { await Exit(); if (fixture != null) Directory.Delete(fixture, true); }
    }
}

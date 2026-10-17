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
    internal static bool Uninstall => Path.GetFileName(Environment.ProcessPath ?? "").StartsWith("Uninstall-BensonMail-", StringComparison.OrdinalIgnoreCase);
    internal static void Trace(string stage)
    {
        var index = Array.IndexOf(Args, "--self-test");
        if (index < 0) index = Array.IndexOf(Args, "--uninstall-ui-test");
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
        using var mutex = new Mutex(false, Uninstall ? null : @"Local\BensonMail-" + Environment.UserName, out var created);
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
    Window? window;
    public MailApp()
    {
        Program.Trace("App constructor");
        UnhandledException += (_, e) =>
        {
            Program.Trace("Unhandled: " + e.Exception);
            var index = Array.IndexOf(Program.Args, "--self-test");
            if (index < 0) index = Array.IndexOf(Program.Args, "--uninstall-ui-test");
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
        window = Program.Uninstall ? new UninstallWindow() : new MainWindow();
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

public sealed class Report
{
    public string path { get; set; }
    public string title { get; set; }
    public string sender { get; set; }
    public string time { get; set; }
    public bool? attachments { get; set; }
    public Report(string path, string title, string sender, string time, bool? attachments)
    {
        this.path = path; this.title = title; this.sender = sender;
        this.time = time; this.attachments = attachments;
    }
    public override string ToString() => title + "\n" + sender + "  ·  " + time + (attachments == true ? "  ·  有附件" : "");
}

sealed class MainWindow : Window
{
    readonly Grid layout = new() { UseLayoutRounding = true, Language = "zh-CN" };
    readonly ListView navigation = new() { SelectionMode = ListViewSelectionMode.Single,
        BorderThickness = new Thickness(0), Background = new SolidColorBrush(Microsoft.UI.Colors.Transparent) };
    readonly Grid pages = new() { Padding = new Thickness(24, 12, 24, 20) };
    readonly Grid reportPage = new() { RowSpacing = 16 };
    readonly Grid mailPage = new();
    readonly Grid aiPage = new();
    readonly TextBlock pageTitle = new() { Text = "邮件报告", FontSize = 28, FontWeight = Microsoft.UI.Text.FontWeights.SemiBold };
    readonly TextBlock reportCount = new() { Opacity = .65, VerticalAlignment = VerticalAlignment.Center };
    readonly TextBlock status = new() { Text = "已暂停", FontSize = 23, FontWeight = Microsoft.UI.Text.FontWeights.SemiBold };
    readonly TextBlock detail = new() { Text = "正在加载设置…", TextWrapping = TextWrapping.Wrap };
    readonly TextBox account = new() { Header = "邮箱地址", PlaceholderText = "name@example.com" };
    readonly PasswordBox mailSecret = new() { Header = "密码／授权码／OAuth2 访问令牌", PlaceholderText = "连接信息未变时可留空保留" };
    readonly ComboBox mailProvider = new() { Header = "邮箱服务商", HorizontalAlignment = HorizontalAlignment.Stretch };
    readonly TextBox mailHost = new() { Header = "IMAP 收件服务器", Text = "imap.163.com" };
    readonly TextBox mailPort = new() { Header = "端口", Text = "993" };
    readonly ComboBox mailSecurity = new() { Header = "连接加密", HorizontalAlignment = HorizontalAlignment.Stretch };
    readonly ComboBox mailAuth = new() { Header = "登录方式", HorizontalAlignment = HorizontalAlignment.Stretch };
    readonly TextBox mailUsername = new() { Header = "登录用户名（可选）", PlaceholderText = "留空使用邮箱地址" };
    readonly TextBox mailFolder = new() { Header = "邮件文件夹", Text = "INBOX" };
    readonly List<JsonElement> mailPresets = new();
    readonly ComboBox savedMailboxes = new() { Header = "已添加的邮箱", HorizontalAlignment = HorizontalAlignment.Stretch };
    readonly List<JsonElement> mailboxProfiles = new();
    bool loadingMailboxes;
    readonly TextBox folder = new() { Header = "报告保存文件夹" };
    readonly ToggleSwitch startup = new() { Header = "登录 Windows 后自动启动", OnContent = "开启", OffContent = "关闭" };
    readonly ComboBox provider = new() { Header = "分析方式", HorizontalAlignment = HorizontalAlignment.Stretch };
    readonly TextBox harnessPath = new() { Header = "DeepSeek Harness 启动器", PlaceholderText = "dsh.cmd / dsh.exe 路径；留空自动查找" };
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
    readonly Button toggle = new() { Content = "开始监听", CornerRadius = new CornerRadius(4) };
    readonly Button check = new() { Content = "立即检查", CornerRadius = new CornerRadius(4) };
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
    Report? SelectedReport => (reports.SelectedItem as ListViewItem)?.Tag as Report;

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
        var frame = new Grid();
        frame.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        frame.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) });
        if (AppWindowTitleBar.IsCustomizationSupported())
        {
            ExtendsContentIntoTitleBar = true;
            var caption = new Grid { Height = 40, Background = new SolidColorBrush(Microsoft.UI.Colors.Transparent) };
            caption.Children.Add(new TextBlock { Text = "邮件小秘书", FontFamily = MailTypography.Font, FontSize = 12,
                Margin = new Thickness(20, 0, 150, 0), VerticalAlignment = VerticalAlignment.Center });
            frame.Children.Add(caption);
            SetTitleBar(caption);
            AppWindow.TitleBar.ButtonBackgroundColor = Microsoft.UI.Colors.Transparent;
            AppWindow.TitleBar.ButtonInactiveBackgroundColor = Microsoft.UI.Colors.Transparent;
            if (AppWindow.Presenter is OverlappedPresenter presenter) presenter.SetBorderAndTitleBar(true, true);
        }
        Grid.SetRow(layout, 1); frame.Children.Add(layout);
        Content = new ContentControl { Content = frame, FontFamily = MailTypography.Font, FontSize = 14,
            Language = "zh-CN", UseLayoutRounding = true, IsTabStop = false,
            HorizontalContentAlignment = HorizontalAlignment.Stretch, VerticalContentAlignment = VerticalAlignment.Stretch };
        BuildLeft();
        Program.Trace("Left controls");
        BuildRight();
        Secondary(check);
        Program.Trace("Right controls");
        foreach (var text in new[] { pageTitle, reportCount, status, detail })
            text.FontFamily = MailTypography.Font;
        foreach (var field in new Control[] { account, mailSecret, folder, provider, apiBase, model, harnessPath,
            apiKey, interval, search, sender, from, to, attachment, mailProvider, mailHost, mailPort,
            mailSecurity, mailAuth, mailUsername, mailFolder })
        {
            field.FontFamily = MailTypography.Font;
            field.CornerRadius = new CornerRadius(4);
            field.BorderThickness = new Thickness(1);
        }
        foreach (var control in new Control[] { preview, toggle, check, startup, navigation, reports })
            control.FontFamily = MailTypography.Font;
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
    static TextBlock Note(string text) => new() { FontFamily = MailTypography.Font, Text = text, TextWrapping = TextWrapping.Wrap, Opacity = .7, FontSize = 12 };
    static void Secondary(Button button)
    {
        button.CornerRadius = new CornerRadius(4);
        button.Padding = new Thickness(12, 8, 12, 8);
        button.MinHeight = 34;
        void Update()
        {
            if (button.Style == (Style)Application.Current.Resources["AccentButtonStyle"]) return;
            if (Forms.SystemInformation.HighContrast) { button.ClearValue(Control.BackgroundProperty); button.ClearValue(Control.BorderBrushProperty); return; }
            var dark = button.ActualTheme == ElementTheme.Dark;
            button.Background = new SolidColorBrush(Windows.UI.Color.FromArgb(dark ? (byte)15 : (byte)190, 255, 255, 255));
            button.BorderBrush = new SolidColorBrush(Windows.UI.Color.FromArgb(dark ? (byte)25 : (byte)30,
                dark ? (byte)255 : (byte)0, dark ? (byte)255 : (byte)0, dark ? (byte)255 : (byte)0));
        }
        button.Loaded += (_, _) => Update();
        button.ActualThemeChanged += (_, _) => Update();
    }
    static StackPanel Stack(params UIElement[] children)
    {
        var stack = new StackPanel { Spacing = 10 };
        foreach (var child in children) stack.Children.Add(child);
        return stack;
    }
    Button Action(string text, Func<Task> action)
    {
        var button = new Button { FontFamily = MailTypography.Font, Content = text };
        Secondary(button);
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
    static Border Card(UIElement content, double padding = 18)
    {
        var card = new Border { Child = content, Padding = new Thickness(padding),
            CornerRadius = new CornerRadius(8), BorderThickness = new Thickness(1) };
        void Update()
        {
            var dark = card.ActualTheme == ElementTheme.Dark;
            var background = System.Drawing.SystemColors.Window;
            var foreground = System.Drawing.SystemColors.WindowText;
            card.Background = new SolidColorBrush(Forms.SystemInformation.HighContrast
                ? Windows.UI.Color.FromArgb(background.A, background.R, background.G, background.B)
                : Windows.UI.Color.FromArgb(dark ? (byte)13 : (byte)179, 255, 255, 255));
            card.BorderBrush = new SolidColorBrush(Forms.SystemInformation.HighContrast
                ? Windows.UI.Color.FromArgb(foreground.A, foreground.R, foreground.G, foreground.B)
                : Windows.UI.Color.FromArgb(dark ? (byte)25 : (byte)15, 0, 0, 0));
        }
        card.Loaded += (_, _) => Update();
        card.ActualThemeChanged += (_, _) => Update();
        Microsoft.Win32.SystemEvents.UserPreferenceChanged += (_, _) => card.DispatcherQueue.TryEnqueue(() =>
        {
            if (card.XamlRoot != null) Update();
        });
        Update();
        return card;
    }
    static TextBlock Heading(string text) => new() { FontFamily = MailTypography.Font, Text = text, FontSize = 18,
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
        void NavigationColors()
        {
            var dark = navigation.ActualTheme == ElementTheme.Dark;
            var fill = new SolidColorBrush(Windows.UI.Color.FromArgb(dark ? (byte)22 : (byte)13,
                dark ? (byte)255 : (byte)0, dark ? (byte)255 : (byte)0, dark ? (byte)255 : (byte)0));
            var hover = new SolidColorBrush(Windows.UI.Color.FromArgb(dark ? (byte)30 : (byte)20,
                dark ? (byte)255 : (byte)0, dark ? (byte)255 : (byte)0, dark ? (byte)255 : (byte)0));
            foreach (var key in new[] { "ListViewItemBackgroundSelected", "ListViewItemBackgroundSelectedPointerOver", "ListViewItemBackgroundSelectedPressed" })
                navigation.Resources[key] = Forms.SystemInformation.HighContrast
                    ? new SolidColorBrush(Windows.UI.Color.FromArgb(255, 0, 95, 184)) : fill;
            navigation.Resources["ListViewItemBackgroundPointerOver"] = hover;
        }
        NavigationColors();
        navigation.ActualThemeChanged += (_, _) => NavigationColors();
        var brand = Row(new SymbolIcon(Symbol.Mail) { Margin = new Thickness(4, 0, 0, 0) },
            new TextBlock { FontFamily = MailTypography.Font, Text = "邮件小秘书", FontSize = 17, FontWeight = Microsoft.UI.Text.FontWeights.SemiBold,
                VerticalAlignment = VerticalAlignment.Center });
        foreach (var (label, symbol) in new[] { ("邮件报告", Symbol.Mail), ("邮箱与检查", Symbol.Setting), ("AI 服务", Symbol.Message) })
        {
            var indicator = new Border { Width = 3, Height = 18, CornerRadius = new CornerRadius(2),
                Background = new SolidColorBrush(Windows.UI.Color.FromArgb(255, 0, 95, 184)),
                Opacity = 0, VerticalAlignment = VerticalAlignment.Center };
            var item = new ListViewItem { Content = Row(indicator, new SymbolIcon(symbol) { Width = 20 },
                new TextBlock { FontFamily = MailTypography.Font, Text = label, VerticalAlignment = VerticalAlignment.Center }),
                Padding = new Thickness(8, 10, 10, 10), CornerRadius = new CornerRadius(4),
                Margin = new Thickness(0, 2, 0, 2), HorizontalContentAlignment = HorizontalAlignment.Stretch };
            navigation.SelectionChanged += (_, _) => indicator.Opacity = item.IsSelected ? 1 : 0;
            navigation.Items.Add(item);
        }
        var footer = Stack(Action("打开报告文件夹", () =>
        {
            Directory.CreateDirectory(folder.Text); Open(folder.Text); return Task.CompletedTask;
        }), Action("退出邮件小秘书", Exit), Note("无新邮件，不调用 AI。"));
        navigation.SelectionChanged += (_, _) =>
        {
            if (navigation.SelectedIndex >= 0) ShowPage(navigation.SelectedIndex);
        };
        var sidebar = new Grid { Padding = new Thickness(12, 12, 12, 16), RowSpacing = 24 };
        sidebar.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        sidebar.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) });
        sidebar.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        sidebar.Children.Add(brand);
        Grid.SetRow(navigation, 1); sidebar.Children.Add(navigation);
        Grid.SetRow(footer, 2); sidebar.Children.Add(footer);
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
        layout.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(200) });
        layout.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        layout.Children.Add(sidebar);
        var main = new Border { Child = shell, Padding = new Thickness(28, 16, 24, 20) };
        Grid.SetColumn(main, 1); layout.Children.Add(main);
        provider.Items.Add("API · 无需安装 Codex"); provider.Items.Add("Codex · 已安装并登录"); provider.Items.Add("DeepSeek Harness · 使用已安装的应用");
        provider.SelectionChanged += (_, _) => {
            var api = provider.SelectedIndex == 0;
            apiBase.Visibility = model.Visibility = apiKey.Visibility = api ? Visibility.Visible : Visibility.Collapsed;
            harnessPath.Visibility = provider.SelectedIndex == 2 ? Visibility.Visible : Visibility.Collapsed;
        };
        mailSecurity.Items.Add("SSL/TLS"); mailSecurity.Items.Add("STARTTLS"); mailSecurity.SelectedIndex = 0;
        mailAuth.Items.Add("密码／客户端授权码"); mailAuth.Items.Add("OAuth2 访问令牌"); mailAuth.SelectedIndex = 0;
        mailProvider.SelectionChanged += (_, _) =>
        {
            if (mailProvider.SelectedIndex < 0 || mailProvider.SelectedIndex >= mailPresets.Count) return;
            var preset = mailPresets[mailProvider.SelectedIndex];
            if (preset.GetProperty("id").GetString() == "custom") return;
            mailHost.Text = preset.GetProperty("host").GetString() ?? "";
            mailPort.Text = "993"; mailSecurity.SelectedIndex = 0;
            mailAuth.SelectedIndex = preset.TryGetProperty("mail_auth", out var auth) && auth.GetString() == "oauth2" ? 1 : 0;
        };
        mailSaveButton = Action("保存邮箱设置", SaveMail);
        aiSaveButton = Action("保存 AI 设置", SaveAI);
        mailSaveButton.Style = aiSaveButton.Style = (Style)Application.Current.Resources["AccentButtonStyle"];
        var advanced = Stack(mailUsername, mailFolder, mailAuth); advanced.Visibility = Visibility.Collapsed;
        savedMailboxes.SelectionChanged += async (_, _) =>
        {
            if (loadingMailboxes || savedMailboxes.SelectedIndex < 0) return;
            await Guard(async () => {
                await Call("select_mail", new { id = mailboxProfiles[savedMailboxes.SelectedIndex].GetProperty("id").GetString() });
                await ReloadMailboxes();
            });
        };
        mailPage.Children.Add(SettingsPage(Stack(
            Card(Stack(Heading("管理邮箱"), savedMailboxes,
                Row(Action("添加邮箱", async () => {
                    await Call("select_mail", new { id = "" }); await ReloadMailboxes();
                }), Action("启用／暂停此邮箱", async () => {
                    if (savedMailboxes.SelectedIndex < 0) throw new InvalidOperationException("请先选择已添加的邮箱。");
                    var profile = mailboxProfiles[savedMailboxes.SelectedIndex];
                    await Call("mail_enabled", new { id = profile.GetProperty("id").GetString(),
                        enabled = !(profile.TryGetProperty("monitor_enabled", out var flag) && flag.GetBoolean()) });
                    await ReloadMailboxes();
                }), Action("移除此邮箱", async () => {
                    if (savedMailboxes.SelectedIndex < 0) return;
                    var profile = mailboxProfiles[savedMailboxes.SelectedIndex];
                    var dialog = new ContentDialog { XamlRoot = layout.XamlRoot, Title = "移除此邮箱？",
                        Content = "停止此邮箱监听并移出列表，已生成的报告保留。", PrimaryButtonText = "移除", CloseButtonText = "取消" };
                    if (await dialog.ShowAsync() == ContentDialogResult.Primary) {
                        await Call("remove_mail", new { id = profile.GetProperty("id").GetString() }); await ReloadMailboxes();
                    }
                })), Note("可同时监听多个邮箱；AI、报告目录和检查间隔共用。编辑连接前请先暂停全部监听。"))),
            Card(Stack(Heading("邮箱连接"), mailProvider, account, mailHost, Row(mailPort, mailSecurity), mailSecret,
                Action("高级连接选项", () => { advanced.Visibility = advanced.Visibility == Visibility.Visible ? Visibility.Collapsed : Visibility.Visible; return Task.CompletedTask; }), advanced,
                Note("请启用邮箱的 IMAP 服务。按服务商要求使用客户端授权码或应用专用密码。OAuth2 需填写访问令牌，过期后手动更新；暂不自动登录和续期。"))),
            Card(Stack(Heading("报告与后台运行"), folder, Action("浏览……", PickFolder), startup,
                Row(interval, Action("应用间隔", async () =>
                {
                    if (!int.TryParse(interval.Text, out var seconds)) throw new InvalidOperationException("请填写整数秒数。");
                    await Call("interval", new { seconds });
                }))))),
            Row(mailSaveButton, Action("测试邮箱连接", async () => { await SaveMail(); await Call("test_mail"); }))));
        aiPage.Children.Add(SettingsPage(Stack(Card(Stack(Heading("选择您喜欢的 AI"), provider, apiBase, model, apiKey, harnessPath,
            Row(Action("检测 Harness", async () => { var found = await Call("harness_detect", new { path = harnessPath.Text }); harnessPath.Text = found.GetString() ?? ""; }), Action("浏览 Harness……", PickHarness)),
            Row(Action("查找 Codex", async () => await Call("codex")), Action("浏览……", PickCodex)),
            Note("来信及可读取的附件文字交给所选 AI，整理为六项报告。Harness 使用用户已安装的应用及其登录、模型配置，不捆绑或下载运行时。请先在 Harness 中配置；测试连接会发送少量文字。")))),
            Row(aiSaveButton, Action("测试 AI 连接", async () => { await SaveAI(); await Call("test_ai"); }))));
        toggle.Click += async (_, _) => await Guard(ToggleService);
        check.Click += async (_, _) => await Guard(async () =>
        {
            check.IsEnabled = false;
            try { await Call("check"); } catch { if (!exitRequested) check.IsEnabled = true; throw; }
        });
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
        filters = new Flyout { Content = Stack(new TextBlock { FontFamily = MailTypography.Font, Text = "筛选邮件", FontSize = 18 }, dates,
            Row(Action("应用筛选", async () => { await Refresh(); if (!exitRequested) filters.Hide(); }), Action("重置", async () =>
            { search.Text = sender.Text = ""; from.Date = to.Date = null; attachment.SelectedIndex = 0; await Refresh(); }),
            reportCount)) };
        dates.Width = 600;
        var toolbar = new Grid { ColumnSpacing = 8 };
        toolbar.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        toolbar.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        toolbar.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        toolbar.Children.Add(search);
        filterButton = new Button { FontFamily = MailTypography.Font, Content = Row(new SymbolIcon(Symbol.Filter) { Width = 16 },
            new TextBlock { FontFamily = MailTypography.Font, Text = "筛选" }),
            Flyout = filters };
        Secondary(filterButton);
        Grid.SetColumn(filterButton, 1); toolbar.Children.Add(filterButton);
        var refreshButton = Action("刷新", Refresh); Grid.SetColumn(refreshButton, 2); toolbar.Children.Add(refreshButton);
        pane.Children.Add(toolbar);
        var reading = new Grid { ColumnSpacing = 12 };
        reading.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(300) });
        reading.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        reports.BorderThickness = new Thickness(0);
        reading.Children.Add(Card(reports, 4));
        var article = new Grid { RowSpacing = 12 };
        article.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        article.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) });
        article.Children.Add(Row(Heading("邮件报告"), Action("打开 TXT", () =>
            { if (SelectedReport is Report report) Open(report.path); return Task.CompletedTask; })));
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
            if (SelectedReport is Report report)
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
        if (!int.TryParse(mailPort.Text, out var port)) throw new InvalidOperationException("请输入有效的 IMAP 端口。");
        await Call("save_mail", new { account = account.Text, secret = mailSecret.Password,
            output_dir = folder.Text, autostart = startup.IsOn,
            mail_provider = mailProvider.SelectedIndex >= 0 ? mailPresets[mailProvider.SelectedIndex].GetProperty("id").GetString() : "custom",
            host = mailHost.Text, port, security = mailSecurity.SelectedIndex == 1 ? "starttls" : "ssl",
            username = mailUsername.Text, mail_folder = mailFolder.Text, mail_auth = mailAuth.SelectedIndex == 1 ? "oauth2" : "password" });
        mailSecret.Password = "";
        await ReloadMailboxes();
    }
    async Task SaveAI()
    {
        await Call("save_ai", new { ai_provider = provider.SelectedIndex == 1 ? "codex" : provider.SelectedIndex == 2 ? "deepseek_harness" : "api",
            api_base = apiBase.Text, api_model = model.Text, key = apiKey.Password, harness_path = harnessPath.Text });
        apiKey.Password = "";
    }
    async Task PickHarness()
    {
        var picker = new Windows.Storage.Pickers.FileOpenPicker();
        WinRT.Interop.InitializeWithWindow.Initialize(picker, WinRT.Interop.WindowNative.GetWindowHandle(this));
        picker.FileTypeFilter.Add(".exe"); picker.FileTypeFilter.Add(".cmd");
        var picked = await picker.PickSingleFileAsync();
        if (picked != null && !exitRequested) harnessPath.Text = picked.Path;
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
        var selected = SelectedReport?.path;
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
            var lines = Stack(new TextBlock { FontFamily = MailTypography.Font, Text = report.title, FontSize = 15,
                FontWeight = Microsoft.UI.Text.FontWeights.SemiBold, TextTrimming = TextTrimming.CharacterEllipsis },
                new TextBlock { FontFamily = MailTypography.Font, Text = report.sender, FontSize = 12, Opacity = .7, TextTrimming = TextTrimming.CharacterEllipsis },
                new TextBlock { FontFamily = MailTypography.Font, Text = report.time, FontSize = 12, Opacity = .55 });
            lines.Spacing = 6;
            var item = new ListViewItem { Tag = report, Content = lines,
                Padding = new Thickness(12), CornerRadius = new CornerRadius(4),
                HorizontalContentAlignment = HorizontalAlignment.Stretch };
            reports.Items.Add(item);
            if (report.path == selected) reports.SelectedItem = item;
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
            var presets = await bridge.Call("mail_presets");
            if (exitRequested) return;
            foreach (var preset in presets.EnumerateArray())
            {
                mailPresets.Add(preset.Clone());
                mailProvider.Items.Add(preset.GetProperty("name").GetString());
            }
            navigation.SelectedIndex = 0;
            string Text(string key) => config.TryGetProperty(key, out var value) ? value.GetString() ?? "" : "";
            harnessPath.Text = Text("harness_path"); account.Text = Text("account"); folder.Text = Text("output_dir"); apiBase.Text = Text("api_base"); model.Text = Text("api_model");
            var presetId = Text("mail_provider");
            mailProvider.SelectedIndex = mailPresets.FindIndex(p => p.GetProperty("id").GetString() ==
                (presetId.Length == 0 ? (Text("host").Length == 0 || Text("host") == "imap.163.com" ? "163" : "custom") : presetId));
            mailHost.Text = Text("host").Length == 0 ? "imap.163.com" : Text("host");
            mailPort.Text = config.TryGetProperty("port", out var savedPort) ? savedPort.ToString() : "993";
            mailUsername.Text = Text("username"); mailFolder.Text = Text("mail_folder").Length == 0 ? "INBOX" : Text("mail_folder");
            mailSecurity.SelectedIndex = Text("security") == "starttls" ? 1 : 0;
            mailAuth.SelectedIndex = Text("mail_auth") == "oauth2" ? 1 : 0;
            provider.SelectedIndex = Text("ai_provider") == "codex" ? 1 : Text("ai_provider") == "deepseek_harness" ? 2 : 0;
            interval.Text = config.GetProperty("interval").ToString();
            startup.IsOn = config.TryGetProperty("autostart", out var auto) && auto.GetBoolean();
            await ReloadMailboxes();
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
        var address = new TextBox { FontFamily = MailTypography.Font, Header = "邮箱地址", Text = account.Text };
        var secret = new PasswordBox { FontFamily = MailTypography.Font, Header = "密码／授权码／OAuth2 访问令牌" };
        var presetChoice = new ComboBox { Header = "邮箱服务商", HorizontalAlignment = HorizontalAlignment.Stretch };
        var host = new TextBox { Header = "IMAP 收件服务器", Text = mailHost.Text };
        var port = new TextBox { Header = "端口", Text = mailPort.Text };
        var username = new TextBox { Header = "登录用户名（可选）", PlaceholderText = "留空使用邮箱地址", Text = mailUsername.Text };
        var mailboxFolder = new TextBox { Header = "邮件文件夹", Text = mailFolder.Text };
        var encryption = new ComboBox { Header = "连接加密", HorizontalAlignment = HorizontalAlignment.Stretch };
        encryption.Items.Add("SSL/TLS"); encryption.Items.Add("STARTTLS"); encryption.SelectedIndex = mailSecurity.SelectedIndex;
        var authentication = new ComboBox { Header = "登录方式", HorizontalAlignment = HorizontalAlignment.Stretch };
        authentication.Items.Add("密码／客户端授权码"); authentication.Items.Add("OAuth2 访问令牌"); authentication.SelectedIndex = mailAuth.SelectedIndex;
        foreach (var preset in mailPresets) presetChoice.Items.Add(preset.GetProperty("name").GetString());
        presetChoice.SelectedIndex = mailProvider.SelectedIndex;
        presetChoice.SelectionChanged += (_, _) =>
        {
            if (presetChoice.SelectedIndex < 0) return;
            var preset = mailPresets[presetChoice.SelectedIndex];
            if (preset.GetProperty("id").GetString() == "custom") return;
            host.Text = preset.GetProperty("host").GetString(); port.Text = "993"; encryption.SelectedIndex = 0;
            authentication.SelectedIndex = preset.TryGetProperty("mail_auth", out var auth) && auth.GetString() == "oauth2" ? 1 : 0;
        };
        var error = Note("");
        var advanced = Stack(username, mailboxFolder, authentication); advanced.Visibility = Visibility.Collapsed;
        var dialog = new ContentDialog { FontFamily = MailTypography.Font, XamlRoot = layout.XamlRoot, Title = "欢迎使用邮件小秘书",
            PrimaryButtonText = "保存邮箱", CloseButtonText = "稍后填写",
            Content = new ScrollViewer { MaxHeight = 400, Content = Stack(presetChoice, address, host, Row(port, encryption), secret,
                Action("高级连接选项", () => { advanced.Visibility = advanced.Visibility == Visibility.Visible ? Visibility.Collapsed : Visibility.Visible; return Task.CompletedTask; }), advanced,
                Note("启用 IMAP，填写服务商要求的授权码或应用专用密码。OAuth2 填访问令牌，过期后手动更新。"), error) } };
        dialog.PrimaryButtonClick += async (_, e) =>
        {
            var deferral = e.GetDeferral();
            try {
                mailProvider.SelectedIndex = presetChoice.SelectedIndex;
                account.Text = address.Text; mailSecret.Password = secret.Password;
                mailHost.Text = host.Text; mailPort.Text = port.Text; mailUsername.Text = username.Text;
                mailFolder.Text = mailboxFolder.Text; mailSecurity.SelectedIndex = encryption.SelectedIndex;
                mailAuth.SelectedIndex = authentication.SelectedIndex;
                await SaveMail();
            }
            catch (Exception ex) { e.Cancel = true; error.Text = ex.Message; }
            finally { deferral.Complete(); }
        };
        var showing = dialog.ShowAsync();
        if (testing)
        {
            await Task.Delay(400);
            if (!dialog.IsLoaded) throw new InvalidOperationException("First-run account dialog did not render");
            presetChoice.SelectedIndex = mailPresets.FindIndex(p => p.GetProperty("id").GetString() == "custom");
            host.Text = "imap.first-run.example.invalid"; port.Text = "1993";
            if (presetChoice.SelectedIndex < 0 || !host.IsLoaded || !port.IsLoaded ||
                host.Text != "imap.first-run.example.invalid")
                throw new InvalidOperationException("First-run custom mailbox configuration unavailable");
            Program.Trace("Passed: First-run provider picker includes custom IMAP and editable server/port");
            dialog.Hide();
        }
        await showing;
        // Return through the dispatcher after the native dialog callback unwinds.
        await Task.Yield();
    }
    async Task ReloadMailboxes()
    {
        var config = await bridge.Call("config");
        loadingMailboxes = true;
        try {
            mailboxProfiles.Clear(); savedMailboxes.Items.Clear();
            string Text(string key) => config.TryGetProperty(key, out var value) ? value.GetString() ?? "" : "";
            var selected = -1;
            foreach (var profile in config.GetProperty("mailboxes").EnumerateArray()) {
                var index = mailboxProfiles.Count; mailboxProfiles.Add(profile.Clone());
                var enabled = !profile.TryGetProperty("monitor_enabled", out var flag) || flag.GetBoolean();
                var mailboxFolder = profile.TryGetProperty("mail_folder", out var mf) ? mf.GetString() : "INBOX";
                savedMailboxes.Items.Add(profile.GetProperty("account").GetString() + " · " + mailboxFolder + (enabled ? " · 已启用" : " · 已暂停"));
                if (profile.GetProperty("id").GetString() == Text("selected_mailbox_id")) selected = index;
            }
            savedMailboxes.SelectedIndex = selected;
            harnessPath.Text = Text("harness_path"); account.Text = Text("account"); mailSecret.Password = "";
            var preset = Text("mail_provider");
            mailProvider.SelectedIndex = mailPresets.FindIndex(p => p.GetProperty("id").GetString() == (preset.Length == 0 ? "163" : preset));
            mailHost.Text = Text("host").Length == 0 ? "imap.163.com" : Text("host");
            mailPort.Text = config.TryGetProperty("port", out var port) ? port.ToString() : "993";
            mailUsername.Text = Text("username"); mailFolder.Text = Text("mail_folder").Length == 0 ? "INBOX" : Text("mail_folder");
            mailSecurity.SelectedIndex = Text("security") == "starttls" ? 1 : 0;
            mailAuth.SelectedIndex = Text("mail_auth") == "oauth2" ? 1 : 0;
        }
        finally { loadingMailboxes = false; }
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
        void Check(bool ok, string label) {
            if (!ok) throw new InvalidOperationException(label);
            checks.Add(label); Program.Trace("Passed: " + label);
        }
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
            Check(mailPresets.Count >= 10 && mailPresets.Exists(p => p.GetProperty("id").GetString() == "custom"),
                "Common mailbox presets and custom IMAP available through bundled bridge");
            Check(savedMailboxes.Items.Count == 2, "Multiple saved accounts populate the native mailbox picker");
            savedMailboxes.SelectedIndex = 1;
            var switchDeadline = DateTime.UtcNow.AddSeconds(3);
            while (account.Text != "second@example.invalid" && DateTime.UtcNow < switchDeadline) await Task.Delay(25);
            Check(account.Text == "second@example.invalid" && mailHost.Text == "imap.second.invalid",
                "Selecting a different saved mailbox loads its own connection without overwriting the other account");
            var savedPreset = mailProvider.SelectedIndex;
            mailProvider.SelectedIndex = mailPresets.FindIndex(p => p.GetProperty("id").GetString() == "qq");
            Check(mailHost.Text == "imap.qq.com" && mailPort.Text == "993", "QQ preset fills editable TLS server settings");
            mailProvider.SelectedIndex = mailPresets.FindIndex(p => p.GetProperty("id").GetString() == "custom");
            mailHost.Text = "imap.example.invalid"; mailPort.Text = "1993";
            mailUsername.Text = "synthetic-login"; mailFolder.Text = "Archive";
            mailSecurity.SelectedIndex = 1; mailAuth.SelectedIndex = 1;
            Check(mailHost.Text == "imap.example.invalid" && mailPort.Text == "1993" && mailFolder.Text == "Archive",
                "Custom host port encryption login username folder and OAuth2 controls accept configuration");
            mailProvider.SelectedIndex = savedPreset;
            mailUsername.Text = ""; mailFolder.Text = "INBOX"; mailSecurity.SelectedIndex = 0; mailAuth.SelectedIndex = 0;
            Check(pageTitle.FontFamily.Source == MailTypography.FontStack &&
                preview.FontFamily.Source == MailTypography.FontStack && account.FontFamily.Source == MailTypography.FontStack,
                "Windows UI font stack applied to headings, controls and report text");
            Check(Forms.SystemInformation.IsFontSmoothingEnabled, "Font smoothing enabled on screenshot desktop");
            using (var installed = new System.Drawing.Text.InstalledFontCollection())
            {
                var families = new List<string>();
                foreach (var family in installed.Families) families.Add(family.Name);
                File.WriteAllText(Path.ChangeExtension(testResult!, ".typography.json"), JsonSerializer.Serialize(new
                {
                    font_stack = MailTypography.FontStack,
                    font_smoothing = Forms.SystemInformation.IsFontSmoothingEnabled,
                    rasterization_scale = layout.XamlRoot.RasterizationScale,
                    installed_families = families
                }, new JsonSerializerOptions { WriteIndented = true }));
            }
            var runtime = await bridge.Call("runtime_info");
            Check(!runtime.GetProperty("console_visible").GetBoolean(), "Packaged mail worker runs without a visible console window");
            Check(reports.Items.Count == 1, "Native WinUI 3 window receives synthetic reports through packaged worker");
            var report = (Report)((ListViewItem)reports.Items[0]).Tag;
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
            Check(navigation.ActualWidth > 150 && navigation.SelectedIndex == 0 && reportPage.Visibility == Visibility.Visible &&
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
            navigation.SelectedIndex = 1;
            await Task.Delay(400);
            layout.UpdateLayout();
            Check(Visible(mailSaveButton), "Mail save button visible without scrolling");
            if (screenArg >= 0)
            {
                var path = Program.Args[screenArg + 1];
                Capture(Path.Combine(Path.GetDirectoryName(path)!, Path.GetFileNameWithoutExtension(path) + "-mailbox.png"));
            }
            navigation.SelectedIndex = 2;
            await Task.Delay(400);
            layout.UpdateLayout();
            Check(Visible(aiSaveButton), "AI save button visible without scrolling");
            if (screenArg >= 0)
            {
                var path = Program.Args[screenArg + 1];
                Capture(Path.Combine(Path.GetDirectoryName(path)!, Path.GetFileNameWithoutExtension(path) + "-settings.png"));
            }
            navigation.SelectedIndex = 0;
            Program.Trace("Opening first-run dialog");
            await Onboard(true);
            checks.Add("First-run native account dialog renders");
            File.WriteAllText(testResult!, JsonSerializer.Serialize(new { ok = true, checks }, new JsonSerializerOptions { WriteIndented = true }));
        }
        catch (Exception e) { File.WriteAllText(testResult!, JsonSerializer.Serialize(new { ok = false, checks, error = e.ToString() })); }
        finally { await Exit(); if (fixture != null) Directory.Delete(fixture, true); }
    }
}

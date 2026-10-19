using System.Linq;
using System;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Windows.Graphics;

namespace BensonMail;

sealed class UninstallWindow : Window
{
    readonly Grid root = new() { Padding = new Thickness(28, 12, 28, 24), RowSpacing = 20 };
    readonly ToggleSwitch preserve = new() { Header = L.T("保留配置"), OnContent = "", OffContent = "" };
    readonly ToggleSwitch keepReports = new() { Header = L.T("保留邮件报告"), OnContent = "", OffContent = "" };
    readonly TextBlock detail = Text(L.T("正在读取卸载信息…"));
    readonly TextBlock locations = Text("");
    readonly TextBlock reports = Text("");
    readonly TextBlock progress = Text(L.T("正在准备…"));
    readonly Button remove = new() { Content = L.T("卸载"), MinWidth = 110 };
    readonly Button close = new() { Content = L.T("取消"), MinWidth = 110 };
    readonly string target;
    readonly string? fixtureResult = Argument("--fixture-result") ?? Argument("--e2e-test");
    readonly string? uiResult = Argument("--uninstall-ui-test");
    readonly bool staged = Argument("--uninstall-worker") != null;
    bool busy;
    bool finished;
    bool loaded;
    string data = "";
    string reportDirectory = "";
    static string? Argument(string key)
    {
        var index = Array.IndexOf(Program.Args, key);
        return index >= 0 && index + 1 < Program.Args.Length ? Program.Args[index + 1] : null;
    }
    static TextBlock Text(string value) => new() { Text = value, FontFamily = MailTypography.Font,
        TextWrapping = TextWrapping.Wrap, IsTextSelectionEnabled = true };
    static StackPanel Stack(params UIElement[] children)
    {
        var stack = new StackPanel { Spacing = 12 };
        foreach (var child in children) stack.Children.Add(child);
        return stack;
    }
    static Border Card(UIElement content)
    {
        var card = new Border { Child = content, Padding = new Thickness(20), CornerRadius = new CornerRadius(8),
            BorderThickness = new Thickness(1) };
        void Colors()
        {
            var dark = card.ActualTheme == ElementTheme.Dark;
            card.Background = new SolidColorBrush(Windows.UI.Color.FromArgb(dark ? (byte)13 : (byte)179, 255, 255, 255));
            card.BorderBrush = new SolidColorBrush(Windows.UI.Color.FromArgb(dark ? (byte)25 : (byte)15, 0, 0, 0));
        }
        card.Loaded += (_, _) => Colors(); card.ActualThemeChanged += (_, _) => Colors();
        return card;
    }
    // Stage before WinUI creates any window. The temporary process owns the
    // only visible window for confirmation, progress and completion.
    internal static bool StageBeforeWindow()
    {
        if (Argument("--uninstall-worker") != null || Argument("--uninstall-ui-test") != null) return false;
        var start = new ProcessStartInfo(Path.Combine(AppContext.BaseDirectory, "MailWorker.exe")) {
            UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true,
            RedirectStandardError = true, StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8, WorkingDirectory = Path.GetTempPath()
        };
        foreach (var value in new[] { "--uninstall-native", "prepare", "--target", AppContext.BaseDirectory,
            "--executable", Path.GetFileName(Environment.ProcessPath!) }) start.ArgumentList.Add(value);
        var fixture = Argument("--fixture-result") ?? Argument("--e2e-test");
        if (fixture != null) { start.ArgumentList.Add("--fixture-result"); start.ArgumentList.Add(fixture); }
        using var worker = Process.Start(start) ?? throw new IOException(L.T("无法启动卸载组件。"));
        var output = worker.StandardOutput.ReadToEndAsync();
        var errors = worker.StandardError.ReadToEndAsync();
        if (!worker.WaitForExit(120000)) {
            try { worker.Kill(entireProcessTree: true); } catch { }
            throw new TimeoutException(L.T("卸载组件未能完成，请关闭占用文件的程序后重试。"));
        }
        var stderr = errors.GetAwaiter().GetResult().Trim();
        string? helperPath = null; string? failure = null;
        foreach (var line in output.GetAwaiter().GetResult().Split('\n', StringSplitOptions.RemoveEmptyEntries)) {
            using var message = JsonDocument.Parse(line);
            if (message.RootElement.TryGetProperty("result", out var result)) helperPath = result.GetProperty("helper").GetString();
            if (message.RootElement.TryGetProperty("error", out var error)) failure = error.GetString();
        }
        if (worker.ExitCode != 0 || helperPath == null)
            throw new IOException(failure ?? (stderr.Length > 0 ? stderr[..Math.Min(stderr.Length, 1600)] : L.T("无法启动卸载组件。")));
        var helper = new ProcessStartInfo(helperPath) { UseShellExecute = false, CreateNoWindow = true,
            WorkingDirectory = Path.GetTempPath() };
        foreach (var value in Program.Args) helper.ArgumentList.Add(value);
        helper.ArgumentList.Add("--uninstall-worker"); helper.ArgumentList.Add(AppContext.BaseDirectory);
        helper.ArgumentList.Add("--parent-pid"); helper.ArgumentList.Add(Environment.ProcessId.ToString());
        using var process = Process.Start(helper) ?? throw new IOException(L.T("无法启动卸载组件。"));
        return true;
    }
    readonly int visibleProcess = Environment.ProcessId;
    long visibleWindow;
    public UninstallWindow()
    {
        Program.Trace("Uninstall window constructor");
        target = Path.GetFullPath(Argument("--uninstall-worker") ?? AppContext.BaseDirectory);
        Title = L.T("卸载邮件小秘书");
        AppWindow.SetIcon(Path.Combine(AppContext.BaseDirectory, "assets", "mail.ico"));
        SystemBackdrop = new MicaBackdrop();
        var area = DisplayArea.GetFromWindowId(AppWindow.Id, DisplayAreaFallback.Primary).WorkArea;
        var width = Math.Min(820, area.Width - 40); var height = Math.Min(780, area.Height - 40);
        AppWindow.Resize(new SizeInt32(width, height));
        AppWindow.Move(new PointInt32(area.X + Math.Max(0, (area.Width - width) / 2),
                                     area.Y + Math.Max(0, (area.Height - height) / 2)));
        var caption = new Grid { Height = 40, Background = new SolidColorBrush(Microsoft.UI.Colors.Transparent) };
        caption.Children.Add(new TextBlock { Text = L.T("邮件小秘书"), FontFamily = MailTypography.Font, FontSize = 12,
            Margin = new Thickness(0, 0, 150, 0), VerticalAlignment = VerticalAlignment.Center });
        if (AppWindowTitleBar.IsCustomizationSupported())
        {
            ExtendsContentIntoTitleBar = true; SetTitleBar(caption);
            AppWindow.TitleBar.ButtonBackgroundColor = Microsoft.UI.Colors.Transparent;
            AppWindow.TitleBar.ButtonInactiveBackgroundColor = Microsoft.UI.Colors.Transparent;
        }
        root.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        root.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) });
        root.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        root.Children.Add(caption);
        var heading = Text(L.T("卸载邮件小秘书")); heading.FontSize = 28; heading.FontWeight = Microsoft.UI.Text.FontWeights.SemiBold;
        var subheading = Text(L.T("若邮件小秘书正在运行，点击卸载后会询问是否退出；确认退出后再继续。"));
        subheading.Opacity = .7;
        preserve.FontFamily = keepReports.FontFamily = MailTypography.Font;
        preserve.IsOn = Array.IndexOf(Program.Args, "--keep-configuration") >= 0;
        keepReports.IsOn = Array.IndexOf(Program.Args, "--delete-reports") < 0;
        var configNote = Text(L.T("保留账号列表、服务器、AI 设置及加密密钥，供本机同一 Windows 用户重装后继续使用。"));
        configNote.Opacity = .7; configNote.FontSize = 12;
        var cacheNote = Text(L.T("缓存和收信进度会清除，重装后重新记录收信起点。自启动项及本次安装的快捷方式会移除。"));
        cacheNote.Opacity = .7; cacheNote.FontSize = 12;
        reports.FontSize = 12; reports.Opacity = .7; locations.FontSize = 12; locations.Opacity = .7;
        var content = Stack(heading, subheading, Card(Stack(preserve, Text(L.T("开启＝保留；关闭＝删除。")), configNote, cacheNote)),
            Card(Stack(keepReports, Text(L.T("开启＝保留；关闭＝删除。")), reports)), locations, detail, progress);
        var scroll = new ScrollViewer { Content = content, VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
            HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled };
        Grid.SetRow(scroll, 1); root.Children.Add(scroll);
        remove.FontFamily = close.FontFamily = MailTypography.Font;
        remove.Style = (Style)Application.Current.Resources["AccentButtonStyle"];
        var actions = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 10,
            HorizontalAlignment = HorizontalAlignment.Right };
        actions.Children.Add(remove); actions.Children.Add(close); Grid.SetRow(actions, 2); root.Children.Add(actions);
        L.Apply(root);
        Content = root;
        Program.Trace("Uninstall controls created");
        remove.IsEnabled = false;
        remove.Click += async (_, _) => { if (finished) Finish(); else await Start(); };
        close.Click += (_, _) => Finish();
        AppWindow.Closing += (_, e) => { if (busy) e.Cancel = true; else RemoveHelperOnExit(); };
        root.Loaded += async (_, _) => await Initialize();
    }
    ProcessStartInfo Worker(string operation)
    {
        var start = new ProcessStartInfo(Path.Combine(AppContext.BaseDirectory, "MailWorker.exe")) {
            UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true, RedirectStandardError = true,
            StandardOutputEncoding = Encoding.UTF8, StandardErrorEncoding = Encoding.UTF8,
            WorkingDirectory = AppContext.BaseDirectory
        };
        start.ArgumentList.Add("--uninstall-native"); start.ArgumentList.Add(operation);
        if (operation == "remove-helper") return start;
        start.ArgumentList.Add("--target"); start.ArgumentList.Add(target);
        if (fixtureResult != null) { start.ArgumentList.Add("--fixture-result"); start.ArgumentList.Add(fixtureResult); }
        if (preserve.IsOn == true) start.ArgumentList.Add("--keep-configuration");
        if (keepReports.IsOn != true) start.ArgumentList.Add("--delete-reports");
        return start;
    }
    async Task<JsonElement> RunWorker(ProcessStartInfo start)
    {
        using var process = Process.Start(start) ?? throw new IOException(L.T("无法启动卸载组件。"));
        var errors = process.StandardError.ReadToEndAsync();
        JsonElement result = default;
        string? failure = null;
        while (await process.StandardOutput.ReadLineAsync() is string line)
        {
            using var message = JsonDocument.Parse(line);
            if (message.RootElement.TryGetProperty("progress", out var text)) detail.Text = L.T(text.GetString());
            if (message.RootElement.TryGetProperty("result", out var value)) result = value.Clone();
            if (message.RootElement.TryGetProperty("error", out var error)) failure = error.GetString();
        }
        await process.WaitForExitAsync(); await errors;
        if (process.ExitCode != 0 || failure != null || result.ValueKind == JsonValueKind.Undefined)
            throw new IOException(failure ?? L.T("卸载组件未能完成，请关闭占用文件的程序后重试。"));
        return result;
    }
    async Task Initialize()
    {
        if (loaded) return; loaded = true;
        Program.Trace("Uninstall layout loaded");
        try {
            if (uiResult != null) {
                locations.Text = L.T("程序目录：模拟安装目录"); reports.Text = L.T("报告默认保留；关闭“保留邮件报告”才会删除可识别的报告及索引。");
                reportDirectory = @"C:\Synthetic-Mail-Reports";
                detail.Text = L.T("卸载会通过独立组件执行，进度显示在此处。");
                progress.Text = L.T("准备就绪"); remove.IsEnabled = true;
                await Task.Delay(500);
                if (AppWindow.Presenter is not OverlappedPresenter { State: OverlappedPresenterState.Maximized })
                    throw new InvalidOperationException("Uninstaller must start maximized with the standard window presenter");
                Program.Trace("Uninstall UI test capture");
                var bounds = AppWindow.Position; var size = AppWindow.Size;
                using var image = new System.Drawing.Bitmap(size.Width, size.Height);
                using var graphics = System.Drawing.Graphics.FromImage(image);
                graphics.CopyFromScreen(bounds.X, bounds.Y, 0, 0, image.Size);
                image.Save(Path.ChangeExtension(uiResult, ".png"), System.Drawing.Imaging.ImageFormat.Png);
                if (!preserve.IsLoaded || !keepReports.IsLoaded || preserve.IsOn == true || keepReports.IsOn != true)
                    throw new InvalidOperationException("Uninstall options did not render with safe defaults");
                keepReports.IsOn = false;
                if (!Worker("prepare").ArgumentList.Contains("--delete-reports")) throw new InvalidOperationException("Report retention off must request deletion");
                var exitCalls = 0;
                foreach (var refusal in new[] { ContentDialogResult.Secondary, ContentDialogResult.None }) {
                    if (await StopRunningApplication(() => true, () => { exitCalls++; return Task.CompletedTask; }, dialog => Task.FromResult(refusal)))
                        throw new InvalidOperationException("Declined process exit continued uninstall");
                }
                if (exitCalls != 0 || busy) throw new InvalidOperationException("Exit refusal changed application state");
                if (!await StopRunningApplication(() => true, () => { exitCalls++; return Task.CompletedTask; }, dialog => Task.FromResult(ContentDialogResult.Primary)) || exitCalls != 1)
                    throw new InvalidOperationException("Accepted process exit did not complete before uninstall");
                var confirmations = 0;
                if (await ConfirmUninstall(async dialog => {
                    if (++confirmations == 1) return ContentDialogResult.Primary;
                    if (!dialog.Content.ToString()!.Contains(reportDirectory)) throw new InvalidOperationException("Report confirmation missing directory");
                    var showing = dialog.ShowAsync(); await Task.Delay(250);
                    if (!dialog.IsLoaded || dialog.DefaultButton != ContentDialogButton.Close) throw new InvalidOperationException("Destructive confirmation must render with cancel default");
                    dialog.Hide(); await showing; return ContentDialogResult.None;
                })) throw new InvalidOperationException("Cancel accepted deletion");
                if (busy || confirmations != 2) throw new InvalidOperationException("Report cancellation did not stop before uninstall");
                if (!await ConfirmUninstall(dialog => Task.FromResult(ContentDialogResult.Primary))) throw new InvalidOperationException("Explicit confirmation rejected");
                keepReports.IsOn = true;
                if (Worker("prepare").ArgumentList.Contains("--delete-reports")) throw new InvalidOperationException("Report retention on must preserve reports");
                if (preserve.OnContent?.ToString() != "" || preserve.OffContent?.ToString() != "" || keepReports.OnContent?.ToString() != "" || keepReports.OffContent?.ToString() != "") throw new InvalidOperationException("Retention switch labels must stay fixed");
                File.WriteAllText(uiResult, JsonSerializer.Serialize(new { ok = true, checks = new[] {
                    "Uninstaller starts maximized with the standard window presenter",
                    "Native WinUI 3 uninstaller rendered with Mica backdrop and Fluent cards",
                    "Running-app prompt supports Yes/No/Cancel; refusal does not exit or uninstall, acceptance awaits graceful exit before confirmations",
                    "Optional mailbox and AI configuration retention visible",
                    "Report retention defaults on; off maps to deletion and on preserves reports",
                    "Fixed switch labels, report-directory confirmation, explicit accept and safe cancellation; no real data accessed"
                }}));
                Finish(); return;
            }
            var info = await RunWorker(Worker("info"));
            data = info.GetProperty("data").GetString() ?? "";
            locations.Text = L.T("程序目录：") + target + L.T("\n数据目录：") + data;
            reportDirectory = info.GetProperty("reports").GetString() is string r && r.Length > 0 ? r : L.T("未配置");
            reports.Text = L.T("报告目录：") + reportDirectory
                + L.T("\n仅删除可识别的报告和邮件索引，保留其他文件及自选根目录。");
            progress.Text = L.T("准备就绪"); remove.IsEnabled = true;
            detail.Text = L.T("准备就绪。可选择保留配置，方便下次安装。");
            visibleWindow = WinRT.Interop.WindowNative.GetWindowHandle(this).ToInt64();
            if (fixtureResult != null) { await Task.Delay(500); await Start(); }
        }
        catch (Exception error) { Failed(error); }
    }
    void SetBusy()
    {
        busy = true; remove.IsEnabled = close.IsEnabled = preserve.IsEnabled = keepReports.IsEnabled = false;
        progress.Text = L.T("处理中，请稍候…");
    }
    async Task<bool> ConfirmUninstall(Func<ContentDialog, Task<ContentDialogResult>>? show = null)
    {
        async Task<bool> Accept(ContentDialog dialog) =>
            (show == null ? await dialog.ShowAsync() : await show(dialog)) == ContentDialogResult.Primary;
        var dialog = new ContentDialog { XamlRoot = root.XamlRoot, Title = L.T("确认卸载？"),
            Content = (preserve.IsOn == true ? L.T("保留邮箱及 AI 配置，移除程序和缓存。") : L.T("移除程序、配置、加密密钥和缓存。"))
                + (keepReports.IsOn == true ? L.T("\n已生成的邮件报告保留。") : L.T("\n同时删除已选的邮件报告。")),
            PrimaryButtonText = L.T("卸载"), CloseButtonText = L.T("取消"), DefaultButton = ContentDialogButton.Close };
        if (!await Accept(dialog)) return false;
        if (keepReports.IsOn == true) return true;
        var reportDialog = new ContentDialog { XamlRoot = root.XamlRoot, Title = L.T("确认删除邮件报告？"),
            Content = L.T("将删除以下目录中本软件可识别的邮件报告及索引：\n") + reportDirectory
                + L.T("\n其他文件及自选根目录会保留。此操作无法撤销。"),
            PrimaryButtonText = L.T("删除报告并卸载"), CloseButtonText = L.T("取消"), DefaultButton = ContentDialogButton.Close };
        return await Accept(reportDialog);
    }
    async Task<bool> StopRunningApplication(Func<bool>? running = null, Func<Task>? stop = null,
        Func<ContentDialog, Task<ContentDialogResult>>? show = null)
    {
        using var process = running == null ? AppLifetime.FindRunning(target) : null;
        if (!(running?.Invoke() ?? process != null)) return true;
        var dialog = new ContentDialog { XamlRoot = root.XamlRoot, Title = L.T("检测到邮件小秘书正在运行，是否退出？"),
            Content = L.T("将先停止邮箱监听并退出程序，再继续卸载确认。选择“否”或“取消”不会卸载。"),
            PrimaryButtonText = L.T("是，退出并继续"), SecondaryButtonText = L.T("否"), CloseButtonText = L.T("取消"),
            DefaultButton = ContentDialogButton.Close };
        var choice = show == null ? await dialog.ShowAsync() : await show(dialog);
        if (choice != ContentDialogResult.Primary) return false;
        remove.IsEnabled = false;
        progress.Text = L.T("正在等待邮件小秘书退出…");
        try { if (stop != null) await stop(); else await AppLifetime.RequestExit(target, process!); }
        finally { remove.IsEnabled = true; progress.Text = L.T("准备就绪"); }
        return true;
    }
    bool starting;
    async Task Start()
    {
        if (starting) return;
        starting = true;
        try {
            if (!await StopRunningApplication()) return;
            if (fixtureResult == null && !await ConfirmUninstall()) return;
            SetBusy();
            if (!staged) throw new InvalidOperationException("Uninstall window must be staged before it is shown");
            await Cleanup();
        }
        catch (Exception error) { Failed(error); }
        finally { starting = false; }
    }
    async Task Cleanup()
    {
        try {
            SetBusy();
            var start = Worker("cleanup"); start.ArgumentList.Add("--parent-pid");
            start.ArgumentList.Add(Argument("--parent-pid") ?? "0");
            await RunWorker(start);
            if (Environment.ProcessId != visibleProcess || WinRT.Interop.WindowNative.GetWindowHandle(this).ToInt64() != visibleWindow)
                throw new InvalidOperationException("Uninstall window changed during cleanup");
            busy = false; finished = true; progress.Text = L.T("已完成");
            detail.Text = preserve.IsOn == true ? L.T("卸载完成。邮箱及 AI 配置已保留，下次重装可继续使用。") : L.T("卸载完成。程序、配置、加密密钥和缓存已清理。");
            remove.Content = L.T("完成"); remove.IsEnabled = true; close.Visibility = Visibility.Collapsed;
            WriteFixture(true, null);
            if (fixtureResult != null) { await Task.Delay(150); Finish(); }
        }
        catch (Exception error) { Failed(error); }
    }
    void Failed(Exception error)
    {
        busy = false; finished = true; progress.Text = L.T("未能完成");
        detail.Text = L.T("卸载未完成：") + L.T(error.Message);
        remove.Content = L.Code == "en" ? "Close" : "关闭"; remove.IsEnabled = true; close.Visibility = Visibility.Collapsed;
        WriteFixture(false, error.Message);
        if (uiResult != null) { File.WriteAllText(uiResult, JsonSerializer.Serialize(new { ok = false, error = error.ToString() })); Finish(); }
        else if (fixtureResult != null) Finish();
    }
    void WriteFixture(bool ok, string? error)
    {
        if (fixtureResult != null)
            File.WriteAllText(fixtureResult, JsonSerializer.Serialize(new { ok, detail = error,
                helper = Path.GetFullPath(AppContext.BaseDirectory), target, data,
                initialProcess = visibleProcess, finalProcess = Environment.ProcessId,
                initialWindow = visibleWindow, finalWindow = WinRT.Interop.WindowNative.GetWindowHandle(this).ToInt64(),
                checks = new[] { "independent helper outside program directory", "responsive native WinUI 3 GUI", "same visible window and process from ready through completion",
                    preserve.IsOn == true ? "encrypted configuration retained and cache removed" : "full installation and user data cleanup" } }));
    }
    bool removingHelper;
    void RemoveHelperOnExit()
    {
        if (!staged || removingHelper) return;
        removingHelper = true;
        try { using var process = Process.Start(Worker("remove-helper")); } catch { }
    }
    void Finish()
    {
        if (busy) return;
        RemoveHelperOnExit();
        Application.Current.Exit();
    }
}

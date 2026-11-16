using System;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace BensonMail;

sealed partial class MainWindow
{
    DateTime? lastCheckAt;
    void ConfigureTrayCommands()
    {
        var state = new NativeTray.Command("", () => { }) { Enabled = false };
        var last = new NativeTray.Command("", () => { }) { Enabled = false };
        var frequency = new NativeTray.Command("", () => { }) { Enabled = false };
        var notifications = new NativeTray.Command("", () => DispatcherQueue.TryEnqueue(async () =>
            await Guard(() => SaveNotificationPreferences(!notificationsEnabled))));
        tray.Commands.AddRange(new[] { state, last, frequency,
            new NativeTray.Command(L.T("打开窗口"), () => DispatcherQueue.TryEnqueue(Restore)),
            new NativeTray.Command(L.T("开始／暂停监听"), () => DispatcherQueue.TryEnqueue(async () => await Guard(ToggleService))),
            notifications,
            new NativeTray.Command(L.T("立即检查"), () => DispatcherQueue.TryEnqueue(async () => { if (!check.IsEnabled) return; check.IsEnabled = false; await Guard(async () => { try { await Call("check"); } catch { check.IsEnabled = true; throw; } }); })),
            new NativeTray.Command(L.T("打开报告文件夹"), () => DispatcherQueue.TryEnqueue(async () => await Guard(OpenReportFolder))),
            new NativeTray.Command(L.T("打开最新报告"), () => DispatcherQueue.TryEnqueue(async () => await Guard(OpenLatestReport))),
            new NativeTray.Command(L.T("通用设置"), () => DispatcherQueue.TryEnqueue(async () => { Restore(); await Guard(() => NavigateSettings(3)); })),
            new NativeTray.Command(L.T("退出邮件小秘书"), () => DispatcherQueue.TryEnqueue(async () => await Exit())) });
        tray.MenuOpening += () => {
            state.Text = status.Text;
            last.Text = L.T("最近检查：") + (lastCheckAt?.ToString("HH:mm:ss") ?? L.T("尚未检查"));
            frequency.Text = L.T("自定义间隔（秒）") + ": " + interval.Text;
            notifications.Text = L.T(notificationsEnabled ? "暂停系统通知" : "恢复系统通知");
            tray.Commands[6].Enabled = check.IsEnabled;
        };
    }
    async Task OpenReportFolder()
    {
        var config = await bridge.Call("config");
        var path = JsonText(config, "output_dir"); System.IO.Directory.CreateDirectory(path); Open(path);
    }
    async Task OpenLatestReport()
    {
        var rows = await bridge.Call("reports", new { });
        var latest = rows.EnumerateArray().FirstOrDefault();
        if (latest.ValueKind == JsonValueKind.Object) Open(JsonText(latest, "path"));
        else detail.Text = L.Bootstrap("尚无报告。", "No reports yet.", "Todavía no hay informes.");
    }
    Button KnownSenderButton()
    {
        var menu = new MenuFlyout();
        var button = new Button { Content = L.Bootstrap("选择已有发件人", "Choose a known sender", "Elegir remitente conocido"), Flyout = menu };
        menu.Opening += async (_, _) => {
            try {
                var rows = await bridge.Call("reports", new { });
                menu.Items.Clear();
                var all = new MenuFlyoutItem { Text = L.T("全部") }; all.Click += (_, _) => sender.Text = ""; menu.Items.Add(all);
                foreach (var name in rows.EnumerateArray().Select(row => JsonText(row, "sender"))
                    .Where(value => !string.IsNullOrWhiteSpace(value)).Distinct(StringComparer.OrdinalIgnoreCase).OrderBy(value => value)) {
                    var item = new MenuFlyoutItem { Text = name }; item.Click += (_, _) => sender.Text = name; menu.Items.Add(item);
                }
            } catch (Exception error) { detail.Text = error.Message; }
        };
        return button;
    }
    async Task ShowRuntimeLog()
    {
        var result = await bridge.Call("runtime_log");
        var text = JsonText(result, "text");
        if (string.IsNullOrWhiteSpace(text)) text = L.Bootstrap("暂无运行记录。", "No runtime records yet.", "Todavía no hay registros.");
        await new ContentDialog { XamlRoot = layout.XamlRoot, Title = L.T("运行记录"),
            Content = Scroll(new TextBlock { Text = text, IsTextSelectionEnabled = true, TextWrapping = TextWrapping.Wrap }),
            CloseButtonText = L.T("关闭"), MinWidth = 420, MaxWidth = 900 }.ShowAsync();
    }
}

using System;
using System.IO;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace BensonMail;

sealed partial class MainWindow
{
    async Task UpdateRecoverySelfTest(Action<bool, string> check)
    {
        check(updateFallbackButton.Visibility == Visibility.Collapsed,
            "GitHub update recovery starts hidden");
        SetUpdateCheckStatus("Synthetic offline check failed", failed: true);
        check(updateFallbackButton.Visibility == Visibility.Visible && updateStatus.Text.Contains("offline"),
            "Failed update checks expose GitHub recovery alongside the error");
        SetUpdateCheckStatus("Synthetic check started");
        check(updateFallbackButton.Visibility == Visibility.Collapsed,
            "Starting the next update check hides the previous failure recovery");
        SetUpdateCheckStatus("Synthetic offline check failed", failed: true);
        SetUpdateCheckStatus("Synthetic latest version");
        check(updateFallbackButton.Visibility == Visibility.Collapsed,
            "Successful update checks clear failure recovery");
        check(UpdateClient.LatestReleaseUrl == "https://github.com/Benson-YiYan/benson-mail-assistant/releases/latest",
            "Update recovery targets the canonical latest release without opening a browser");

        var previousPacks = Environment.GetEnvironmentVariable("BENSON_MAIL_TEST_LANGUAGE_PACKS");
        var previousLanguage = L.Code;
        var packFolder = Path.Combine(fixture!, "legacy-update-language-packs");
        Directory.CreateDirectory(packFolder);
        try {
            // Deliberately incomplete legacy packs omit the new recovery label.
            foreach (var code in new[] { "en", "es" })
                File.WriteAllText(Path.Combine(packFolder, code + ".json"), JsonSerializer.Serialize(new {
                    schema_version = 1, language = code, platform = "windows",
                    exact = new System.Collections.Generic.Dictionary<string, string> { ["邮件小秘书"] = "Legacy app label" },
                    templates = Array.Empty<object>(), guides = new { mail_account = "Synthetic guide" }
                }));
            Environment.SetEnvironmentVariable("BENSON_MAIL_TEST_LANGUAGE_PACKS", packFolder);
            check(L.Select("en") && L.T("前往 GitHub 下载最新版") == "Download the latest version from GitHub",
                "Legacy English packs retain the built-in update recovery translation");
            check(L.T("屏蔽邮件") == "Blocked emails",
                "Legacy English language packs retain built-in sender policy labels");
            updateFallbackButton.Content = L.T("前往 GitHub 下载最新版");
            check(L.Select("es"), "Synthetic legacy Spanish pack loads");
            L.Apply(updateFallbackButton);
            check((string)updateFallbackButton.Content == "Descargar la última versión desde GitHub",
                "Legacy Spanish packs translate the existing recovery button when switching languages");
            check(L.T("屏蔽邮件") == "Correos bloqueados",
                "Legacy Spanish language packs retain built-in sender policy labels");
            // Run the real language-change handler over the existing settings cards,
            // report/chat controls and tray. Dictionary coverage alone misses stale UI.
            var chineseLabels = new[] { "管理邮箱", "邮箱连接", "检查频率", "选择您喜欢的 AI", "系统通知与免打扰", "历史邮件与诊断", "费用与用量" };
            bool HasText(UIElement? element, string text)
            {
                if (element == null || element == reports || element == savedMailboxes || element == chatMessages) return false;
                if (element is TextBlock label) return label.Text == text;
                if (element is Panel panel) { foreach (var child in panel.Children) if (HasText(child, text)) return true; }
                else if (element is Border border) return HasText(border.Child, text);
                else if (element is ScrollViewer scroll) return HasText(scroll.Content as UIElement, text);
                else if (element is ContentControl content) return HasText(content.Content as UIElement, text);
                return false;
            }
            foreach (var language in new[] { "zh", "en", "es", "zh", "es", "en", "zh" }) {
                await ChangeLanguage(language);
                foreach (var label in chineseLabels)
                    check(HasText(Content as UIElement, L.T(label)),
                        "Existing settings card refreshes to " + language + ": " + label);
                check(retryReport.Content?.ToString() == L.T("重新总结") &&
                    sendQuestion.Content?.ToString() == L.T("发送问题") &&
                    question.Header?.ToString() == L.T("对邮件提问") &&
                    notificationToggle.Content?.ToString() == L.T(notificationsEnabled ? "暂停系统通知" : "开启系统通知") &&
                    this.check.Content?.ToString() == L.T("立即检查"),
                    "Existing report/chat actions and check button refresh to " + language);
                check(updateFallbackButton.Content?.ToString() == L.T("前往 GitHub 下载最新版") &&
                    tray.Text == L.T("邮件小秘书") && account.Header?.ToString() == L.T("邮箱地址"),
                    "Existing recovery, tray and mailbox labels refresh to " + language);
            }
            var collision = new StackPanel();
            var start = new TextBlock { Text = "开始日期" };
            var from = new TextBlock { Text = "起始日期" };
            collision.Children.Add(start); collision.Children.Add(from);
            L.Apply(collision);
            foreach (var language in new[] { "en", "es", "zh" }) {
                L.Select(language); L.Apply(collision);
            }
            check(start.Text == "开始日期" && from.Text == "起始日期",
                "Labels sharing a foreign translation restore their individual Chinese sources");
            check(L.Select("en") && L.T("打开报告") == "Open report" &&
                L.T("安装程序未能启动，请重试。") == "Setup could not be started. Please retry.",
                "Legacy English packs retain report and updater controls from the current built-in catalog");
            check(L.Select("es") && L.T("打开报告") == "Abrir informe",
                "Legacy Spanish packs retain report controls from the current built-in catalog");
        }
        finally {
            Environment.SetEnvironmentVariable("BENSON_MAIL_TEST_LANGUAGE_PACKS", previousPacks);
            L.Select(previousLanguage);
            updateFallbackButton.Content = L.T("前往 GitHub 下载最新版");
            SetUpdateCheckStatus("");
        }
    }
}

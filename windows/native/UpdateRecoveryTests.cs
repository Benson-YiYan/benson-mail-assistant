using System;
using System.IO;
using System.Text.Json;
using Microsoft.UI.Xaml;

namespace BensonMail;

sealed partial class MainWindow
{
    void UpdateRecoverySelfTest(Action<bool, string> check)
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
        }
        finally {
            Environment.SetEnvironmentVariable("BENSON_MAIL_TEST_LANGUAGE_PACKS", previousPacks);
            L.Select(previousLanguage);
            updateFallbackButton.Content = L.T("前往 GitHub 下载最新版");
            SetUpdateCheckStatus("");
        }
    }
}

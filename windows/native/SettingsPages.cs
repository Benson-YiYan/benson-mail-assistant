using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace BensonMail;

sealed partial class MainWindow
{
    readonly Grid generalPage = new();
    readonly Dictionary<string, string> pageBaselines = new();
    readonly Dictionary<string, TextBlock> pageDirtyLabels = new();
    readonly Dictionary<string, ContentControl> settingsPageHosts = new();
    readonly ToggleSwitch notificationsSetting = new() { Header = L.T("系统通知"), OnContent = L.T("开启"), OffContent = L.T("关闭") };
    readonly TextBox inputRate = new() { Header = L.T("每百万输入 Token 价格"), Text = "0" };
    readonly TextBox outputRate = new() { Header = L.T("每百万输出 Token 价格"), Text = "0" };
    readonly TextBox rateCurrency = new() { Header = L.T("币种"), Text = "USD", MaxLength = 3 };
    readonly TextBox codexPath = new() { Header = L.T("Codex 启动器"), PlaceholderText = L.T("留空使用已保存的 Codex 启动器") };
    bool loadingSettingsDrafts;
    bool navigatingSettings;
    Func<ContentDialog, Task<ContentDialogResult>>? settingsLeaveFixture;
    int currentPageIndex;
    bool appliedQuietEnabled;
    string appliedQuietStart = "22:00", appliedQuietEnd = "08:00";

    static string PageKey(int index) => index == 1 ? "mail" : index == 2 ? "ai" : index == 3 ? "general" : "";
    Dictionary<string, object?> SettingsValues(string page)
    {
        if (page == "mail") return new() {
            ["mailboxes"] = MailboxDraftValues(), ["selected_mailbox_id"] = SelectedMailboxDraftId,
            ["seconds"] = interval.Text,
            ["mail_policy"] = new { mode = senderPolicyMode.SelectedIndex == 1 ? "whitelist" : "blacklist", addresses = senderPolicyAddressValues.ToArray(), skip_spam = senderPolicySpam.IsOn }
        };
        if (page == "ai") return new() {
            ["ai_provider"] = provider.SelectedIndex == 1 ? "codex" : provider.SelectedIndex == 2 ? "deepseek_harness" : "api",
            ["api_base"] = apiBase.Text, ["api_model"] = model.Text, ["key"] = apiKey.Password, ["harness_path"] = harnessPath.Text,
            ["codex_path"] = codexPath.Text,
            ["rates"] = new { input_per_million = inputRate.Text, output_per_million = outputRate.Text, currency = rateCurrency.Text }
        };
        return new() { ["output_dir"] = folder.Text, ["notifications_enabled"] = notificationsSetting.IsOn,
            ["quiet_hours"] = new { enabled = quietEnabled.IsOn, start = quietStart.Text, end = quietEnd.Text },
            ["autostart"] = startup.IsOn, ["ui_language"] = languageChoice.SelectedIndex == 0 ? "zh" : languageChoice.SelectedIndex == 2 ? "es" : "en" };
    }
    bool SettingsDirty(string page) => page.Length > 0 && pageBaselines.TryGetValue(page, out var baseline) && baseline != JsonSerializer.Serialize(SettingsValues(page));
    void AcceptSettingsBaseline(string page)
    {
        pageBaselines[page] = JsonSerializer.Serialize(SettingsValues(page)); RefreshSettingsDirty();
    }
    void RefreshSettingsDirty()
    {
        if (loadingSettingsDrafts || changingLanguage) return;
        foreach (var pair in pageDirtyLabels) {
            pair.Value.Text = L.T("有未保存的设置");
            pair.Value.Visibility = SettingsDirty(pair.Key) ? Visibility.Visible : Visibility.Collapsed;
        }
    }
    StackPanel SettingsSaveBar(string page, Button save, params UIElement[] extra)
    {
        var dirty = new TextBlock { Text = L.T("有未保存的设置"), VerticalAlignment = VerticalAlignment.Center, Visibility = Visibility.Collapsed };
        pageDirtyLabels[page] = dirty;
        var row = Row(save, dirty); foreach (var child in extra) row.Children.Add(child); return row;
    }
    void BindSettingsDrafts()
    {
        foreach (var entry in new[] { ("mail", mailPage), ("ai", aiPage), ("general", generalPage) }) {
            var child = entry.Item2.Children[0]; entry.Item2.Children.Clear();
            var host = new ContentControl { Content = child, HorizontalContentAlignment = HorizontalAlignment.Stretch, VerticalContentAlignment = VerticalAlignment.Stretch, IsTabStop = false };
            settingsPageHosts[entry.Item1] = host; entry.Item2.Children.Add(host);
        }

        foreach (var field in new[] { account, mailHost, mailPort, mailUsername, mailFolder, folder, interval, mailProxy.Host, mailProxy.Port,
            apiBase, model, harnessPath, codexPath, inputRate, outputRate, rateCurrency, quietStart, quietEnd }) field.TextChanged += (_, _) => RefreshSettingsDirty();
        mailSecret.PasswordChanged += (_, _) => RefreshSettingsDirty(); apiKey.PasswordChanged += (_, _) => RefreshSettingsDirty();
        foreach (var combo in new[] { mailProvider, mailSecurity, mailAuth, mailProxy.Mode, provider, senderPolicyMode, languageChoice })
            combo.SelectionChanged += (_, _) => RefreshSettingsDirty();
        foreach (var toggle in new[] { startup, notificationsSetting, quietEnabled, senderPolicySpam }) toggle.Toggled += (_, _) => RefreshSettingsDirty();
    }
    async Task LoadPageDraft(string page)
    {
        loadingSettingsDrafts = true;
        try {
            var config = await bridge.Call("config");
            if (page == "mail") {
                await ReloadMailboxes(); ResetMailboxDrafts(); await LoadSenderPolicy();
                folder.Text = JsonText(config, "output_dir"); interval.Text = JsonText(config, "interval", "60"); mailSecret.Password = "";
            }
            else if (page == "ai") {
                provider.SelectedIndex = JsonText(config, "ai_provider") == "codex" ? 1 : JsonText(config, "ai_provider") == "deepseek_harness" ? 2 : 0;
                apiBase.Text = JsonText(config, "api_base"); model.Text = JsonText(config, "api_model"); harnessPath.Text = JsonText(config, "harness_path");
                codexPath.Text = ""; apiKey.Password = "";
                var usage = await Assistant("usage");
                if (usage.TryGetProperty("rates", out var rates)) { inputRate.Text = JsonText(rates, "input_per_million", "0"); outputRate.Text = JsonText(rates, "output_per_million", "0"); rateCurrency.Text = JsonText(rates, "currency", "USD"); }
            }
            else {
                LoadNotificationPreferences(config); folder.Text = JsonText(config, "output_dir");
                startup.IsOn = config.TryGetProperty("autostart", out var auto) && auto.GetBoolean();
                changingLanguage = true; languageChoice.SelectedIndex = L.Code == "zh" ? 0 : L.Code == "es" ? 2 : 1; changingLanguage = false;
            }
            AcceptSettingsBaseline(page);
        }
        finally { loadingSettingsDrafts = false; RefreshSettingsDirty(); }
    }
    async Task SaveSettingsPage(string page)
    {
        var host = settingsPageHosts[page];
        host.IsEnabled = false; navigation.IsEnabled = false;
        try {
            var values = SettingsValues(page);
            if (page == "general") {
                await bridge.Call("validate_settings_page", new { page, values });
                var code = languageChoice.SelectedIndex == 0 ? "zh" : languageChoice.SelectedIndex == 2 ? "es" : "en";
                if (!await EnsureLanguage(code)) return;
            }
            await Call("save_settings_page", new { page, values });
            if (page == "general") await ChangeLanguage(values["ui_language"]?.ToString() ?? "en", persist: false);
            await LoadPageDraft(page);
            detail.Text = L.T("本页设置已保存。");
        }
        finally { host.IsEnabled = true; navigation.IsEnabled = true; }
    }
    async Task<bool> ConfirmLeaveSettings(string page)
    {
        if (!SettingsDirty(page)) return true;
        if (testResult != null && settingsLeaveFixture == null) return true;
        var dialog = new ContentDialog { XamlRoot = layout.XamlRoot, Title = L.T("你有未保存的设置，确定要离开吗？"),
            Content = L.T("离开会放弃此页尚未保存的修改。"), PrimaryButtonText = L.T("放弃修改并离开"), CloseButtonText = L.T("继续编辑") };
        var answer = settingsLeaveFixture == null ? await dialog.ShowAsync() : await settingsLeaveFixture(dialog);
        if (answer != ContentDialogResult.Primary) return false;
        await LoadPageDraft(page); return true;
    }
    async Task NavigateSettings(int target)
    {
        if (navigatingSettings || target < 0 || target == currentPageIndex) return;
        navigatingSettings = true;
        try {
            if (!await ConfirmLeaveSettings(PageKey(currentPageIndex))) { navigation.SelectedIndex = currentPageIndex; return; }
            currentPageIndex = target; ShowPage(target);
        }
        finally { navigatingSettings = false; }
    }
    async Task TestSavedSettings(string page)
    {
        if (SettingsDirty(page)) throw new InvalidOperationException(L.T("请先保存此页设置，再测试连接。"));
        await Call(page == "mail" ? "test_mail" : "test_ai");
    }
    async Task SettingsPagesSelfTest(Action<bool, string> check)
    {
        await bridge.Call("pause");
        await LoadPageDraft("mail");
        if (mailboxDrafts.Count == 0) await AddMailboxDraft();
        var before = await bridge.Call("config");
        var configPath = System.IO.Path.Combine(fixture!, "config.json");
        var savedBytes = System.IO.File.ReadAllBytes(configPath);
        account.Text = "staged-six@example.invalid";
        mailHost.Text = "imap.example.invalid";
        mailPort.Text = "993";
        mailUsername.Text = "staged-login";
        mailFolder.Text = "Archive";
        interval.Text = "77";
        mailSecret.Password = "synthetic-staged-secret";
        senderPolicyMode.SelectedIndex = 0;
        senderPolicySpam.IsOn = true;
        senderPolicyAddressValues.Add("staged-block@example.invalid");
        RefreshSettingsDirty();
        check(SettingsDirty("mail") && pageDirtyLabels["mail"].Visibility == Visibility.Visible,
            "Six mailbox edits and policy edits expose the page-wide unsaved indicator");
        check(System.IO.File.ReadAllBytes(configPath).SequenceEqual(savedBytes) && (await bridge.Call("config")).GetRawText() == before.GetRawText(),
            "Editing six native controls changes neither backend config nor persisted configuration before Save");
        var promptSeen = false;
        settingsLeaveFixture = dialog => { promptSeen = dialog.Title?.ToString() == L.T("你有未保存的设置，确定要离开吗？"); return Task.FromResult(ContentDialogResult.None); };
        try { check(!await ConfirmLeaveSettings("mail") && promptSeen && SettingsDirty("mail"), "Cancelling the unsaved-settings prompt preserves all staged edits"); }
        finally { settingsLeaveFixture = null; }
        await SaveSettingsPage("mail");
        var saved = await bridge.Call("config");
        check(saved.GetProperty("account").GetString() == "staged-six@example.invalid" && saved.GetProperty("username").GetString() == "staged-login" &&
            saved.GetProperty("mail_folder").GetString() == "Archive" && saved.GetProperty("interval").GetInt32() == 77 &&
            saved.GetProperty("mail_policy").GetProperty("skip_spam").GetBoolean() && !SettingsDirty("mail"),
            "The single page Save commits connection, credential, interval and policy together and clears dirty state");
        var savedCount = saved.GetProperty("mailboxes").GetArrayLength();
        await AddMailboxDraft(); await RemoveMailboxDraftForFixture();
        check((await bridge.Call("config")).GetProperty("mailboxes").GetArrayLength() == savedCount,
            "Mailbox list draft changes never invoke immediate select/add/remove/enable persistence");
        await LoadPageDraft("mail");
        foreach (var page in new[] { "mail", "ai", "general" }) check(pageDirtyLabels.ContainsKey(page), "One page-wide save/dirty footer is mounted for " + page);
    }
    Task RemoveMailboxDraftForFixture()
    {
        mailboxDrafts.RemoveAt(mailboxDraftIndex); mailboxDraftIndex = mailboxDrafts.Count - 1;
        RenderMailboxDraftNames(); if (mailboxDraftIndex >= 0) ShowMailboxDraft(mailboxDraftIndex); return Task.CompletedTask;
    }

}

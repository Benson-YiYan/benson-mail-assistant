using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.UI.Xaml.Controls;

namespace BensonMail;

sealed partial class MainWindow
{
    readonly List<Dictionary<string, object?>> mailboxDrafts = new();
    readonly HashSet<string> explicitDraftProviders = new();
    int mailboxDraftIndex = -1;
    Dictionary<string, object?>? SelectedMailboxDraft =>
        mailboxDraftIndex >= 0 && mailboxDraftIndex < mailboxDrafts.Count ? mailboxDrafts[mailboxDraftIndex] : null;
    static string DraftString(Dictionary<string, object?> draft, string key, string fallback = "") =>
        draft.TryGetValue(key, out var value) && value != null ? value.ToString() ?? fallback : fallback;
    void ResetMailboxDrafts()
    {
        mailboxDrafts.Clear();
        explicitDraftProviders.Clear();
        managedMailCredential = "";
        foreach (var profile in mailboxProfiles)
            mailboxDrafts.Add(JsonSerializer.Deserialize<Dictionary<string, object?>>(profile.GetRawText())!);
        mailboxDraftIndex = savedMailboxes.SelectedIndex;
    }
    void StoreMailboxDraft()
    {
        if (SelectedMailboxDraft is not { } draft || loadingMailboxes) return;
        var binding = MainOAuthBinding();
        var managed = MainManagedOAuth;
        draft["account"] = account.Text;
        draft["secret"] = managed ? (IsManagedOAuthBundle(managedMailCredential, binding) ? managedMailCredential : "") : mailSecret.Password;
        draft["mail_provider"] = binding.Provider;
        draft["host"] = mailHost.Text; draft["port"] = mailPort.Text; draft["security"] = mailSecurity.SelectedIndex == 1 ? "starttls" : "ssl";
        draft["proxy_mode"] = mailProxy.Value; draft["proxy_host"] = mailProxy.Host.Text; draft["proxy_port"] = mailProxy.Port.Text;
        draft["username"] = mailUsername.Text; draft["mail_folder"] = mailFolder.Text;
        draft["mail_auth"] = SupportsManagedOAuth(binding.Provider) ? "oauth2" : "password";
        draft["oauth_client_id"] = binding.ClientId; draft["oauth_tenant"] = "common";
        draft["oauth_mode"] = SupportsManagedOAuth(binding.Provider)
            ? (oauthModeChoice.SelectedIndex == 0 ? "managed" : "manual") : "manual";
        if (providerExplicitlySelected && !draft.ContainsKey("id")) explicitDraftProviders.Add(SelectedMailboxDraftId);
        draft["read_all_mail"] = readAllMail.IsOn;
    }
    object MailboxDraftValues()
    {
        StoreMailboxDraft();
        return mailboxDrafts;
    }
    string SelectedMailboxDraftId => mailboxDraftIndex >= 0 && mailboxDraftIndex < mailboxDrafts.Count
        ? DraftString(mailboxDrafts[mailboxDraftIndex], "id", DraftString(mailboxDrafts[mailboxDraftIndex], "client_id")) : "";
    void ShowMailboxDraft(int index)
    {
        if (index < 0 || index >= mailboxDrafts.Count) return;
        loadingMailboxes = true;
        try {
            mailboxDraftIndex = index;
            var draft = mailboxDrafts[index];
            var connection = JsonSerializer.SerializeToElement(draft);
            string Text(string key, string fallback = "") => DraftString(draft, key, fallback);
            account.Text = Text("account");
            mailProvider.SelectedIndex = mailPresets.FindIndex(p => JsonText(p, "id") == Text("mail_provider", "custom"));
            mailHost.Text = Text("host", "imap.163.com"); mailPort.Text = Text("port", "993");
            mailUsername.Text = OptionalMailUsername(account.Text, Text("username"));
            // TextChanged is dispatched later; the selected profile and its login
            // explanation must already agree before this switch returns.
            RefreshMailLogin(account, mailUsername, mailLoginSummary);
            mailFolder.Text = Text("mail_folder", "INBOX"); mailSecurity.SelectedIndex = Text("security") == "starttls" ? 1 : 0;
            readAllMail.IsOn = Text("read_all_mail").Equals("true", StringComparison.OrdinalIgnoreCase);
            mailAuth.SelectedIndex = Text("mail_auth") == "oauth2" ? 1 : 0; mailProxy.Load(connection);
            var supportsOAuth = SupportsManagedOAuth(Text("mail_provider"));
            var managed = supportsOAuth && Text("oauth_mode", "manual") == "managed";
            oauthClientId.Text = OAuthApplicationCredentials.ClientId(Text("mail_provider"));
            oauthTenant.Text = "common";
            oauthModeChoice.SelectedIndex = managed ? 0 : 1;
            if (!supportsOAuth) oauthModeChoice.SelectedIndex = 0;
            managedMailCredential = managed ? Text("secret") : "";
            mailSecret.Password = managed ? "" : Text("secret");
            providerExplicitlySelected = draft.ContainsKey("id") || draft.ContainsKey("original_id") ||
                explicitDraftProviders.Contains(SelectedMailboxDraftId);
            UpdateOAuthControls();
            savedMailboxes.SelectedIndex = index;
        }
        finally { loadingMailboxes = false; }
        RefreshSettingsDirty();
    }
    void RenderMailboxDraftNames()
    {
        loadingMailboxes = true;
        try {
            savedMailboxes.Items.Clear();
            foreach (var draft in mailboxDrafts) {
                var enabled = DraftString(draft, "monitor_enabled", "True").Equals("true", StringComparison.OrdinalIgnoreCase);
                var name = DraftString(draft, "account");
                savedMailboxes.Items.Add((name.Length == 0 ? L.T("新邮箱（尚未保存）") : name) + " · " + DraftString(draft, "mail_folder", "INBOX") + (enabled ? L.T(" · 已启用") : L.T(" · 已暂停")));
            }
            savedMailboxes.SelectedIndex = mailboxDraftIndex;
        }
        finally { loadingMailboxes = false; }
    }
    Task AddMailboxDraft()
    {
        StoreMailboxDraft();
        mailboxDrafts.Add(new() { ["client_id"] = Guid.NewGuid().ToString("N"), ["account"] = "", ["host"] = "imap.163.com",
            ["port"] = "993", ["security"] = "ssl", ["mail_folder"] = "INBOX", ["mail_provider"] = "163", ["mail_auth"] = "password",
            ["monitor_enabled"] = true, ["read_all_mail"] = false, ["oauth_mode"] = "manual",
            ["oauth_client_id"] = "", ["oauth_tenant"] = "common" });
        providerExplicitlySelected = false;
        mailboxDraftIndex = mailboxDrafts.Count - 1; RenderMailboxDraftNames(); ShowMailboxDraft(mailboxDraftIndex); return Task.CompletedTask;
    }
    Task ToggleMailboxDraft()
    {
        StoreMailboxDraft();
        if (mailboxDraftIndex < 0) return Task.CompletedTask;
        var draft = mailboxDrafts[mailboxDraftIndex];
        draft["monitor_enabled"] = !DraftString(draft, "monitor_enabled", "True").Equals("true", StringComparison.OrdinalIgnoreCase);
        RenderMailboxDraftNames(); RefreshSettingsDirty(); return Task.CompletedTask;
    }
    async Task RemoveMailboxDraft()
    {
        if (mailboxDraftIndex < 0) return;
        var dialog = new ContentDialog { XamlRoot = layout.XamlRoot, Title = L.T("移除此邮箱？"),
            Content = L.T("将在保存本页时移除此邮箱；已生成的报告保留。"), PrimaryButtonText = L.T("移除"), CloseButtonText = L.T("取消") };
        if (await dialog.ShowAsync() != ContentDialogResult.Primary) return;
        mailboxDrafts.RemoveAt(mailboxDraftIndex); mailboxDraftIndex = mailboxDrafts.Count - 1;
        RenderMailboxDraftNames();
        if (mailboxDraftIndex >= 0) ShowMailboxDraft(mailboxDraftIndex);
        else {
            loadingMailboxes = true;
            account.Text = mailSecret.Password = oauthClientId.Text = managedMailCredential = "";
            oauthTenant.Text = "common"; oauthModeChoice.SelectedIndex = 0; providerExplicitlySelected = false;
            loadingMailboxes = false; UpdateOAuthControls(); RefreshSettingsDirty();
        }
    }
}

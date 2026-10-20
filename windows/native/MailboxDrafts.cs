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
    int mailboxDraftIndex = -1;
    static string DraftString(Dictionary<string, object?> draft, string key, string fallback = "") =>
        draft.TryGetValue(key, out var value) && value != null ? value.ToString() ?? fallback : fallback;
    void ResetMailboxDrafts()
    {
        mailboxDrafts.Clear();
        foreach (var profile in mailboxProfiles)
            mailboxDrafts.Add(JsonSerializer.Deserialize<Dictionary<string, object?>>(profile.GetRawText())!);
        mailboxDraftIndex = savedMailboxes.SelectedIndex;
    }
    void StoreMailboxDraft()
    {
        if (mailboxDraftIndex < 0 || mailboxDraftIndex >= mailboxDrafts.Count || loadingMailboxes) return;
        var draft = mailboxDrafts[mailboxDraftIndex];
        draft["account"] = account.Text; draft["secret"] = mailSecret.Password;
        draft["mail_provider"] = mailProvider.SelectedIndex >= 0 && mailProvider.SelectedIndex < mailPresets.Count ? JsonText(mailPresets[mailProvider.SelectedIndex], "id") : "custom";
        draft["host"] = mailHost.Text; draft["port"] = mailPort.Text; draft["security"] = mailSecurity.SelectedIndex == 1 ? "starttls" : "ssl";
        draft["proxy_mode"] = mailProxy.Value; draft["proxy_host"] = mailProxy.Host.Text; draft["proxy_port"] = mailProxy.Port.Text;
        draft["username"] = mailUsername.Text; draft["mail_folder"] = mailFolder.Text; draft["mail_auth"] = mailAuth.SelectedIndex == 1 ? "oauth2" : "password";
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
            account.Text = Text("account"); mailSecret.Password = Text("secret");
            mailProvider.SelectedIndex = mailPresets.FindIndex(p => JsonText(p, "id") == Text("mail_provider", "custom"));
            mailHost.Text = Text("host", "imap.163.com"); mailPort.Text = Text("port", "993");
            mailUsername.Text = OptionalMailUsername(account.Text, Text("username"));
            mailFolder.Text = Text("mail_folder", "INBOX"); mailSecurity.SelectedIndex = Text("security") == "starttls" ? 1 : 0;
            mailAuth.SelectedIndex = Text("mail_auth") == "oauth2" ? 1 : 0; mailProxy.Load(connection);
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
            ["port"] = "993", ["security"] = "ssl", ["mail_folder"] = "INBOX", ["mail_provider"] = "163", ["mail_auth"] = "password", ["monitor_enabled"] = true });
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
        else { loadingMailboxes = true; account.Text = mailSecret.Password = ""; loadingMailboxes = false; RefreshSettingsDirty(); }
    }
}

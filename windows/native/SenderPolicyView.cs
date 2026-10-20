using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace BensonMail;

sealed partial class MainWindow
{
    readonly StackPanel senderPolicyBody = new() { Spacing = 10 };
    readonly ComboBox senderPolicyMode = new() { Header = L.T("名单模式"), HorizontalAlignment = HorizontalAlignment.Stretch };
    readonly ToggleSwitch senderPolicySpam = new() { Header = L.T("不总结垃圾邮件（部分邮箱可能不支持）"), OnContent = "", OffContent = "" };
    readonly TextBlock senderPolicyExplanation = Note("");
    readonly TextBlock senderPolicyStatus = Note("");
    readonly StackPanel senderPolicyAddresses = new() { Spacing = 4 };
    readonly StackPanel senderPolicyRecords = new() { Spacing = 8 };
    readonly Expander senderPolicyRecordDisclosure = new() { HorizontalAlignment = HorizontalAlignment.Stretch, HorizontalContentAlignment = HorizontalAlignment.Stretch };
    readonly HashSet<string> senderPolicyAddressSelection = new(StringComparer.OrdinalIgnoreCase);
    readonly HashSet<string> senderPolicyRecordSelection = new(StringComparer.Ordinal);
    readonly List<string> senderPolicyAddressValues = new();
    JsonElement senderPolicySnapshot;
    bool senderPolicyBusy, senderPolicyLoaded;

    Border BuildSenderPolicy()
    {
        senderPolicyMode.Items.Add(L.T("黑名单"));
        senderPolicyMode.Items.Add(L.T("白名单"));
        senderPolicyMode.SelectedIndex = 0;
        senderPolicyMode.FontFamily = senderPolicySpam.FontFamily = MailTypography.Font;
        senderPolicyMode.SelectionChanged += (_, _) => RefreshSenderPolicyLanguage();
        senderPolicyRecordDisclosure.Content = Stack(
            Note(L.T("这里只保存本地跳过记录；删除记录不会删除邮箱服务器上的邮件。")),
            Row(Action(L.T("全选记录"), () => {
                foreach (var record in PolicyRows("records")) senderPolicyRecordSelection.Add(PolicyText(record, "id"));
                RenderSenderPolicyRecords(); return Task.CompletedTask;
            }), Action(L.T("取消选择"), () => {
                senderPolicyRecordSelection.Clear(); RenderSenderPolicyRecords(); return Task.CompletedTask;
            })),
            Row(Action(L.T("总结选中邮件"), () => RunSenderPolicy(() => SummarizeSenderPolicyRecords(senderPolicyRecordSelection.ToArray()))),
                Action(L.T("删除选中记录"), () => RunSenderPolicy(() => DeleteSenderPolicyRecords(senderPolicyRecordSelection.ToArray())))),
            senderPolicyRecords);
        var content = Stack(Heading(L.T("屏蔽邮件")),
            Note(L.T("此设置适用于所有已配置邮箱。黑名单跳过名单内的发件人；白名单只总结名单内的发件人。")),
            senderPolicyMode, senderPolicyExplanation, senderPolicySpam,
            Heading(L.T("名单中的邮箱地址")), senderPolicyAddresses,
            Row(Action(L.T("添加地址"), () => RunSenderPolicy(AddSenderPolicyAddress)),
                Action(L.T("从发件人中批量选择"), () => RunSenderPolicy(ChooseSenderPolicyAddresses))),
            Row(Action(L.T("移除选中地址"), () => RunSenderPolicy(async () => {
                senderPolicyAddressValues.RemoveAll(address => senderPolicyAddressSelection.Contains(address));
                await SaveSenderPolicy();
            })), Action(L.T("保存屏蔽设置"), () => RunSenderPolicy(SaveSenderPolicy))),
            Action(L.T("刷新屏蔽记录"), () => RunSenderPolicy(LoadSenderPolicy)),
            senderPolicyRecordDisclosure, senderPolicyStatus);
        senderPolicyBody.Children.Add(content);
        return Card(senderPolicyBody);
    }

    static string PolicyText(JsonElement value, string key)
        => value.ValueKind == JsonValueKind.Object && value.TryGetProperty(key, out var field) ? field.ToString() : "";

    IEnumerable<JsonElement> PolicyRows(string key)
        => senderPolicySnapshot.ValueKind == JsonValueKind.Object && senderPolicySnapshot.TryGetProperty(key, out var rows) && rows.ValueKind == JsonValueKind.Array
            ? rows.EnumerateArray().ToArray() : Array.Empty<JsonElement>();

    void RefreshSenderPolicyLanguage()
    {
        senderPolicyExplanation.Text = L.T(senderPolicyMode.SelectedIndex == 1
            ? "白名单：只有名单中的发件人会自动总结。空白名单会跳过所有发件人。"
            : "黑名单：名单中的发件人不自动总结，其他发件人照常处理。");
        if (senderPolicyLoaded) RenderSenderPolicyRecords();
    }

    async Task RunSenderPolicy(Func<Task> action)
    {
        if (senderPolicyBusy || exitRequested) return;
        senderPolicyBusy = true; senderPolicyBody.IsEnabled = false; senderPolicyStatus.Text = L.T("正在处理…");
        try { senderPolicyStatus.Text = ""; await action(); }
        catch (Exception error) { if (!exitRequested) senderPolicyStatus.Text = L.T(error.Message); }
        finally { senderPolicyBusy = false; if (!exitRequested) senderPolicyBody.IsEnabled = true; }
    }

    async Task LoadSenderPolicy()
    {
        var result = await bridge.Call("policy_status");
        if (exitRequested) return;
        SetSenderPolicy(result);
    }

    void SetSenderPolicy(JsonElement result)
    {
        senderPolicySnapshot = result.Clone();
        var policy = result.TryGetProperty("policy", out var nested) ? nested : result.TryGetProperty("mail_policy", out nested) ? nested : result;
        senderPolicyMode.SelectedIndex = PolicyText(policy, "mode") == "whitelist" ? 1 : 0;
        senderPolicySpam.IsOn = policy.TryGetProperty("skip_spam", out var skip) && skip.ValueKind == JsonValueKind.True;
        senderPolicyAddressValues.Clear();
        if (policy.TryGetProperty("addresses", out var addresses) && addresses.ValueKind == JsonValueKind.Array)
            senderPolicyAddressValues.AddRange(addresses.EnumerateArray().Select(item => item.GetString() ?? "").Where(item => item.Length > 0));
        senderPolicyLoaded = true;
        RenderSenderPolicyAddresses(); RefreshSenderPolicyLanguage();
    }

    void RenderSenderPolicyAddresses()
    {
        senderPolicyAddresses.Children.Clear();
        senderPolicyAddressSelection.IntersectWith(senderPolicyAddressValues);
        foreach (var address in senderPolicyAddressValues) {
            var item = new CheckBox { Content = address, IsChecked = senderPolicyAddressSelection.Contains(address), FontFamily = MailTypography.Font };
            item.Checked += (_, _) => senderPolicyAddressSelection.Add(address);
            item.Unchecked += (_, _) => senderPolicyAddressSelection.Remove(address);
            senderPolicyAddresses.Children.Add(item);
        }
        if (senderPolicyAddressValues.Count == 0) senderPolicyAddresses.Children.Add(Note(L.T("名单为空。")));
    }

    async Task SaveSenderPolicy()
    {
        await bridge.Call("policy_save", new { mode = senderPolicyMode.SelectedIndex == 1 ? "whitelist" : "blacklist",
            addresses = senderPolicyAddressValues.ToArray(), skip_spam = senderPolicySpam.IsOn });
        await LoadSenderPolicy();
    }

    async Task AddSenderPolicyAddress()
    {
        var input = new TextBox { Header = L.T("发件人邮箱地址"), PlaceholderText = "name@example.com", FontFamily = MailTypography.Font, MinWidth = 320 };
        var dialog = new ContentDialog { XamlRoot = layout.XamlRoot, Title = L.T("添加地址"), Content = input,
            PrimaryButtonText = L.T("添加"), CloseButtonText = L.T("取消"), DefaultButton = ContentDialogButton.Primary };
        if (await dialog.ShowAsync() != ContentDialogResult.Primary) return;
        var address = input.Text.Trim();
        if (address.Length == 0) throw new InvalidOperationException(L.T("请输入邮箱地址。"));
        var added = !senderPolicyAddressValues.Contains(address, StringComparer.OrdinalIgnoreCase);
        if (added) senderPolicyAddressValues.Add(address);
        try { await SaveSenderPolicy(); }
        catch { if (added) senderPolicyAddressValues.Remove(address); throw; }
    }

    async Task ChooseSenderPolicyAddresses()
    {
        var selected = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        var candidates = new SortedSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var field in new[] { "known_senders", "senders" })
            foreach (var item in PolicyRows(field)) {
                var address = item.ValueKind == JsonValueKind.String ? item.GetString() ?? "" : PolicyText(item, "address");
                if (address.Length == 0) address = PolicyText(item, "sender");
                if (address.Length > 0) candidates.Add(address);
            }
        foreach (var record in PolicyRows("records")) {
            var address = PolicyText(record, "sender_address");
            if (address.Length == 0) address = PolicyText(record, "sender");
            if (address.Length > 0) candidates.Add(address);
        }
        var choices = new StackPanel { Spacing = 4 };
        foreach (var address in candidates) {
            var item = new CheckBox { Content = address, FontFamily = MailTypography.Font };
            item.Checked += (_, _) => selected.Add(address);
            item.Unchecked += (_, _) => selected.Remove(address);
            choices.Children.Add(item);
        }
        if (choices.Children.Count == 0) choices.Children.Add(Note(L.T("还没有已知发件人，可以先手动添加地址。")));
        var dialog = new ContentDialog { XamlRoot = layout.XamlRoot, Title = L.T("从发件人中批量选择"),
            Content = new ScrollViewer { Content = choices, MaxHeight = 400, MinWidth = 360 },
            PrimaryButtonText = L.T("添加选中地址"), CloseButtonText = L.T("取消") };
        if (await dialog.ShowAsync() != ContentDialogResult.Primary) return;
        foreach (var address in selected)
            if (!senderPolicyAddressValues.Contains(address, StringComparer.OrdinalIgnoreCase)) senderPolicyAddressValues.Add(address);
        await SaveSenderPolicy();
    }

    void RenderSenderPolicyRecords()
    {
        senderPolicyRecords.Children.Clear();
        var records = PolicyRows("records").ToArray();
        senderPolicyRecordDisclosure.Header = L.Bootstrap($"已屏蔽 {records.Length} 封邮件",
            $"{records.Length} skipped emails", $"{records.Length} correos omitidos");
        senderPolicyRecordSelection.IntersectWith(records.Select(record => PolicyText(record, "id")));
        foreach (var group in records.GroupBy(record => {
            var address = PolicyText(record, "sender_address");
            return address.Length > 0 ? address : PolicyText(record, "sender");
        }, StringComparer.OrdinalIgnoreCase)) {
            var contents = new StackPanel { Spacing = 8 };
            foreach (var record in group) {
                var id = PolicyText(record, "id");
                var title = PolicyText(record, "subject");
                if (title.Length == 0) title = L.T("无主题");
                var selected = new CheckBox { Content = new TextBlock { Text = title, TextWrapping = TextWrapping.Wrap },
                    IsChecked = senderPolicyRecordSelection.Contains(id), FontFamily = MailTypography.Font };
                selected.Checked += (_, _) => senderPolicyRecordSelection.Add(id);
                selected.Unchecked += (_, _) => senderPolicyRecordSelection.Remove(id);
                var reason = PolicyText(record, "reason");
                var reasonLabel = L.T(reason is "spam" or "junk" ? "垃圾邮件" : reason is "whitelist" or "not_whitelisted" ? "不在白名单" : reason == "blacklist" ? "命中黑名单" : reason);
                var state = PolicyText(record, "state");
                var stateLabel = L.T(state == "queued" ? "等待总结" : state == "processing" ? "正在总结" : state == "error" ? "总结失败，可重试" : "");
                contents.Children.Add(Stack(selected, Note(string.Join(" · ", new[] {
                    PolicyText(record, "received"), PolicyText(record, "account"), reasonLabel, stateLabel }.Where(value => value.Length > 0))),
                    Note(PolicyText(record, "last_error")),
                    Row(Action(L.T("总结此邮件"), () => RunSenderPolicy(() => SummarizeSenderPolicyRecords(new[] { id }))),
                        Action(L.T("删除此记录"), () => RunSenderPolicy(() => DeleteSenderPolicyRecords(new[] { id }))))));
            }
            senderPolicyRecords.Children.Add(new Expander { Header = group.Key + " · " + L.T($"{group.Count()} 封邮件"),
                Content = contents, HorizontalAlignment = HorizontalAlignment.Stretch, HorizontalContentAlignment = HorizontalAlignment.Stretch });
        }
        if (records.Length == 0) senderPolicyRecords.Children.Add(Note(L.T("还没有被跳过的邮件。")));
    }

    async Task DeleteSenderPolicyRecords(string[] ids)
    {
        if (ids.Length == 0) return;
        var dialog = new ContentDialog { XamlRoot = layout.XamlRoot, Title = L.T("删除本地跳过记录？"),
            Content = L.T("只删除选中的本地记录，不会删除邮箱服务器上的邮件。"),
            PrimaryButtonText = L.T("删除记录"), CloseButtonText = L.T("取消"), DefaultButton = ContentDialogButton.Close };
        if (await dialog.ShowAsync() != ContentDialogResult.Primary) return;
        await bridge.Call("policy_remove_records", new { ids }); await LoadSenderPolicy();
    }

    async Task SummarizeSenderPolicyRecords(string[] ids)
    {
        if (ids.Length == 0) return;
        senderPolicyStatus.Text = L.T("正在总结选中邮件…");
        await bridge.Call("policy_summarize_records", new { ids });
        await LoadSenderPolicy(); await Refresh();
        senderPolicyStatus.Text = L.T(running ? "已加入总结队列。" : "已加入总结队列；开始监听后会处理。");
    }

    async Task SenderPolicySelfTest(Action<bool, string> check)
    {
        var original = await bridge.Call("policy_status");
        var originalPolicy = original.GetProperty("policy").Clone();
        try {
            check(senderPolicyMode.SelectedIndex == 0 && !senderPolicySpam.IsOn,
                "Sender policy defaults to an empty blocklist with spam skipping disabled");
            senderPolicyMode.SelectedIndex = 1;
            senderPolicySpam.IsOn = true;
            senderPolicyAddressValues.Add("allowed@example.invalid");
            await SaveSenderPolicy();
            var saved = await bridge.Call("config");
            check(saved.GetProperty("mail_policy").GetProperty("mode").GetString() == "whitelist" &&
                saved.GetProperty("mail_policy").GetProperty("skip_spam").GetBoolean() &&
                saved.GetProperty("mail_policy").GetProperty("addresses")[0].GetString() == "allowed@example.invalid",
                "Native sender controls persist one global allowlist and spam option through the bridge");
            check(senderPolicyExplanation.Text == L.T("白名单：只有名单中的发件人会自动总结。空白名单会跳过所有发件人。"),
                "Allowlist UI explains that an empty allowlist skips every sender");
            SetSenderPolicy(JsonSerializer.SerializeToElement(new {
                policy = originalPolicy,
                records = new[] {
                    new { id = "synthetic-a", sender = "blocked@example.invalid", subject = "Synthetic report A", received = "2026-10-20", reason = "blacklist", state = "blocked" },
                    new { id = "synthetic-b", sender = "blocked@example.invalid", subject = "Synthetic report B", received = "2026-10-20", reason = "spam", state = "queued" }
                }
            }));
            check(senderPolicyRecords.Children.Count == 1 && senderPolicyRecords.Children[0] is Expander { IsExpanded: false },
                "Skipped records group by sender in a collapsed native expander");
            check(!senderPolicyRecordDisclosure.IsExpanded && senderPolicyRecordDisclosure.Header.ToString()!.Contains("2"),
                "All skipped history and bulk actions stay inside a collapsed disclosure with a live total");
            var group = (StackPanel)((Expander)senderPolicyRecords.Children[0]).Content;
            check(group.Children.Count == 2, "Expanded sender groups contain each skipped email");
            var first = (CheckBox)((StackPanel)group.Children[0]).Children[0];
            first.IsChecked = true;
            check(senderPolicyRecordSelection.Contains("synthetic-a"),
                "Record checkboxes track stable IDs for bulk local actions");
            senderPolicyRecordSelection.Add("synthetic-b");
            RenderSenderPolicyRecords();
            check(senderPolicyRecordSelection.Count == 2, "Record selections survive grouped list redraws");
        }
        finally {
            await bridge.Call("policy_save", originalPolicy);
            senderPolicyRecordSelection.Clear();
            await LoadSenderPolicy();
        }
    }
}

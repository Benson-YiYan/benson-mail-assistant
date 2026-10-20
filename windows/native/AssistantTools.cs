using System;
using System.Globalization;
using System.IO;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Windows.ApplicationModel.DataTransfer;

namespace BensonMail;

sealed partial class MainWindow
{
    readonly Button notificationToggle = new() { Content = L.T("暂停系统通知"), CornerRadius = new CornerRadius(4) };
    readonly ToggleSwitch quietEnabled = new() { Header = L.T("免打扰时间"), OnContent = L.T("开启"), OffContent = L.T("关闭") };
    readonly TextBox quietStart = new() { Header = L.T("开始时间"), Text = "22:00", PlaceholderText = "HH:mm", Width = 150 };
    readonly TextBox quietEnd = new() { Header = L.T("结束时间"), Text = "08:00", PlaceholderText = "HH:mm", Width = 150 };
    bool notificationsEnabled = true;

    Task<JsonElement> Assistant(string action, object? values = null)
    {
        var payload = JsonSerializer.SerializeToElement(values ?? new { });
        var data = new System.Collections.Generic.Dictionary<string, object?> { ["action"] = action };
        foreach (var property in payload.EnumerateObject()) data[property.Name] = property.Value;
        return bridge.Call("assistant_features", data);
    }
    static string JsonText(JsonElement item, string key, string fallback = "") =>
        item.TryGetProperty(key, out var value) && value.ValueKind != JsonValueKind.Null ? value.ValueKind == JsonValueKind.String ? value.GetString() ?? fallback : value.ToString() : fallback;
    void LoadNotificationPreferences(JsonElement config)
    {
        notificationsEnabled = !config.TryGetProperty("notifications_enabled", out var enabled) || enabled.GetBoolean();
        notificationsSetting.IsOn = notificationsEnabled;
        notificationToggle.Content = L.T(notificationsEnabled ? "暂停系统通知" : "开启系统通知");
        if (config.TryGetProperty("quiet_hours", out var quiet)) {
            quietEnabled.IsOn = quiet.TryGetProperty("enabled", out var active) && active.GetBoolean();
            quietStart.Text = JsonText(quiet, "start", "22:00"); quietEnd.Text = JsonText(quiet, "end", "08:00");
            appliedQuietEnabled = quietEnabled.IsOn; appliedQuietStart = quietStart.Text; appliedQuietEnd = quietEnd.Text;
        }
    }
    async Task SaveNotificationPreferences(bool? enabled = null)
    {
        var wasDirty = SettingsDirty("general");
        await Call("save_notifications", new { notifications_enabled = enabled ?? notificationsEnabled,
            quiet_hours = new { enabled = appliedQuietEnabled, start = appliedQuietStart, end = appliedQuietEnd } });
        if (enabled.HasValue) notificationsEnabled = enabled.Value;
        if (!wasDirty) { notificationsSetting.IsOn = notificationsEnabled; AcceptSettingsBaseline("general"); }
        notificationToggle.Content = L.T(notificationsEnabled ? "暂停系统通知" : "开启系统通知");
    }
    bool NativeNotificationsAllowed()
    {
        if (!notificationsEnabled) return false;
        if (!appliedQuietEnabled) return true;
        if (!TimeSpan.TryParseExact(appliedQuietStart, @"hh\:mm", CultureInfo.InvariantCulture, out var start) ||
            !TimeSpan.TryParseExact(appliedQuietEnd, @"hh\:mm", CultureInfo.InvariantCulture, out var end)) return true;
        var now = DateTime.Now.TimeOfDay;
        return start != end && !(start < end ? now >= start && now < end : now >= start || now < end);
    }
    Border NotificationSettingsCard() => Card(Stack(Heading(L.T("系统通知与免打扰")), notificationsSetting, quietEnabled,
        Row(quietStart, quietEnd), Note(L.T("使用电脑本地时间，可跨午夜。开始和结束相同表示全天免打扰；邮件仍会检查并保存报告，静默通知不会补发。"))));
    Border HistoryAndDiagnosticsCard() => Card(Stack(Heading(L.T("历史邮件与诊断")),
        Note(L.T("按日期补总结已有邮件；先查看数量，确认后才加入队列。会跳过已总结邮件，并遵守屏蔽及垃圾邮件设置。")),
        Row(Action(L.T("补总结历史邮件"), BackfillHistory), Action(L.T("导出诊断包"), ExportDiagnostics)),
        Note(L.T("诊断包仅包含脱敏的运行信息，不包含密钥、邮件正文或附件。"))));
    Border UsageSettingsCard() => Card(Stack(Heading(L.T("费用与用量")),
        Note(L.T("记录 AI 调用次数和服务商返回的 Token。未返回用量的调用会单独标记；价格由你填写，金额仅为估算。")),
        inputRate, outputRate, rateCurrency, Note(L.T("价格仅在保存 AI 服务页后生效，并绑定当前基础地址和模型。")), Action(L.T("查看用量"), ShowUsage)));

    void AssistantToolsSelfTest(Action<bool, string> check)
    {
        var savedEnabled = notificationsEnabled; var savedQuiet = appliedQuietEnabled;
        var savedStart = appliedQuietStart; var savedEnd = appliedQuietEnd;
        try {
            notificationsEnabled = false; appliedQuietEnabled = false;
            check(!NativeNotificationsAllowed(), "Native presentation guard discards pending system notices while muted");
            notificationsEnabled = true; appliedQuietEnabled = false;
            check(NativeNotificationsAllowed(), "Notifications can resume independently of monitoring");
            appliedQuietEnabled = true; appliedQuietStart = appliedQuietEnd = "09:00";
            check(!NativeNotificationsAllowed(), "Equal quiet-hour endpoints silence native notifications all day");
        }
        finally { notificationsEnabled = savedEnabled; appliedQuietEnabled = savedQuiet; appliedQuietStart = savedStart; appliedQuietEnd = savedEnd; }
    }

    async Task ExportDiagnostics()
    {
        var picker = new Windows.Storage.Pickers.FolderPicker();
        WinRT.Interop.InitializeWithWindow.Initialize(picker, WinRT.Interop.WindowNative.GetWindowHandle(this));
        picker.FileTypeFilter.Add("*");
        var picked = await picker.PickSingleFolderAsync();
        if (picked == null || exitRequested) return;
        var result = await Assistant("diagnostics", new { directory = picked.Path });
        var dialog = new ContentDialog { XamlRoot = layout.XamlRoot, Title = L.T("诊断包已导出"),
            Content = Stack(Note(L.T("诊断包仅包含脱敏的运行信息，不包含密钥、邮件正文或附件。")),
                new TextBox { Text = JsonText(result, "path"), IsReadOnly = true, TextWrapping = TextWrapping.Wrap, AcceptsReturn = true }),
            PrimaryButtonText = L.T("打开文件夹"), CloseButtonText = L.T("关闭") };
        if (await dialog.ShowAsync() == ContentDialogResult.Primary) Open(picked.Path);
    }
    async Task BackfillHistory()
    {
        if (SettingsDirty("mail")) throw new InvalidOperationException(L.T("请先保存此页设置，再测试连接。"));
        var start = new CalendarDatePicker { Header = L.T("起始日期"), Date = DateTimeOffset.Now.AddDays(-7), MinWidth = 0, Width = 200 };
        var end = new CalendarDatePicker { Header = L.T("结束日期"), Date = DateTimeOffset.Now, MinWidth = 0, Width = 200 };
        var message = new TextBlock { TextWrapping = TextWrapping.Wrap, IsTextSelectionEnabled = true };
        JsonElement snapshot = default;
        var previewButton = new Button { Content = L.T("查看待处理数量") };
        var dialog = new ContentDialog { XamlRoot = layout.XamlRoot, Title = L.T("补总结历史邮件"),
            PrimaryButtonText = L.T("确认加入总结队列"), IsPrimaryButtonEnabled = false, CloseButtonText = L.T("取消") };
        void Invalidate() { snapshot = default; dialog.IsPrimaryButtonEnabled = false; message.Text = ""; }
        start.DateChanged += (_, _) => Invalidate(); end.DateChanged += (_, _) => Invalidate();
        previewButton.Click += async (_, _) => {
            dialog.IsPrimaryButtonEnabled = false; previewButton.IsEnabled = false;
            try {
                if (!start.Date.HasValue || !end.Date.HasValue || start.Date.Value.Date > end.Date.Value.Date)
                    throw new InvalidOperationException(L.T("请选择有效的起始和结束日期。"));
                message.Text = L.T("正在读取邮件数量，不会调用 AI…");
                snapshot = await Assistant("history_preview", new { start = start.Date.Value.ToString("yyyy-MM-dd"),
                    end = end.Date.Value.ToString("yyyy-MM-dd"), mailbox_id = SelectedMailboxDraftId });
                message.Text = L.T("待总结：") + JsonText(snapshot, "count", "0") + "\n" + L.T("已总结：") + JsonText(snapshot, "already_summarized", "0") +
                    "\n" + L.T("确认后会消耗所选 AI 的额度；暂停监听时只加入队列，开始监听后处理。");
                dialog.IsPrimaryButtonEnabled = snapshot.TryGetProperty("count", out var count) && count.GetInt32() > 0;
            } catch (Exception error) { message.Text = L.T(error.Message); }
            finally { previewButton.IsEnabled = true; }
        };
        dialog.Content = Stack(Note(L.T("针对当前选中的邮箱。日期按邮箱服务器的收件日期筛选。")), Row(start, end), previewButton, message);
        if (await dialog.ShowAsync() == ContentDialogResult.Primary && snapshot.ValueKind == JsonValueKind.Object) {
            var result = await Assistant("history_queue", new { preview_id = JsonText(snapshot, "preview_id") });
            detail.Text = L.T("已加入总结队列：") + JsonText(result, "count", "0");
        }
    }
    async Task ShowUsage()
    {
        var snapshot = await Assistant("usage");
        var summary = new TextBlock { TextWrapping = TextWrapping.Wrap, IsTextSelectionEnabled = true };
        void Render(JsonElement data) => summary.Text = L.T("调用次数：") + JsonText(data, "calls", "0") + "\n" +
            L.T("输入 Token：") + JsonText(data, "input_tokens", "0") + "\n" + L.T("输出 Token：") + JsonText(data, "output_tokens", "0") + "\n" +
            L.T("用量未知的调用：") + JsonText(data, "unknown_usage_calls", "0") + "\n" + L.T("估算费用：") + JsonText(data, "estimated_cost", "—") + " " + JsonText(data, "currency", "USD");
        Render(snapshot);
        var breakdown = new TextBlock { TextWrapping = TextWrapping.Wrap, IsTextSelectionEnabled = true };
        if (snapshot.TryGetProperty("groups", out var groups)) foreach (var group in groups.EnumerateArray())
            breakdown.Text += JsonText(group, "provider") + " · " + JsonText(group, "model") + "\n" +
                L.T("调用次数：") + JsonText(group, "calls", "0") + " · " + L.T("输入 Token：") + JsonText(group, "input_tokens", "—") +
                " · " + L.T("输出 Token：") + JsonText(group, "output_tokens", "—") + "\n" + L.T("估算费用：") +
                JsonText(group, "estimated_cost", "—") + " " + JsonText(group, "currency") + "\n\n";

        await new ContentDialog { XamlRoot = layout.XamlRoot, Title = L.T("费用与用量"), CloseButtonText = L.T("关闭"),
            Content = Scroll(Stack(summary, breakdown, Note(L.T("未提供 Token 用量的调用不计入费用。Codex 与 Harness 的订阅费用无法由本工具推算。")))) }.ShowAsync();
    }
    async Task ShowSources()
    {
        if (SelectedReport is not Report report) return;
        var result = await Assistant("sources", new { path = report.path });
        var content = Stack(Note(L.T("以下内容来自保存的原邮件和附件提取结果，用于核对报告。AI 的推断仍需自行确认。")));
        if (result.TryGetProperty("sources", out var sources)) foreach (var source in sources.EnumerateArray()) {
            content.Children.Add(Heading(L.T(JsonText(source, "label"))));
            if (source.TryGetProperty("truncated", out var truncated) && truncated.GetBoolean()) content.Children.Add(Note(L.T("来源文字过长，当前只展示部分内容。")));
            content.Children.Add(new TextBox { Text = JsonText(source, "text"), IsReadOnly = true,
                TextWrapping = TextWrapping.Wrap, AcceptsReturn = true, MaxHeight = 240 });
        }
        if (JsonText(result, "limitation").Length > 0) content.Children.Add(Note(L.T(JsonText(result, "limitation"))));
        if (!result.TryGetProperty("available", out var available) || !available.GetBoolean()) content.Children.Add(Note(L.T("这份旧报告未保存可核对的来源内容。")));
        await new ContentDialog { XamlRoot = layout.XamlRoot, Title = L.T("查看邮件与附件来源"), Content = Scroll(content), CloseButtonText = L.T("关闭") }.ShowAsync();
    }
    async Task ReplyDraft()
    {
        if (SelectedReport is not Report report) return;
        var tone = new ComboBox { Header = L.T("语气"), HorizontalAlignment = HorizontalAlignment.Stretch };
        foreach (var text in new[] { "正式", "友好", "简短" }) tone.Items.Add(L.T(text)); tone.SelectedIndex = 0;
        var language = new ComboBox { Header = L.T("草稿语言"), HorizontalAlignment = HorizontalAlignment.Stretch };
        foreach (var text in new[] { L.T("跟随来信语言"), "简体中文", "English", "Español" }) language.Items.Add(text); language.SelectedIndex = 0;
        var instructions = new TextBox { Header = L.T("补充要求"), AcceptsReturn = true, TextWrapping = TextWrapping.Wrap, Height = 80 };
        var draft = new TextBox { Header = L.T("可编辑的回复草稿"), AcceptsReturn = true, TextWrapping = TextWrapping.Wrap, Height = 220 };
        var status = new TextBlock { TextWrapping = TextWrapping.Wrap, IsTextSelectionEnabled = true };
        var recipient = new TextBox { Header = L.T("收件人") };
        var subject = new TextBox { Header = L.T("主题") };
        string draftPath = "";
        var saveDraft = new Button { Content = L.T("保存本地草稿"), IsEnabled = false };
        var generate = new Button { Content = L.T("生成草稿") };
        var copy = new Button { Content = L.T("复制草稿"), IsEnabled = false };
        generate.Click += async (_, _) => {
            generate.IsEnabled = false; status.Text = L.T("正在生成草稿…");
            try {
                var result = await Assistant("reply_draft", new { path = report.path, instructions = instructions.Text,
                    tone = new[] { "formal", "friendly", "brief" }[Math.Max(0, tone.SelectedIndex)],
                    language = new[] { "auto", "zh", "en", "es" }[Math.Max(0, language.SelectedIndex)] });
                draft.Text = JsonText(result, "draft"); copy.IsEnabled = draft.Text.Length > 0;
                recipient.Text = JsonText(result, "recipient"); subject.Text = JsonText(result, "subject");
                draftPath = JsonText(result, "draft_path", JsonText(result, "path")); saveDraft.IsEnabled = draftPath.Length > 0;
                status.Text = L.T("收件人：") + JsonText(result, "recipient") + "\n" + L.T("主题：") + JsonText(result, "subject") + "\n" +
                    L.T("草稿未发送。请核对收件人、日期、金额和承诺，再复制到邮箱发送。");
            } catch (Exception error) { status.Text = L.T(error.Message); }
            finally { generate.IsEnabled = true; }
        };
        saveDraft.Click += async (_, _) => {
            saveDraft.IsEnabled = false;
            try { await Assistant("draft_save", new { draft_path = draftPath, draft = draft.Text, recipient = recipient.Text, subject = subject.Text }); status.Text = L.T("本地草稿已保存，尚未发送。"); }
            catch (Exception error) { status.Text = L.T(error.Message); }
            finally { saveDraft.IsEnabled = true; }
        };
        copy.Click += (_, _) => { var data = new DataPackage(); data.SetText(draft.Text); Clipboard.SetContent(data); status.Text = L.T("草稿已复制，尚未发送。"); };
        await new ContentDialog { XamlRoot = layout.XamlRoot, Title = L.T("回复草稿"), CloseButtonText = L.T("关闭"),
            Content = Scroll(Stack(tone, language, instructions, Row(generate, copy, saveDraft), recipient, subject, draft, status)) }.ShowAsync();
    }
}

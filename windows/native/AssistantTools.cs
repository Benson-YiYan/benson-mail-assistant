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
    Border UsageSettingsCard() => Card(Stack(Heading(L.T("费用单价")),
        Note(L.T("以下是计算预估费用的单价，不是 Token 用量或限额。实际调用次数、Token 用量和费用请点击“查看用量记录”。")),
        inputRate, outputRate, rateCurrency, Note(L.T("价格仅在保存 AI 服务页后生效，并绑定当前基础地址和模型。")), Action(L.T("查看用量记录"), ShowUsage)));

    void AssistantToolsSelfTest(Action<bool, string> check)
    {
        using (var usage = JsonDocument.Parse("{\"input_tokens\":3067,\"output_tokens\":627,\"estimated_cost\":null}")) {
            check(UsageNumber(usage.RootElement, "input_tokens") == "3,067" && UsageNumber(usage.RootElement, "output_tokens") == "627",
                "Usage displays separately labelled input and output counts with thousands separators");
            check(UsageCost(usage.RootElement) == L.T("未知"), "Missing cost is explicitly unknown and never inferred as free");
        }
        using (var usage = JsonDocument.Parse("{\"calls\":1,\"input_tokens\":0,\"output_tokens\":0,\"groups\":[{\"input_tokens\":null,\"output_tokens\":null}]}"))
            check(UsageNumber(usage.RootElement, "output_tokens") == L.T("未知"),
                "A provider without token usage remains unknown even when the aggregate backend sum is zero");
        using (var usage = JsonDocument.Parse("{\"provider\":\"fixture\",\"model\":\"fixture\",\"calls\":4,\"input_tokens\":3067,\"output_tokens\":627,\"actual_cost\":1.25,\"actual_currency\":\"USD\",\"actual_cost_calls\":1,\"estimated_cost\":2.5,\"currency\":\"CNY\",\"estimated_cost_calls\":2,\"unknown_cost_calls\":1}")) {
            var text = UsageGroupText(usage.RootElement);
            check(text.Contains(L.T("上游返回费用：") + "1.25 USD") && text.Contains(L.T("本地估算费用：") + "2.5 CNY") &&
                text.Contains(L.T("上游费用覆盖调用数：") + "1") && text.Contains(L.T("本地估算覆盖调用数：") + "2") &&
                text.Contains(L.T("费用未知的调用：") + "1") && !text.Contains("3.75"),
                "Provider cost and local estimate retain distinct currencies and coverage without being summed");
        }
        using (var balance = JsonDocument.Parse("{\"status\":\"ok\",\"provider\":\"fixture\",\"balances\":[{\"currency\":\"USD\",\"total_balance\":\"1234.5\",\"granted_balance\":\"0\",\"topped_up_balance\":\"1234.5\"}],\"checked_at\":\"fixture-time\"}"))
            check(UsageBalanceText(balance.RootElement).Contains(L.T("账户余额：") + "1,234.5 USD") &&
                UsageBalanceText(balance.RootElement).Contains("fixture-time"), "Manual balance renderer preserves currency, amount and check time without generating AI content");
        foreach (var status in new[] { "unsupported", "not_api", "error" }) {
            using var balance = JsonDocument.Parse("{\"status\":\"" + status + "\",\"message\":\"UNTRANSLATED_MESSAGE_MUST_NOT_APPEAR\"}");
            var text = UsageBalanceText(balance.RootElement);
            check(text.Length > 0 && !text.Contains("UNTRANSLATED_MESSAGE_MUST_NOT_APPEAR"),
                "Balance status is localized from protocol status without displaying upstream message: " + status);
        }
        using (var balance = JsonDocument.Parse("{\"status\":\"error\",\"error_code\":\"permission\"}"))
            check(UsageBalanceText(balance.RootElement) == L.T("当前 API Key 没有查询余额的权限；AI 调用仍可能正常。"),
                "Balance permission failures explain that inference may still work without recommending a management key");
        using (var balance = JsonDocument.Parse("{\"status\":\"error\",\"error_code\":\"authentication\"}"))
            check(UsageBalanceText(balance.RootElement) == L.T("余额查询的 API Key 认证失败，请检查已保存的密钥。"),
                "Balance authentication failures have a precise localized explanation");
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
    static string UsageNumber(JsonElement data, string key)
    {
        if (!data.TryGetProperty(key, out var value) || value.ValueKind == JsonValueKind.Null ||
            !decimal.TryParse(value.ToString(), NumberStyles.Float, CultureInfo.InvariantCulture, out var number)) return L.T("未知");
        if ((key == "input_tokens" || key == "output_tokens") && data.TryGetProperty("groups", out var groups) &&
            data.TryGetProperty("calls", out var calls) && calls.GetInt32() > 0) {
            var anyKnown = false;
            foreach (var group in groups.EnumerateArray())
                if (group.TryGetProperty(key, out var groupValue) && groupValue.ValueKind == JsonValueKind.Number) anyKnown = true;
            if (!anyKnown) return L.T("未知");
        }
        return number.ToString("#,0.########", CultureInfo.InvariantCulture);
    }
    static string UsageCost(JsonElement data, string amountKey = "estimated_cost", string currencyKey = "currency")
    {
        var amount = UsageNumber(data, amountKey);
        return amount == L.T("未知") ? amount : amount + " " + JsonText(data, currencyKey);
    }
    static string UsageGroupText(JsonElement group) =>
        JsonText(group, "provider") + " · " + JsonText(group, "model") + "\n" +
        L.T("调用次数：") + UsageNumber(group, "calls") + "\n" + L.T("输入 Token：") + UsageNumber(group, "input_tokens") +
        "\n" + L.T("输出 Token：") + UsageNumber(group, "output_tokens") + "\n" +
        L.T("上游返回费用：") + UsageCost(group, "actual_cost", "actual_currency") + "\n" +
        L.T("上游费用覆盖调用数：") + UsageNumber(group, "actual_cost_calls") + "\n" +
        L.T("本地估算费用：") + UsageCost(group) + "\n" +
        L.T("本地估算覆盖调用数：") + UsageNumber(group, "estimated_cost_calls") + "\n" +
        L.T("费用未知的调用：") + UsageNumber(group, "unknown_cost_calls") + "\n\n";
    static string UsageBalanceText(JsonElement data)
    {
        switch (JsonText(data, "status")) {
            case "unsupported": return L.T("当前服务商或基础地址不支持查询账户余额。仅支持官方 DeepSeek 和 OpenRouter。");
            case "not_api": return L.T("当前使用 Codex 或 Harness，无法查询 API 账户余额。");
            case "ok": break;
            default:
                return JsonText(data, "error_code") switch {
                    "permission" => L.T("当前 API Key 没有查询余额的权限；AI 调用仍可能正常。"),
                    "authentication" or "invalid_key" => L.T("余额查询的 API Key 认证失败，请检查已保存的密钥。"),
                    "missing_key" => L.T("尚未保存 API Key，请先在 AI 服务页保存密钥。"),
                    "credentials" => L.T("无法读取已保存的 API Key，请检查系统凭据存储并重新保存密钥。"),
                    "timeout" => L.T("账户余额查询超时，请稍后重试并检查网络。"),
                    "rate_limit" => L.T("账户余额查询过于频繁，请稍后重试。"),
                    "tls" => L.T("账户余额查询的安全连接失败，请检查网络代理与系统证书。"),
                    "dns" => L.T("无法解析余额查询服务器地址，请检查网络与 DNS。"),
                    "invalid_response" or "response_too_large" => L.T("服务商返回了无法识别的余额响应。"),
                    _ => L.T("账户余额查询失败，请检查已保存的 AI 设置、网络或服务商状态。")
                };
        }
        var text = JsonText(data, "provider");
        if (data.TryGetProperty("balances", out var balances)) foreach (var balance in balances.EnumerateArray()) {
            var currency = JsonText(balance, "currency");
            text += "\n" + L.T("账户余额：") + UsageNumber(balance, "total_balance") + " " + currency;
            if (balance.TryGetProperty("granted_balance", out var granted) && granted.ValueKind != JsonValueKind.Null)
                text += "\n" + L.T("赠送余额：") + UsageNumber(balance, "granted_balance") + " " + currency;
            if (balance.TryGetProperty("topped_up_balance", out var topped) && topped.ValueKind != JsonValueKind.Null)
                text += "\n" + L.T("充值余额：") + UsageNumber(balance, "topped_up_balance") + " " + currency;
        }
        return text + "\n" + L.T("查询时间：") + JsonText(data, "checked_at");
    }
    async Task ShowUsage()
    {
        var snapshot = await Assistant("usage");
        var summary = new TextBlock { TextWrapping = TextWrapping.Wrap, IsTextSelectionEnabled = true };
        void Render(JsonElement data) => summary.Text = L.T("调用次数：") + UsageNumber(data, "calls") + "\n" +
            L.T("输入 Token：") + UsageNumber(data, "input_tokens") + "\n" + L.T("输出 Token：") + UsageNumber(data, "output_tokens") + "\n" +
            L.T("用量未知的调用：") + UsageNumber(data, "unknown_usage_calls") + "\n" +
            L.T("费用未知的调用：") + UsageNumber(data, "unknown_cost_calls");
        Render(snapshot);
        var breakdown = new TextBlock { TextWrapping = TextWrapping.Wrap, IsTextSelectionEnabled = true };
        if (snapshot.TryGetProperty("groups", out var groups)) foreach (var group in groups.EnumerateArray())
            breakdown.Text += UsageGroupText(group);
        var balanceResult = new TextBlock { Text = L.T("尚未查询账户余额。"), TextWrapping = TextWrapping.Wrap, IsTextSelectionEnabled = true };
        var balanceButton = new Button { Content = L.T("查询账户余额") };
        balanceButton.Click += async (_, _) => {
            balanceButton.IsEnabled = false; balanceResult.Text = L.T("正在查询账户余额…");
            try { balanceResult.Text = UsageBalanceText(await Assistant("usage_balance")); }
            catch { balanceResult.Text = L.T("账户余额查询失败，请检查已保存的 AI 设置、网络或服务商状态。"); }
            finally { balanceButton.IsEnabled = true; }
        };

        await new ContentDialog { XamlRoot = layout.XamlRoot, Title = L.T("费用与用量"), CloseButtonText = L.T("关闭"),
            Content = Scroll(Stack(summary, breakdown,
                Note(L.T("输入 Token 是发给 AI 的内容，包括原邮件、附件和对话；输出 Token 是 AI 返回的内容。")),
                Note(L.T("上游返回费用与本地估算费用分别显示，不相加。只有缺少上游费用的调用才使用本地估算。未知不代表免费；覆盖调用数表明已知费用涉及多少次本软件调用，不能推断完整账单。")),
                Note(L.T("Codex 与 Harness 的订阅费用无法由本工具推算。")),
                Heading(L.T("账户余额")), balanceButton, balanceResult,
                Note(L.T("仅手动查询，不生成 AI 内容。账户余额可能包含其他应用的消费，不能用于归属本软件费用。查询使用已保存的 AI 设置。")),
                Note(L.T("OpenRouter 余额接口可能要求管理权限，普通推理 Key 可能返回 403。无需为了查询余额将推理 Key 换成管理 Key。")))) }.ShowAsync();
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

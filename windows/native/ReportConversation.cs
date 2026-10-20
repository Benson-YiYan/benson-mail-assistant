using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace BensonMail;

sealed partial class MainWindow
{
    readonly Button retryReport = new() { Content = L.T("重新总结"), IsEnabled = false };
    readonly Button sendQuestion = new() { Content = L.T("发送问题"), IsEnabled = false };
    readonly Button attachQuestion = new() { Content = L.T("添加附件"), IsEnabled = false };
    readonly Button clearQuestionFiles = new() { Content = L.T("移除附件"), IsEnabled = false };
    readonly TextBox question = new() { Header = L.T("对邮件提问"), PlaceholderText = L.T("输入问题，可继续追问或添加附件"),
        AcceptsReturn = true, TextWrapping = TextWrapping.Wrap, MinHeight = 80, MaxHeight = 140 };
    readonly TextBlock conversationStatus = new() { TextWrapping = TextWrapping.Wrap, IsTextSelectionEnabled = true };
    readonly TextBlock questionFiles = new() { TextWrapping = TextWrapping.Wrap, IsTextSelectionEnabled = true };
    readonly StackPanel chatMessages = new() { Spacing = 12 };
    readonly ScrollViewer chatScroll = new() { VerticalScrollBarVisibility = ScrollBarVisibility.Auto };
    readonly Grid chatPanel = new() { RowSpacing = 10, Visibility = Visibility.Collapsed };
    readonly ProgressRing conversationProgress = new() { IsActive = false, Width = 20, Height = 20 };
    readonly Dictionary<string, (string text, List<string> files)> questionDrafts = new(StringComparer.OrdinalIgnoreCase);
    readonly HashSet<string> conversationBusy = new(StringComparer.OrdinalIgnoreCase);
    readonly Dictionary<string, string> conversationErrors = new(StringComparer.OrdinalIgnoreCase);
    JsonElement conversationHistory;
    bool conversationCompressed;
    string? conversationPath;
    bool loadingQuestion;
    long conversationLoadGeneration;

    Grid BuildReportConversation()
    {
        foreach (var control in new Control[] { retryReport, sendQuestion, attachQuestion, clearQuestionFiles, question })
            control.FontFamily = MailTypography.Font;
        retryReport.Click += async (_, _) => await RetrySelectedReport();
        sendQuestion.Click += async (_, _) => await SendQuestion();
        attachQuestion.Click += async (_, _) => await Guard(AddQuestionFiles);
        clearQuestionFiles.Click += (_, _) => {
            if (conversationPath == null) return;
            var draft = Draft(conversationPath); draft.files.Clear(); questionDrafts[conversationPath] = draft; UpdateConversationControls();
        };
        question.TextChanged += (_, _) => {
            if (!loadingQuestion && conversationPath != null) {
                var draft = Draft(conversationPath); questionDrafts[conversationPath] = (question.Text, draft.files);
                UpdateConversationControls();
            }
        };
        chatPanel.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) });
        for (var i = 0; i < 3; i++) chatPanel.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        chatScroll.Content = chatMessages; chatPanel.Children.Add(chatScroll);
        Grid.SetRow(questionFiles, 1); chatPanel.Children.Add(questionFiles);
        Grid.SetRow(question, 2); chatPanel.Children.Add(question);
        var actions = Row(attachQuestion, clearQuestionFiles, sendQuestion);
        Grid.SetRow(actions, 3); chatPanel.Children.Add(actions);
        var panel = new Grid { RowSpacing = 10 };
        panel.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        panel.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) });
        panel.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        Grid.SetRow(conversationStatus, 2); panel.Children.Add(conversationStatus);
        panel.Children.Add(Row(Action(L.T("查看报告"), () => { preview.Visibility = Visibility.Visible; chatPanel.Visibility = Visibility.Collapsed; return Task.CompletedTask; }),
            Action(L.T("对邮件提问"), () => { preview.Visibility = Visibility.Collapsed; chatPanel.Visibility = Visibility.Visible; return Task.CompletedTask; })));
        Grid.SetRow(preview, 1); panel.Children.Add(preview);
        Grid.SetRow(chatPanel, 1); panel.Children.Add(chatPanel);
        return panel;
    }
    (string text, List<string> files) Draft(string path)
    {
        if (!questionDrafts.TryGetValue(path, out var draft)) { draft = ("", new List<string>()); questionDrafts[path] = draft; }
        return draft;
    }
    void ResetConversation()
    {
        conversationPath = SelectedReport?.path;
        conversationHistory = default; conversationCompressed = false; chatMessages.Children.Clear();
        loadingQuestion = true;
        question.Text = conversationPath == null ? "" : Draft(conversationPath).text;
        loadingQuestion = false;
        UpdateConversationControls();
    }
    bool CurrentConversation(string path, long generation) => !exitRequested && generation == previewGeneration &&
        string.Equals(SelectedReport?.path, path, StringComparison.OrdinalIgnoreCase);
    async Task LoadConversation(string path, long generation)
    {
        var loadGeneration = ++conversationLoadGeneration;
        try {
            var result = await bridge.Call("chat_history", new { path });
            if (!CurrentConversation(path, generation) || loadGeneration != conversationLoadGeneration) return;
            SetConversation(result);
        } catch (Exception error) {
            conversationErrors[path] = error.Message;
            if (CurrentConversation(path, generation)) UpdateConversationControls();
        }
    }
    void SetConversation(JsonElement result)
    {
        conversationHistory = result.TryGetProperty("messages", out var messages) ? messages.Clone() : default;
        conversationCompressed = result.TryGetProperty("compressed", out var compressed) && compressed.ValueKind == JsonValueKind.True;
        RefreshConversationLanguage();
    }
    void RefreshConversationLanguage()
    {
        chatMessages.Children.Clear();
        if (conversationHistory.ValueKind == JsonValueKind.Array) foreach (var message in conversationHistory.EnumerateArray()) {
            var role = message.TryGetProperty("role", out var r) ? r.GetString() : "assistant";
            var heading = new TextBlock { FontFamily = MailTypography.Font, Text = L.T(role == "user" ? "我" : role == "system" ? "上下文摘要" : "邮件小秘书"),
                FontWeight = Microsoft.UI.Text.FontWeights.SemiBold };
            var body = new MarkdownReportView { FontFamily = MailTypography.Font, FontSize = 14 };
            body.Show(message.TryGetProperty("content", out var text) ? text.GetString() ?? "" : "", true);
            var card = Stack(heading, body);
            if (message.TryGetProperty("files", out var files) && files.ValueKind == JsonValueKind.Array) {
                var names = new List<string>();
                foreach (var file in files.EnumerateArray()) {
                    if (file.ValueKind == JsonValueKind.String) names.Add(Path.GetFileName(file.GetString() ?? ""));
                    else if (file.ValueKind == JsonValueKind.Object && file.TryGetProperty("name", out var name)) names.Add(name.GetString() ?? "");
                }
                card.Children.Add(new TextBlock { FontFamily = MailTypography.Font, Text = string.Join(" · ", names), TextWrapping = TextWrapping.Wrap, Opacity = .65 });
            }
            chatMessages.Children.Add(Card(card, 12));
        }
        if (chatMessages.Children.Count == 0) chatMessages.Children.Add(Note(L.T("针对这封邮件提问，聊天记录会自动保存。")));
        UpdateConversationControls();
        chatScroll.UpdateLayout(); chatScroll.ChangeView(null, chatScroll.ScrollableHeight, null);
    }
    void UpdateConversationControls()
    {
        var selected = conversationPath != null;
        var busy = selected && conversationBusy.Contains(conversationPath!);
        retryReport.IsEnabled = selected && !busy;
        attachQuestion.IsEnabled = selected && !busy;
        question.IsEnabled = selected && !busy;
        var draft = selected ? Draft(conversationPath!) : ("", new List<string>());
        clearQuestionFiles.IsEnabled = selected && !busy && draft.Item2.Count > 0;
        sendQuestion.IsEnabled = selected && !busy && (!string.IsNullOrWhiteSpace(question.Text) || draft.Item2.Count > 0);
        var names = new List<string>(); foreach (var file in draft.Item2) names.Add(Path.GetFileName(file));
        questionFiles.Text = string.Join(" · ", names);
        questionFiles.Visibility = names.Count == 0 ? Visibility.Collapsed : Visibility.Visible;
        conversationProgress.IsActive = busy;
        conversationStatus.Text = busy ? L.T("AI 正在处理，请稍候…") :
            selected && conversationErrors.TryGetValue(conversationPath!, out var error) ? L.T("操作失败：") + error :
            conversationCompressed ? L.T("已压缩较早的聊天记录，保留上下文继续对话。") : selected ? L.T("聊天记录自动保存；发送后会调用 AI。") : L.T("请先选择一封邮件。");
    }
    async Task AddQuestionFiles()
    {
        if (conversationPath == null || conversationBusy.Contains(conversationPath)) return;
        var path = conversationPath;
        var picker = new Windows.Storage.Pickers.FileOpenPicker();
        WinRT.Interop.InitializeWithWindow.Initialize(picker, WinRT.Interop.WindowNative.GetWindowHandle(this));
        picker.FileTypeFilter.Add("*");
        var picked = await picker.PickMultipleFilesAsync();
        if (exitRequested || !string.Equals(path, conversationPath, StringComparison.OrdinalIgnoreCase)) return;
        var draft = Draft(path);
        foreach (var file in picked) if (!draft.files.Contains(file.Path)) draft.files.Add(file.Path);
        questionDrafts[path] = draft; UpdateConversationControls();
    }
    async Task SendQuestion()
    {
        if (conversationPath == null || (string.IsNullOrWhiteSpace(question.Text) && Draft(conversationPath).files.Count == 0)) return;
        var path = conversationPath; var generation = previewGeneration;
        if (!conversationBusy.Add(path)) return;
        ++conversationLoadGeneration; // Do not let an older history read replace a newly sent answer.
        var draft = Draft(path); var sentText = question.Text; var sentFiles = draft.files.ToArray();
        conversationErrors.Remove(path); UpdateConversationControls();
        try {
            var result = await bridge.Call("chat_send", new { path, text = sentText, files = sentFiles });
            questionDrafts[path] = ("", new List<string>());
            if (!CurrentConversation(path, generation)) return;
            loadingQuestion = true; question.Text = ""; loadingQuestion = false;
            SetConversation(result);
        } catch (Exception error) { conversationErrors[path] = error.Message; }
        finally { conversationBusy.Remove(path); if (CurrentConversation(path, generation)) UpdateConversationControls(); }
    }
    async Task ConversationSelfTest(Action<bool, string> check)
    {
        if (fixture == null || reports.Items.Count == 0) throw new InvalidOperationException("Conversation test needs synthetic reports");
        reports.SelectedIndex = 0;
        var path = SelectedReport!.path;
        ResetConversation();
        await LoadConversation(path, previewGeneration);
        check(conversationPath == path && retryReport.IsEnabled, "Selected report enables re-analysis and restores its saved conversation");
        var initialLanguage = L.Code;
        foreach (var language in new[] { "zh", "en", "es" }) {
            await ChangeLanguage(language);
            await RetrySelectedReport();
            check(!conversationBusy.Contains(path) && preview.Text.Contains(language == "zh" ? "新邮件提醒" : language == "en" ? "New email" : "Correo nuevo") && !conversationErrors.ContainsKey(path),
                "Re-analysis uses the current " + language + " language through the actual bridge");
            question.Text = "Fixture question in " + language;
            await SendQuestion();
            var last = conversationHistory[conversationHistory.GetArrayLength() - 1].GetProperty("content").GetString() ?? "";
            check(last.Contains(language == "zh" ? "模拟回答" : language == "en" ? "Synthetic answer" : "Respuesta sintética"),
                "Multi-turn answers follow the current " + language + " language");
        }
        await ChangeLanguage(initialLanguage);
        var attached = Path.Combine(fixture, "question-attachment.txt");
        File.WriteAllText(attached, "Synthetic question attachment. No real mailbox, AI, or credentials.");
        questionDrafts[path] = ("Fixture question with an attachment", new List<string> { attached });
        question.Text = "Fixture question with an attachment";
        await SendQuestion();
        check(!conversationBusy.Contains(path) && !conversationErrors.ContainsKey(path) &&
            conversationHistory.ValueKind == JsonValueKind.Array && conversationHistory.GetArrayLength() >= 2,
            "Email question sends a synthetic attachment and renders user/assistant messages through the packaged worker");
        var count = conversationHistory.GetArrayLength();
        question.Text = "Fixture follow-up question";
        var sending = SendQuestion();
        var duplicate = SendQuestion();
        await Task.WhenAll(sending, duplicate);
        check(conversationHistory.GetArrayLength() == count + 2 && question.Text.Length == 0 && Draft(path).files.Count == 0,
            "Repeated send is deduplicated; multi-turn questions retain history and clear only the successful draft");
        var savedCount = conversationHistory.GetArrayLength();
        conversationHistory = default; chatMessages.Children.Clear();
        await LoadConversation(path, previewGeneration);
        check(conversationHistory.ValueKind == JsonValueKind.Array && conversationHistory.GetArrayLength() == savedCount,
            "Conversation history restores from the backend without an AI request");
        SetConversation(JsonSerializer.SerializeToElement(new { messages = conversationHistory, compressed = true }));
        check(conversationCompressed && conversationStatus.Text == L.T("已压缩较早的聊天记录，保留上下文继续对话。"),
            "Compressed context status is visible without exposing implementation details");
        questionDrafts[path] = ("Retry after error", new List<string> { Path.Combine(fixture, "missing-question-file.txt") });
        question.Text = "Retry after error";
        await SendQuestion();
        check(conversationErrors.ContainsKey(path) && question.Text == "Retry after error" && !conversationBusy.Contains(path),
            "Failed questions display errors and preserve the draft for retry");
        conversationErrors.Remove(path); questionDrafts[path] = ("", new List<string>()); question.Text = "";
        await LoadConversation(path, previewGeneration);
        var previousGeneration = previewGeneration;
        previewGeneration++;
        check(!CurrentConversation(path, previousGeneration), "Stale report responses cannot replace another email's view");
        previewGeneration = previousGeneration;
        preview.Visibility = Visibility.Visible; chatPanel.Visibility = Visibility.Collapsed;
    }
    async Task RetrySelectedReport()
    {
        if (conversationPath == null) return;
        var path = conversationPath; var generation = previewGeneration;
        if (!conversationBusy.Add(path)) return;
        conversationErrors.Remove(path); UpdateConversationControls();
        try {
            var result = await bridge.Call("report_retry", new { path });
            if (CurrentConversation(path, generation)) {
                preview.Show(result.GetProperty("text").GetString() ?? "", true);
                preview.Visibility = Visibility.Visible; chatPanel.Visibility = Visibility.Collapsed;
            }
        } catch (Exception error) { conversationErrors[path] = error.Message; }
        finally { conversationBusy.Remove(path); if (CurrentConversation(path, generation)) UpdateConversationControls(); }
    }
}

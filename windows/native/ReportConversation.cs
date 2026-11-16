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
    readonly TextBlock conversationHeading = new() { VerticalAlignment = VerticalAlignment.Center, FontFamily = MailTypography.Font };
    readonly Button restoreConversation = new() { Content = L.T("恢复对话"), IsEnabled = false, MinHeight = 24, Padding = new Thickness(8, 0, 8, 0) };
    readonly Button clearQuestionFiles = new() { Content = L.T("移除附件"), IsEnabled = false };
    readonly TextBox question = new() { Header = L.T("对邮件提问"), PlaceholderText = L.T("针对原邮件和附件提问，可继续追问或添加文件"),
        AcceptsReturn = true, TextWrapping = TextWrapping.Wrap, Height = 80, MinHeight = 60, MaxHeight = 80 };
    readonly TextBlock conversationStatus = new() { TextWrapping = TextWrapping.Wrap, IsTextSelectionEnabled = true };
    readonly StackPanel questionFileItems = new() { Orientation = Orientation.Horizontal, Spacing = 6 };
    readonly ScrollViewer questionFiles = new() { HorizontalScrollBarVisibility = ScrollBarVisibility.Auto,
        HorizontalScrollMode = ScrollMode.Enabled, VerticalScrollBarVisibility = ScrollBarVisibility.Disabled,
        VerticalScrollMode = ScrollMode.Disabled, MaxHeight = 34 };
    string questionFilesSignature = "";
    readonly HashSet<string> restoringConversations = new(StringComparer.OrdinalIgnoreCase);
    MarkdownReportView? streamingReply;
    string? streamingReplyPath;
    readonly Dictionary<string, (string question, string[] files, string partial)> pendingConversations = new(StringComparer.OrdinalIgnoreCase);
    readonly StackPanel chatMessages = new() { Spacing = 12 };
    readonly ScrollViewer chatScroll = new() { VerticalScrollBarVisibility = ScrollBarVisibility.Auto };
    readonly Grid chatPanel = new() { RowSpacing = 8 };
    readonly Grid conversationLayout = new() { RowSpacing = 4 };
    StackPanel conversationActions = null!;
    ReportPaneSplitter reportSplitter = null!;
    readonly ConversationBusyIndicator conversationProgress = new() { IsActive = false, Width = 20, Height = 20 };
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
        foreach (var control in new Control[] { retryReport, sendQuestion, attachQuestion, clearQuestionFiles, restoreConversation, question })
            control.FontFamily = MailTypography.Font;
        var chatHeader = new Grid();
        chatHeader.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        chatHeader.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        conversationHeading.Text = L.T("对邮件提问"); chatHeader.Children.Add(conversationHeading);
        Grid.SetColumn(restoreConversation, 1); chatHeader.Children.Add(restoreConversation);
        question.Header = chatHeader;
        Microsoft.UI.Xaml.Automation.AutomationProperties.SetAutomationId(restoreConversation, "mail-chat-restore");
        restoreConversation.Click += async (_, _) => await RestoreConversation();
        questionFiles.Content = questionFileItems;
        retryReport.Click += async (_, _) => await RetrySelectedReport();
        sendQuestion.Click += async (_, _) => await SendQuestion();
        question.KeyDown += async (_, e) => {
            if (!chatEnterToSendSetting.IsOn || e.Key != Windows.System.VirtualKey.Enter) return;
            if (Microsoft.UI.Input.InputKeyboardSource.GetKeyStateForCurrentThread(Windows.System.VirtualKey.Shift)
                .HasFlag(Windows.UI.Core.CoreVirtualKeyStates.Down)) return;
            e.Handled = true;
            if (sendQuestion.IsEnabled) await SendQuestion();
        };
        attachQuestion.Click += async (_, _) => await Guard(AddQuestionFiles);
        clearQuestionFiles.Click += (_, _) => {
            if (conversationPath == null || conversationBusy.Contains(conversationPath)) return;
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
        var actions = conversationActions = Row(attachQuestion, clearQuestionFiles, sendQuestion);
        Grid.SetRow(actions, 3); chatPanel.Children.Add(actions);
        var panel = conversationLayout;
        panel.RowDefinitions.Add(new RowDefinition { Height = new GridLength(3, GridUnitType.Star), MinHeight = 140 });
        panel.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        panel.RowDefinitions.Add(new RowDefinition { Height = new GridLength(2, GridUnitType.Star), MinHeight = 160 });
        panel.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        Grid.SetRow(conversationStatus, 3); panel.Children.Add(conversationStatus);
        panel.Children.Add(preview);
        reportSplitter = new ReportPaneSplitter(panel, 0, 2);
        reportSplitter.SetLabel(L.T("拖动调整报告与聊天区域"));
        Grid.SetRow(reportSplitter, 1); panel.Children.Add(reportSplitter);
        Grid.SetRow(chatPanel, 2); panel.Children.Add(chatPanel);
        panel.LayoutUpdated += (_, _) => FitConversationViewport();
        return panel;
    }
    void FitConversationViewport()
    {
        if (conversationLayout.RowDefinitions.Count < 3 || conversationActions == null) return;
        var height = conversationLayout.RowDefinitions[2].ActualHeight;
        if (height <= 0) return;
        // Grid star rows can retain a ScrollViewer's desired height. Bound the
        // history viewport explicitly so it cannot push the composer off screen.
        if (Math.Abs(chatPanel.MaxHeight - height) > .5 || double.IsInfinity(chatPanel.MaxHeight))
            chatPanel.MaxHeight = height;
        var filesHeight = questionFiles.Visibility == Visibility.Visible ? questionFiles.ActualHeight : 0;
        var historyHeight = Math.Max(0, height - question.ActualHeight - conversationActions.ActualHeight -
            filesHeight - chatPanel.RowSpacing * 3 - 4);
        if (Math.Abs(chatScroll.MaxHeight - historyHeight) > .5 || double.IsInfinity(chatScroll.MaxHeight))
            chatScroll.MaxHeight = historyHeight;
    }
    bool ConversationComposerVisible()
    {
        foreach (var control in new FrameworkElement[] { question, attachQuestion, clearQuestionFiles, sendQuestion }) {
            var origin = control.TransformToVisual(layout).TransformPoint(new Windows.Foundation.Point(0, 0));
            var local = control.TransformToVisual(conversationLayout).TransformPoint(new Windows.Foundation.Point(0, 0));
            if (control.ActualHeight <= 0 || origin.Y < 0 || origin.Y + control.ActualHeight > layout.ActualHeight ||
                local.Y < 0 || local.Y + control.ActualHeight > conversationLayout.ActualHeight)
                return false;
        }
        return true;
    }
    (string text, List<string> files) Draft(string path)
    {
        if (!questionDrafts.TryGetValue(path, out var draft)) { draft = ("", new List<string>()); questionDrafts[path] = draft; }
        return draft;
    }
    void ResetConversation()
    {
        streamingReply = null; streamingReplyPath = null;
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
    async Task RestoreConversation()
    {
        if (conversationPath == null) return;
        var path = conversationPath;
        var generation = previewGeneration;
        if (!conversationBusy.Add(path)) return;
        restoringConversations.Add(path); conversationErrors.Remove(path); UpdateConversationControls();
        try { await LoadConversation(path, generation); }
        finally {
            restoringConversations.Remove(path); conversationBusy.Remove(path);
            if (CurrentConversation(path, generation)) UpdateConversationControls();
        }
    }
    void RemoveQuestionFile(string path, string file)
    {
        if (conversationBusy.Contains(path)) return;
        var draft = Draft(path);
        draft.files.Remove(file); questionDrafts[path] = draft;
        if (string.Equals(path, conversationPath, StringComparison.OrdinalIgnoreCase)) UpdateConversationControls();
    }
    void RefreshQuestionFiles(string? path, List<string> files, bool busy)
    {
        // Typing must not rebuild focused controls or interrupt input composition.
        var signature = (path ?? "") + "\0" + busy + "\0" + string.Join("\0", files);
        if (questionFilesSignature == signature) return;
        questionFilesSignature = signature; questionFileItems.Children.Clear();
        foreach (var file in files) {
            var name = Path.GetFileName(file);
            var remove = new Button { Content = "×", MinWidth = 24, MinHeight = 24, Padding = new Thickness(4, 0, 4, 0),
                IsEnabled = path != null && !busy, FontFamily = MailTypography.Font };
            var capturedPath = path; var capturedFile = file;
            remove.Click += (_, _) => { if (capturedPath != null) RemoveQuestionFile(capturedPath, capturedFile); };
            Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(remove, L.T("移除附件") + " " + name);
            ToolTipService.SetToolTip(remove, L.T("移除附件") + " " + name);
            var row = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 4 };
            row.Children.Add(new TextBlock { Text = name, FontFamily = MailTypography.Font, MaxWidth = 180,
                TextTrimming = TextTrimming.CharacterEllipsis, VerticalAlignment = VerticalAlignment.Center });
            row.Children.Add(remove); ToolTipService.SetToolTip(row, file);
            questionFileItems.Children.Add(row);
        }
        questionFiles.Visibility = files.Count == 0 ? Visibility.Collapsed : Visibility.Visible;
    }
    void SetConversation(JsonElement result)
    {
        streamingReply = null; streamingReplyPath = null;
        conversationHistory = result.TryGetProperty("messages", out var messages) ? messages.Clone() : default;
        conversationCompressed = result.TryGetProperty("compressed", out var compressed) && compressed.ValueKind == JsonValueKind.True;
        RefreshConversationLanguage();
    }
    void RefreshConversationLanguage()
    {
        reportSplitter?.SetLabel(L.T("拖动调整报告与聊天区域"));
        conversationHeading.Text = L.T("对邮件提问"); restoreConversation.Content = L.T("恢复对话");
        questionFilesSignature = "";
        chatMessages.Children.Clear();
        if (conversationHistory.ValueKind == JsonValueKind.Array) foreach (var message in conversationHistory.EnumerateArray()) {
            var role = message.TryGetProperty("role", out var r) ? r.GetString() : "assistant";
            var heading = new TextBlock { FontFamily = MailTypography.Font, Text = L.T(role == "user" ? "我" : role == "system" ? "上下文摘要" : "邮件小秘书"),
                FontWeight = Microsoft.UI.Text.FontWeights.SemiBold };
            var body = new MarkdownReportView { FontFamily = MailTypography.Font, FontSize = 14, ContentSized = true };
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
            chatMessages.Children.Add(Card(card, 12, userMessage: role == "user"));
        }
        AppendPendingConversation();
        if (chatMessages.Children.Count == 0) chatMessages.Children.Add(Note(L.T("基于原邮件和实际附件提问，可添加文件；不会用总结报告代替原文。聊天记录自动保存。")));
        UpdateConversationControls();
        chatScroll.UpdateLayout(); chatScroll.ChangeView(null, chatScroll.ScrollableHeight, null);
    }
    void UpdateConversationControls()
    {
        var selected = conversationPath != null;
        var busy = selected && conversationBusy.Contains(conversationPath!);
        retryReport.IsEnabled = selected && !busy;
        restoreConversation.IsEnabled = selected && !busy;
        attachQuestion.IsEnabled = selected && !busy;
        question.IsEnabled = selected && !busy;
        var draft = selected ? Draft(conversationPath!) : ("", new List<string>());
        clearQuestionFiles.IsEnabled = selected && !busy && draft.Item2.Count > 0;
        sendQuestion.IsEnabled = selected && !busy && (!string.IsNullOrWhiteSpace(question.Text) || draft.Item2.Count > 0);
        RefreshQuestionFiles(conversationPath, draft.Item2, busy);
        question.Height = draft.Item2.Count == 0 ? 80 : 60;
        conversationProgress.IsActive = busy;
        conversationStatus.Text = selected && restoringConversations.Contains(conversationPath!) ? L.T("正在恢复对话…") :
            busy ? L.T("AI 正在处理，请稍候…") :
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
    void AppendPendingConversation()
    {
        streamingReply = null; streamingReplyPath = null;
        if (conversationPath == null || !pendingConversations.TryGetValue(conversationPath, out var pending)) return;
        var sentQuestion = new TextBlock { Text = pending.question, TextWrapping = TextWrapping.Wrap,
            IsTextSelectionEnabled = true, FontFamily = MailTypography.Font };
        var sent = Stack(new TextBlock { Text = L.T("我"), FontFamily = MailTypography.Font }, sentQuestion);
        if (pending.files.Length > 0) {
            var names = new List<string>(); foreach (var file in pending.files) names.Add(Path.GetFileName(file));
            sent.Children.Add(new TextBlock { Text = string.Join(" · ", names), TextWrapping = TextWrapping.Wrap,
                FontFamily = MailTypography.Font, Opacity = .65 });
        }
        streamingReply = new MarkdownReportView { ContentSized = true, FontFamily = MailTypography.Font, FontSize = 14 };
        streamingReply.Show(pending.partial, true);
        streamingReplyPath = conversationPath;
        chatMessages.Children.Add(Card(sent, 12, userMessage: true));
        chatMessages.Children.Add(Card(Stack(new TextBlock { Text = L.T("邮件小秘书"), FontFamily = MailTypography.Font }, streamingReply), 12));
    }
    void ReceiveChatPartial(JsonElement ev)
    {
        if (!ev.TryGetProperty("chat_path", out var path) || !ev.TryGetProperty("chat_partial", out var partial) ||
            path.ValueKind != JsonValueKind.String || partial.ValueKind != JsonValueKind.String) return;
        var key = path.GetString();
        if (key == null || !pendingConversations.TryGetValue(key, out var pending)) return;
        var text = partial.GetString() ?? "";
        if (pending.partial == text) return;
        pendingConversations[key] = (pending.question, pending.files, text);
        if (!string.Equals(key, conversationPath, StringComparison.OrdinalIgnoreCase) ||
            !string.Equals(streamingReplyPath, conversationPath, StringComparison.OrdinalIgnoreCase) || streamingReply == null) return;
        var follow = chatScroll.ScrollableHeight - chatScroll.VerticalOffset < 40;
        streamingReply.Show(text, true);
        if (follow) { chatScroll.UpdateLayout(); chatScroll.ChangeView(null, chatScroll.ScrollableHeight, null, true); }
    }
    async Task SendQuestion()
    {
        if (conversationPath == null || (string.IsNullOrWhiteSpace(question.Text) && Draft(conversationPath).files.Count == 0)) return;
        var path = conversationPath;
        if (!conversationBusy.Add(path)) return;
        ++conversationLoadGeneration; // Do not let an older history read replace a newly sent answer.
        var draft = Draft(path); var sentText = question.Text; var sentFiles = draft.files.ToArray();
        conversationErrors.Remove(path); UpdateConversationControls();
        try {
            pendingConversations[path] = (sentText, sentFiles, "");
            RefreshConversationLanguage();
            var result = await bridge.Call("chat_send", new { path, text = sentText, files = sentFiles });
            questionDrafts[path] = ("", new List<string>());
            pendingConversations.Remove(path);
            if (!CurrentConversation(path, previewGeneration)) return;
            loadingQuestion = true; question.Text = ""; loadingQuestion = false;
            SetConversation(result);
        } catch (Exception error) { conversationErrors[path] = error.Message; }
        finally {
            var hadPending = pendingConversations.Remove(path); conversationBusy.Remove(path);
            if (CurrentConversation(path, previewGeneration)) {
                if (hadPending) RefreshConversationLanguage(); else UpdateConversationControls();
            }
        }
    }
    async Task ConversationSelfTest(Action<bool, string> check)
    {
        var tableMessage = new MarkdownReportView { ContentSized = true };
        tableMessage.Show("# 一级标题\n## 二级标题\n\n- 列表项\n-- 子列表项\n\n> 引用内容\n\n| 项目 | 时间 |\n| --- | --- |\n| **午饭** | 12:00 |", true);
        check(tableMessage.HeadingCount == 2 && tableMessage.ListCount >= 1 && tableMessage.QuoteCount == 1 &&
            tableMessage.TableCount == 1 && tableMessage.BoldCount == 1,
            "Chat Markdown renderer preserves headings, nested lists, quotes, tables and inline formatting");
        check(tableMessage.Content is StackPanel, "Chat Markdown uses its content height without a nested scroll viewer");
        if (fixture == null || reports.Items.Count == 0) throw new InvalidOperationException("Conversation test needs synthetic reports");
        layout.UpdateLayout();
        check(preview.Visibility == Visibility.Visible && chatPanel.Visibility == Visibility.Visible && reportSplitter.IsLoaded,
            "Report and chat remain visible together with a native draggable divider");
        var originalUpper = conversationLayout.RowDefinitions[0].Height;
        var originalLower = conversationLayout.RowDefinitions[2].Height;
        try {
            reportSplitter.ResizeUpperPane(-1000000); layout.UpdateLayout(); FitConversationViewport(); layout.UpdateLayout();
            check(Math.Abs(conversationLayout.RowDefinitions[0].ActualHeight - 140) <= 1 &&
                conversationLayout.RowDefinitions[2].ActualHeight >= 159 && ConversationComposerVisible(),
                "Dragging the report divider upward preserves the report and chat minimum sizes");
            reportSplitter.ResizeUpperPane(1000000); layout.UpdateLayout(); FitConversationViewport(); layout.UpdateLayout();
            check(Math.Abs(conversationLayout.RowDefinitions[2].ActualHeight - 160) <= 1 &&
                conversationLayout.RowDefinitions[0].ActualHeight >= 139 && ConversationComposerVisible(),
                "Dragging the report divider downward preserves usable chat controls");
        }
        finally {
            conversationLayout.RowDefinitions[0].Height = originalUpper;
            conversationLayout.RowDefinitions[2].Height = originalLower;
            layout.UpdateLayout();
        }
        conversationProgress.IsActive = true;
        await Task.Delay(200);
        check(conversationProgress.IsLoaded && conversationProgress.Visibility == Visibility.Visible,
            "Native busy indicator renders and animates without loading a shared ProgressRing template");
        conversationProgress.IsActive = false;
        check(conversationProgress.Visibility == Visibility.Collapsed, "Busy indicator hides when processing ends");
        reports.SelectedIndex = 0;
        var path = SelectedReport!.path;
        ResetConversation();
        await LoadConversation(path, previewGeneration);
        check(conversationPath == path && retryReport.IsEnabled, "Selected report enables re-analysis and restores its saved conversation");
        var firstAttachment = Path.Combine(fixture, "first-draft.txt");
        var secondAttachment = Path.Combine(fixture, "second-draft.txt");
        var otherPath = path + ".other";
        questionDrafts[path] = ("Unsent input stays intact", new List<string> { firstAttachment, secondAttachment });
        questionDrafts[otherPath] = ("Other report draft", new List<string> { firstAttachment });
        question.Text = "Unsent input stays intact"; UpdateConversationControls();
        var firstChip = questionFileItems.Children[0];
        question.Text += " while typing";
        check(ReferenceEquals(firstChip, questionFileItems.Children[0]),
            "Typing does not rebuild attachment controls or interrupt composition");
        conversationBusy.Add(path); UpdateConversationControls(); RemoveQuestionFile(path, firstAttachment);
        check(Draft(path).files.Count == 2 && !restoreConversation.IsEnabled,
            "Attachment removal and restore cannot race an active AI request");
        conversationBusy.Remove(path); RemoveQuestionFile(path, firstAttachment);
        check(Draft(path).files.Count == 1 && Draft(path).files[0] == secondAttachment &&
            Draft(otherPath).files.Count == 1 && question.Text == "Unsent input stays intact while typing" &&
            questionFileItems.Children.Count == 1,
            "Removing one attachment preserves the remaining file, text and other report draft");
        questionDrafts[path] = ("", new List<string>()); question.Text = ""; questionDrafts.Remove(otherPath);
        pendingConversations[path] = ("Synthetic streaming question", Array.Empty<string>(), "");
        RefreshConversationLanguage();
        ReceiveChatPartial(JsonSerializer.SerializeToElement(new { chat_path = path, chat_partial = "# Live reply\n\n| A | B |\n| --- | --- |\n| 1 | 2 |" }));
        check(streamingReply != null && streamingReply.HeadingCount == 1 && streamingReply.TableCount == 1 &&
            streamingReply.Content is StackPanel, "Streaming chunks update one content-sized Markdown reply inside the conversation scroll area");
        SetConversation(JsonSerializer.SerializeToElement(new { messages = Array.Empty<object>(), compressed = false }));
        check(streamingReply != null && streamingReply.TableCount == 1,
            "Refreshing the conversation preserves an in-flight streamed reply");
        pendingConversations.Remove(path); RefreshConversationLanguage();
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
        questionDrafts[path] = ("Preserve this unfinished question", new List<string> { attached });
        question.Text = "Preserve this unfinished question";
        await RestoreConversation();
        check(conversationHistory.ValueKind == JsonValueKind.Array && conversationHistory.GetArrayLength() == savedCount &&
            question.Text == "Preserve this unfinished question" && Draft(path).files.Count == 1 && restoreConversation.IsEnabled,
            "Restore reloads saved history without AI while preserving the current question and attachments");
        questionDrafts[path] = ("", new List<string>()); question.Text = "";
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
        preview.Visibility = chatPanel.Visibility = Visibility.Visible;
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
                preview.Visibility = chatPanel.Visibility = Visibility.Visible;
            }
        } catch (Exception error) { conversationErrors[path] = error.Message; }
        finally { conversationBusy.Remove(path); if (CurrentConversation(path, generation)) UpdateConversationControls(); }
    }
}

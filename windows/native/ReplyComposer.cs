using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Windows.ApplicationModel.DataTransfer;

namespace BensonMail;

sealed partial class MainWindow
{
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
        var sent = false;
        var mailbox = new ComboBox { Header = L.T("发送邮箱"), HorizontalAlignment = HorizontalAlignment.Stretch };
        foreach (var profile in mailboxProfiles) mailbox.Items.Add(new ComboBoxItem { Content = JsonText(profile, "account"), Tag = JsonText(profile, "id") });
        mailbox.SelectedIndex = mailboxProfiles.FindIndex(profile => JsonText(profile, "id") == SelectedMailboxDraftId);
        if (mailbox.SelectedIndex < 0 && mailbox.Items.Count > 0) mailbox.SelectedIndex = 0;
        var send = new Button { Content = L.T("发送"), IsEnabled = false };
        var review = new Button { Content = L.T("确认发送"), Visibility = Visibility.Collapsed };
        var cancelReview = new Button { Content = L.T("取消"), Visibility = Visibility.Collapsed };
        var reviewContent = new StackPanel { Spacing = 8, Visibility = Visibility.Collapsed };
        var reviewedMailbox = ""; var reviewedRecipient = ""; var reviewedSubject = ""; var reviewedBody = "";
        var sending = false;
        var generating = false;
        void UpdateSend() => send.IsEnabled = !sent && !sending && !generating && !string.IsNullOrWhiteSpace(draftPath) &&
            !string.IsNullOrWhiteSpace(draft.Text) && !string.IsNullOrWhiteSpace(recipient.Text) && mailbox.SelectedIndex >= 0;
        void EndReview() {
            review.Visibility = cancelReview.Visibility = reviewContent.Visibility = Visibility.Collapsed;
            tone.IsEnabled = language.IsEnabled = instructions.IsEnabled = generate.IsEnabled = !sent && !sending;
            recipient.IsEnabled = subject.IsEnabled = draft.IsEnabled = mailbox.IsEnabled = !sent && !sending;
            saveDraft.IsEnabled = !sent && !sending && draftPath.Length > 0;
            UpdateSend();
        }
        var copy = new Button { Content = L.T("复制草稿"), IsEnabled = false };
        generate.Click += async (_, _) => {
            generating = true; generate.IsEnabled = false; saveDraft.IsEnabled = false; UpdateSend(); status.Text = L.T("正在生成草稿…");
            try {
                var result = await Assistant("reply_draft", new { path = report.path, instructions = instructions.Text,
                    tone = new[] { "formal", "friendly", "brief" }[Math.Max(0, tone.SelectedIndex)],
                    language = new[] { "auto", "zh", "en", "es" }[Math.Max(0, language.SelectedIndex)] });
                draft.Text = JsonText(result, "draft"); copy.IsEnabled = draft.Text.Length > 0;
                recipient.Text = JsonText(result, "recipient"); subject.Text = JsonText(result, "subject");
                draftPath = JsonText(result, "draft_path", JsonText(result, "path")); saveDraft.IsEnabled = draftPath.Length > 0;
                status.Text = L.T("收件人：") + JsonText(result, "recipient") + "\n" + L.T("主题：") + JsonText(result, "subject") + "\n" +
                    L.T("草稿未发送。请核对收件人、日期、金额和承诺。");
            } catch (Exception error) { status.Text = L.T(error.Message); }
            finally { generating = false; generate.IsEnabled = !sent; saveDraft.IsEnabled = draftPath.Length > 0 && !sent; UpdateSend(); }
        };
        saveDraft.Click += async (_, _) => {
            saveDraft.IsEnabled = false;
            try { await Assistant("draft_save", new { draft_path = draftPath, draft = draft.Text, recipient = recipient.Text, subject = subject.Text }); status.Text = L.T("本地草稿已保存，尚未发送。"); }
            catch (Exception error) { status.Text = L.T(error.Message); }
            finally { saveDraft.IsEnabled = true; }
        };
        copy.Click += (_, _) => { var data = new DataPackage(); data.SetText(draft.Text); Clipboard.SetContent(data); status.Text = L.T("草稿已复制，尚未发送。"); };
        draft.TextChanged += (_, _) => UpdateSend(); recipient.TextChanged += (_, _) => UpdateSend();
        mailbox.SelectionChanged += (_, _) => UpdateSend();
        cancelReview.Click += (_, _) => EndReview();
        send.Click += (_, _) => {
            if (!send.IsEnabled || mailbox.SelectedItem is not ComboBoxItem selected) return;
            reviewedMailbox = selected.Tag as string ?? "";
            reviewedRecipient = recipient.Text; reviewedSubject = subject.Text; reviewedBody = draft.Text;
            reviewContent.Children.Clear();
            reviewContent.Children.Add(Heading(L.T("确认发送邮件")));
            reviewContent.Children.Add(Note(L.T("你确定发送以下内容给") + reviewedRecipient + L.T("吗？")));
            reviewContent.Children.Add(Note(L.T("发件邮箱") + "：" + selected.Content));
            reviewContent.Children.Add(Note(L.T("收件邮箱") + "：" + reviewedRecipient));
            reviewContent.Children.Add(Note(L.T("主题") + "：" + reviewedSubject));
            reviewContent.Children.Add(new TextBlock { Text = reviewedBody, TextWrapping = TextWrapping.Wrap, IsTextSelectionEnabled = true });
            review.Visibility = cancelReview.Visibility = reviewContent.Visibility = Visibility.Visible;
            tone.IsEnabled = language.IsEnabled = instructions.IsEnabled = generate.IsEnabled = false;
            recipient.IsEnabled = subject.IsEnabled = draft.IsEnabled = mailbox.IsEnabled = saveDraft.IsEnabled = send.IsEnabled = false;
        };
        review.Click += async (_, _) => {
            if (sending || sent || reviewedMailbox.Length == 0) return;
            sending = true; review.IsEnabled = cancelReview.IsEnabled = false; status.Text = L.T("正在发送…");
            try {
                var saved = await Assistant("draft_save", new { draft_path = draftPath, draft = reviewedBody, recipient = reviewedRecipient, subject = reviewedSubject });
                draftPath = JsonText(saved, "path", draftPath);
                var result = await Assistant("reply_send", new { draft_path = draftPath, draft = reviewedBody,
                    recipient = reviewedRecipient, subject = reviewedSubject, mailbox_id = reviewedMailbox, confirmed = true });
                sent = result.TryGetProperty("sent", out var delivered) && delivered.ValueKind == JsonValueKind.True;
                if (!sent) throw new InvalidOperationException(L.T("发送失败，请检查邮箱设置。"));
                send.Content = L.T("邮件已发送");
                status.Text = result.TryGetProperty("draft_status_saved", out var persisted) && persisted.ValueKind == JsonValueKind.False
                    ? L.T("邮件已发送，但本机草稿状态保存失败；请检查已发送邮件。") : L.T("邮件已发送");
            } catch (Exception error) { status.Text = L.T(error.Message); }
            finally { sending = false; review.IsEnabled = cancelReview.IsEnabled = true; EndReview(); }
        };
        var dialog = new ContentDialog { XamlRoot = layout.XamlRoot, Title = L.T("回复"), CloseButtonText = L.T("关闭"),
            Content = Scroll(Stack(tone, language, instructions, Row(generate, copy, saveDraft), recipient, subject, draft, mailbox, send, reviewContent, Row(review, cancelReview), status)) };
        dialog.Closing += (_, args) => { if (sending) args.Cancel = true; };
        await dialog.ShowAsync();
    }
}

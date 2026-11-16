using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Windows.ApplicationModel.DataTransfer;

namespace BensonMail;

sealed partial class MainWindow
{
    static string OriginalLabel(string zh, string en, string es) => L.Bootstrap(zh, en, es);
    static bool HasOriginalBody(JsonElement original) => original.TryGetProperty("available", out var available) &&
        available.ValueKind == JsonValueKind.True && !string.IsNullOrWhiteSpace(JsonText(original, "body"));
    static string OriginalMissing() => OriginalLabel("本地没有保存这封邮件的原文。AI 总结报告不能代替原文。",
        "The original email body was not saved locally. The AI report cannot substitute for it.",
        "El cuerpo original no se guardó localmente. El informe de IA no lo sustituye.");
    async Task CopyOriginalMail()
    {
        if (SelectedReport is not Report report) return;
        var original = await bridge.Call("read_original", new { path = report.path });
        if (!HasOriginalBody(original)) { detail.Text = OriginalMissing(); return; }
        var data = new DataPackage(); data.SetText(JsonText(original, "body")); Clipboard.SetContent(data);
        detail.Text = OriginalLabel("原文已复制。", "Original email copied.", "Se copió el correo original.");
    }
    async Task ShowOriginalMail()
    {
        if (SelectedReport is not Report report) return;
        var original = await bridge.Call("read_original", new { path = report.path });
        var content = Stack(Heading(JsonText(original, "title", report.title)));
        var sender = JsonText(original, "sender", report.sender);
        var account = JsonText(original, "account", report.account);
        if (sender.Length > 0) content.Children.Add(Note(OriginalLabel("发件人", "Sender", "Remitente") + ": " + sender));
        if (account.Length > 0) content.Children.Add(Note(OriginalLabel("邮箱", "Mailbox", "Buzón") + ": " + account));
        if (report.time.Length > 0) content.Children.Add(Note(report.time));
        if (original.TryGetProperty("attachments", out var attachments) && attachments.ValueKind == JsonValueKind.Array && attachments.GetArrayLength() > 0) {
            content.Children.Add(Heading(OriginalLabel("附件", "Attachments", "Adjuntos")));
            foreach (var attachment in attachments.EnumerateArray()) content.Children.Add(Note(attachment.GetString() ?? ""));
        }
        content.Children.Add(new TextBlock { Text = HasOriginalBody(original) ? JsonText(original, "body") : OriginalMissing(),
            FontFamily = MailTypography.Font, TextWrapping = TextWrapping.Wrap, IsTextSelectionEnabled = true });
        var copy = new Button { Content = OriginalLabel("复制原文", "Copy original", "Copiar original"), IsEnabled = HasOriginalBody(original) };
        copy.Click += (_, _) => { var data = new DataPackage(); data.SetText(JsonText(original, "body")); Clipboard.SetContent(data); };
        content.Children.Insert(1, copy);
        await new ContentDialog { XamlRoot = layout.XamlRoot, Title = OriginalLabel("原文", "Original email", "Correo original"),
            Content = Scroll(content), CloseButtonText = L.T("关闭"), MinWidth = 420, MaxWidth = 900 }.ShowAsync();
    }
    async Task OriginalMailSelfTest(Action<bool, string> check)
    {
        if (SelectedReport is not Report report) throw new InvalidOperationException("Original-mail fixture report missing");
        var original = await bridge.Call("read_original", new { path = report.path });
        check(HasOriginalBody(original) && JsonText(original, "body").Contains("请检查合同正文"),
            "Original-mail action loads saved incoming body instead of generated report text without contacting AI");
        check(original.TryGetProperty("attachments", out var attachments) && attachments.GetArrayLength() == 1 &&
            attachments[0].GetString() == "合同.pdf", "Original-mail view receives attachment names without loading their files");
        using var missing = JsonDocument.Parse("{\"available\":false,\"body\":\"\",\"attachments\":[]}");
        check(!HasOriginalBody(missing.RootElement), "Original-mail copy stays disabled when local original is missing");
    }

}

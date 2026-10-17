using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text.Json;
using System.Text.RegularExpressions;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace BensonMail;

internal static class L
{
    internal static string Code { get; private set; } = "zh";
    internal static string Locale => Code == "zh" ? "zh-CN" : "en-US";
    static readonly Dictionary<string, string> exact = new();
    static readonly Dictionary<string, string> originals = new();
    static readonly List<(Regex pattern, string english)> templates = new();
    internal static string Detect(string name) => name.StartsWith("zh", StringComparison.OrdinalIgnoreCase) ? "zh" : "en";
    internal static void Initialize()
    {
        using var stream = typeof(L).Assembly.GetManifestResourceStream("BensonMail.ui-en.json")!;
        using var catalog = JsonDocument.Parse(stream);
        foreach (var item in catalog.RootElement.GetProperty("exact").EnumerateObject()) exact[item.Name] = item.Value.GetString()!;
        foreach (var row in catalog.RootElement.GetProperty("templates").EnumerateArray())
            templates.Add((new Regex(row.GetProperty("pattern").GetString()!, RegexOptions.Singleline), row.GetProperty("en").GetString()!));
        Code = Detect(CultureInfo.CurrentUICulture.Name);
        try {
            var path = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "BensonMail", "config.json");
            if (File.Exists(path)) { using var config = JsonDocument.Parse(File.ReadAllText(path));
                if (config.RootElement.TryGetProperty("ui_language", out var language) && language.GetString() is "zh" or "en") Code = language.GetString()!; }
        } catch { }
        if (Array.IndexOf(Program.Args, "--self-test") >= 0 || Array.IndexOf(Program.Args, "--uninstall-ui-test") >= 0) Code = "zh";
        var index = Array.IndexOf(Program.Args, "--ui-language");
        if (index >= 0 && index + 1 < Program.Args.Length && Program.Args[index + 1] is "zh" or "en") Code = Program.Args[index + 1];
    }
    internal static void Select(string code) { if (code is "zh" or "en") Code = code; }
    internal static string T(string? value)
    {
        if (value == null) return "";
        if (originals.TryGetValue(value, out var original)) value = original;
        if (Code != "en") return value;
        string? translated = null;
        if (exact.TryGetValue(value, out var found)) translated = found;
        else foreach (var (pattern, english) in templates) {
            var match = pattern.Match(value);
            if (!match.Success) continue;
            translated = Regex.Replace(english, @"\{(\d+)\}", slot => {
                var n = int.Parse(slot.Groups[1].Value) + 1;
                return n < match.Groups.Count ? match.Groups[n].Value : slot.Value;
            });
            break;
        }
        if (translated == null) return value;
        originals[translated] = value;
        return translated;
    }
    // Only application-owned labels. Never walk editable inputs or report contents.
    internal static void Apply(UIElement? element, params UIElement[] excluded)
    {
        if (element == null || Array.IndexOf(excluded, element) >= 0) return;
        if (element is FrameworkElement frame) frame.Language = Locale;
        switch (element) {
            case TextBox box: box.Header = box.Header is string h ? T(h) : box.Header; box.PlaceholderText = T(box.PlaceholderText); return;
            case PasswordBox box: box.Header = box.Header is string h ? T(h) : box.Header; box.PlaceholderText = T(box.PlaceholderText); return;
            case CalendarDatePicker date: date.Header = date.Header is string h ? T(h) : date.Header; date.PlaceholderText = T(date.PlaceholderText); return;
            case ToggleSwitch toggle: toggle.Header = toggle.Header is string h ? T(h) : toggle.Header; toggle.OnContent = toggle.OnContent is string on ? T(on) : toggle.OnContent; toggle.OffContent = toggle.OffContent is string off ? T(off) : toggle.OffContent; return;
            case ComboBox combo:
                combo.Header = combo.Header is string header ? T(header) : combo.Header;
                var selected = combo.SelectedIndex;
                // Updating the collection raises selection events; caller suppresses their side effects.
                for (var i = 0; i < combo.Items.Count; i++) if (combo.Items[i] is string item) combo.Items[i] = T(item);
                combo.SelectedIndex = selected; return;
            case TextBlock text: text.Text = T(text.Text); return;
            case Panel panel: foreach (var child in panel.Children) Apply(child, excluded); return;
            case Border border: Apply(border.Child, excluded); return;
            case ScrollViewer scroll: Apply(scroll.Content as UIElement, excluded); return;
            case ListView list: foreach (var item in list.Items) if (item is UIElement child) Apply(child, excluded); return;
            case ContentControl content:
                if (content.Content is string label) content.Content = T(label);
                else Apply(content.Content as UIElement, excluded);
                return;
        }
    }
}

using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Text.RegularExpressions;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace BensonMail;

internal static class L
{
    internal static string Code { get; private set; } = "zh";
    internal static string Locale => Code == "zh" ? "zh-CN" : Code == "es" ? "es-ES" : "en-US";
    static readonly Dictionary<string, string> exact = new();
    static readonly Dictionary<string, string> originals = new() {
        ["Email Assistant"] = "邮件小秘书", ["Asistente de correo electrónico"] = "邮件小秘书",
        ["Uninstall Email Assistant"] = "卸载邮件小秘书", ["Desinstalar Asistente de correo electrónico"] = "卸载邮件小秘书"
    };
    static readonly List<(Regex pattern, string english)> templates = new();
    sealed class LabelSource
    {
        internal readonly Dictionary<string, (string source, string displayed)> Properties = new();
    }
    static readonly ConditionalWeakTable<DependencyObject, LabelSource> sources = new();
    static readonly Dictionary<string, Dictionary<string, string>> fallbackExact = new();
    static readonly Dictionary<string, List<(Regex pattern, string english)>> fallbackTemplates = new();
    static L()
    {
        foreach (var code in new[] { "en", "es" }) {
            var labels = new Dictionary<string, string>();
            var patterns = new List<(Regex pattern, string english)>();
            using var stream = Assembly.GetExecutingAssembly().GetManifestResourceStream("BensonMail.ui-" + code + ".json")
                ?? throw new InvalidDataException("Missing built-in interface labels: " + code);
            using var document = JsonDocument.Parse(stream);
            foreach (var item in document.RootElement.GetProperty("exact").EnumerateObject()) labels[item.Name] = item.Value.GetString()!;
            foreach (var row in document.RootElement.GetProperty("templates").EnumerateArray())
                patterns.Add((new Regex(row.GetProperty("pattern").GetString()!, RegexOptions.Singleline, TimeSpan.FromMilliseconds(100)), row.GetProperty("en").GetString()!));
            fallbackExact[code] = labels;
            fallbackTemplates[code] = patterns;
        }
    }
    internal static string Detect(string name) => name.StartsWith("zh", StringComparison.OrdinalIgnoreCase) ? "zh" : name.StartsWith("es", StringComparison.OrdinalIgnoreCase) ? "es" : "en";
    internal static string? FixtureHome { get; set; }
    internal static string DataHome => FixtureHome ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "BensonMail");
    internal static IEnumerable<string> PackPaths(string code)
    {
        // The CI fixture directory is only honored by explicit synthetic test entry points.
        // A normal launch cannot replace the authenticated production language source via an environment variable.
        var fixtureMode = Array.IndexOf(Program.Args, "--self-test") >= 0 || Array.IndexOf(Program.Args, "--uninstall-ui-test") >= 0 || Array.IndexOf(Program.Args, "--fixture") >= 0;
        if (fixtureMode && Environment.GetEnvironmentVariable("BENSON_MAIL_TEST_LANGUAGE_PACKS") is string fixturePacks && Path.IsPathFullyQualified(fixturePacks))
            yield return Path.Combine(fixturePacks, code + ".json");
        if (FixtureHome != null) yield return Path.Combine(FixtureHome, "languages", code + ".json");
        yield return Path.Combine(DataHome, "languages", code + ".json");
        yield return Path.Combine(AppContext.BaseDirectory, "languages", code + ".json");
        var index = Array.IndexOf(Program.Args, "--uninstall-worker");
        if (index >= 0 && index + 1 < Program.Args.Length) yield return Path.Combine(Program.Args[index + 1], "languages", code + ".json");
    }
    internal static bool TryLoad(string code, bool activate = false)
    {
        if (code is not ("zh" or "en" or "es")) return false;
        foreach (var path in PackPaths(code)) try {
            var info = new FileInfo(path);
            if (!info.Exists || info.Length < 2 || info.Length > 8 * 1024 * 1024) continue;
            using var catalog = JsonDocument.Parse(File.ReadAllText(path));
            var root = catalog.RootElement;
            if (root.GetProperty("schema_version").GetInt32() != 1 || root.GetProperty("language").GetString() != code || root.GetProperty("platform").GetString() != "windows") continue;
            var nextExact = new Dictionary<string, string>();
            var nextTemplates = new List<(Regex pattern, string english)>();
            foreach (var item in root.GetProperty("exact").EnumerateObject()) {
                var translated = item.Value.GetString();
                if (string.IsNullOrWhiteSpace(translated)) throw new InvalidDataException("Empty language label");
                nextExact[item.Name] = translated;
            }
            if (code != "zh" && nextExact.Count == 0) continue;
            foreach (var row in root.GetProperty("templates").EnumerateArray()) nextTemplates.Add((new Regex(row.GetProperty("pattern").GetString()!, RegexOptions.Singleline, TimeSpan.FromMilliseconds(100)), row.GetProperty("en").GetString()!));
            _ = root.GetProperty("guides").GetProperty("mail_account").GetString();
            if (activate) {
                exact.Clear(); templates.Clear();
                foreach (var pair in nextExact) exact[pair.Key] = pair.Value;
                templates.AddRange(nextTemplates); Code = code;
            }
            return true;
        } catch { }
        return false;
    }
    internal static void Initialize()
    {
        Code = Detect(CultureInfo.CurrentUICulture.Name);
        try {
            var initial = File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "installed-language.txt")).Trim();
            if (initial is "zh" or "en" or "es") Code = initial;
        } catch { }
        try {
            var path = Path.Combine(DataHome, "config.json");
            if (File.Exists(path)) { using var config = JsonDocument.Parse(File.ReadAllText(path));
                if (config.RootElement.TryGetProperty("ui_language", out var language) && language.GetString() is "zh" or "en" or "es") Code = language.GetString()!; }
        } catch { }
        if (Array.IndexOf(Program.Args, "--self-test") >= 0 || Array.IndexOf(Program.Args, "--uninstall-ui-test") >= 0) Code = "zh";
        var index = Array.IndexOf(Program.Args, "--ui-language");
        if (index >= 0 && index + 1 < Program.Args.Length && Program.Args[index + 1] is "zh" or "en" or "es") Code = Program.Args[index + 1];
        TryLoad(Code, true);
    }
    internal static bool Select(string code) => TryLoad(code, true);
    internal static string Bootstrap(string zh, string en, string es) => Code == "zh" ? zh : Code == "es" ? es : en;
    internal static string GuidePath(string name)
    {
        foreach (var path in PackPaths(Code)) try {
            using var doc = JsonDocument.Parse(File.ReadAllText(path));
            var text = doc.RootElement.GetProperty("guides").GetProperty(name).GetString()!;
            var destination = Path.Combine(DataHome, "guides", "Mail-account-setup-" + Code + ".txt");
            Directory.CreateDirectory(Path.GetDirectoryName(destination)!); File.WriteAllText(destination, text);
            return destination;
        } catch { }
        return Path.Combine(AppContext.BaseDirectory, "Mail-account-setup-" + Code + ".txt");
    }
    internal static string T(string? value)
    {
        if (value == null) return "";
        if (originals.TryGetValue(value, out var original)) value = original;
        else {
            // Status lines concatenate an owned prefix with paths, versions or
            // technical diagnostics. Reverse only that prefix, preserving data.
            string? prefix = null, sourcePrefix = null;
            foreach (var pair in originals)
                if (pair.Value.EndsWith("：", StringComparison.Ordinal) &&
                    value.StartsWith(pair.Key, StringComparison.Ordinal) &&
                    (prefix == null || pair.Key.Length > prefix.Length)) {
                    prefix = pair.Key; sourcePrefix = pair.Value;
                }
            if (prefix != null) value = sourcePrefix + value[prefix.Length..];
        }
        if (Code == "zh") return value;
        if (value == "邮件小秘书") return Code == "es" ? "Asistente de correo electrónico" : "Email Assistant";
        if (value == "卸载邮件小秘书") return Code == "es" ? "Desinstalar Asistente de correo electrónico" : "Uninstall Email Assistant";
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
        // Keep update recovery usable with a language pack downloaded by an older release.
        if (translated == null && value == "前往 GitHub 下载最新版")
            translated = Bootstrap(value, "Download the latest version from GitHub", "Descargar la última versión desde GitHub");
        if (translated == null && fallbackExact.TryGetValue(Code, out var builtIn) && builtIn.TryGetValue(value, out var fallback)) translated = fallback;
        if (translated == null && fallbackTemplates.TryGetValue(Code, out var patterns)) foreach (var (pattern, replacement) in patterns) {
            var match = pattern.Match(value);
            if (!match.Success) continue;
            translated = Regex.Replace(replacement, @"\{(\d+)\}", slot => {
                var n = int.Parse(slot.Groups[1].Value) + 1;
                return n < match.Groups.Count ? match.Groups[n].Value : slot.Value;
            });
            break;
        }
        if (translated == null) translated = SenderPolicyLocalization.Translate(value, Code);
        if (translated == null && (Program.Uninstall || Array.IndexOf(Program.Args, "--uninstall-ui-test") >= 0))
            translated = UninstallLocalization.Translate(value, Code);
        if (translated == null) {
            // These prefixes are often combined by the caller rather than a
            // format template, so translate their app-owned part separately.
            foreach (var pair in exact)
                if (pair.Key.EndsWith("：", StringComparison.Ordinal) && value.StartsWith(pair.Key, StringComparison.Ordinal)) {
                    translated = pair.Value + value[pair.Key.Length..]; break;
                }
            if (translated == null && fallbackExact.TryGetValue(Code, out var prefixLabels)) foreach (var pair in prefixLabels)
                if (pair.Key.EndsWith("：", StringComparison.Ordinal) && value.StartsWith(pair.Key, StringComparison.Ordinal)) {
                    translated = pair.Value + value[pair.Key.Length..]; break;
                }
        }
        if (translated == null) return value;
        originals[translated] = value;
        return translated;
    }
    static string Property(DependencyObject owner, string name, string value)
    {
        var properties = sources.GetValue(owner, _ => new LabelSource()).Properties;
        // Keep the exact source for each label. Different Chinese labels can share
        // one English/Spanish translation; a global reverse map alone loses them.
        var source = properties.TryGetValue(name, out var previous) && previous.displayed == value
            ? previous.source : originals.TryGetValue(value, out var original) ? original : value;
        var displayed = T(source);
        properties[name] = (source, displayed);
        return displayed;
    }
    // Only application-owned labels. Never walk editable inputs or report contents.
    internal static void Apply(UIElement? element, params UIElement[] excluded)
    {
        if (element == null || Array.IndexOf(excluded, element) >= 0) return;
        if (element is FrameworkElement frame) frame.Language = Locale;
        switch (element) {
            case TextBox box: box.Header = box.Header is string h ? Property(box, "Header", h) : box.Header; box.PlaceholderText = Property(box, "Placeholder", box.PlaceholderText); return;
            case PasswordBox box: box.Header = box.Header is string passwordHeader ? Property(box, "Header", passwordHeader) : box.Header; box.PlaceholderText = Property(box, "Placeholder", box.PlaceholderText); return;
            case CalendarDatePicker date: date.Header = date.Header is string dateHeader ? Property(date, "Header", dateHeader) : date.Header; date.PlaceholderText = Property(date, "Placeholder", date.PlaceholderText); return;
            case ToggleSwitch toggle: toggle.Header = toggle.Header is string toggleHeader ? Property(toggle, "Header", toggleHeader) : toggle.Header; toggle.OnContent = toggle.OnContent is string on ? Property(toggle, "On", on) : toggle.OnContent; toggle.OffContent = toggle.OffContent is string off ? Property(toggle, "Off", off) : toggle.OffContent; return;
            case ComboBox combo:
                combo.Header = combo.Header is string header ? Property(combo, "Header", header) : combo.Header;
                var selected = combo.SelectedIndex;
                // Updating the collection raises selection events; caller suppresses their side effects.
                for (var i = 0; i < combo.Items.Count; i++) if (combo.Items[i] is string item) combo.Items[i] = Property(combo, "Item" + i, item);
                combo.SelectedIndex = selected; return;
            case TextBlock text: text.Text = Property(text, "Text", text.Text); return;
            case Panel panel: foreach (var child in panel.Children) Apply(child, excluded); return;
            case Border border: Apply(border.Child, excluded); return;
            case ScrollViewer scroll: Apply(scroll.Content as UIElement, excluded); return;
            case ListView list:
                if (list.Header is string listHeader) list.Header = Property(list, "Header", listHeader);
                foreach (var item in list.Items) if (item is UIElement child) Apply(child, excluded); return;
            case ContentControl content:
                if (content.Content is string label) content.Content = Property(content, "Content", label);
                else Apply(content.Content as UIElement, excluded);
                return;
        }
    }
}

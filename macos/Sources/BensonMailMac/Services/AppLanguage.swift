import SwiftUI
import AppKit

/// Selects the UI and future report language; existing email content, reports and paths stay intact.
final class AppLanguage: ObservableObject {
    static let shared = AppLanguage()
    @Published private(set) var code: String
    private let exact: [String: String]
    private let templates: [(NSRegularExpression, [String], String)]
    static func detect(_ preferred: [String]) -> String {
        preferred.first?.lowercased().hasPrefix("zh") == true ? "zh" : "en"
    }
    private init() {
        let args = CommandLine.arguments
        let fixture = args.firstIndex(of: "--fixture").flatMap { $0 + 1 < args.count ? args[$0 + 1] : nil }
        let base = fixture.map { URL(fileURLWithPath: $0) } ?? FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/BensonMail")
        let saved = (try? Data(contentsOf: base.appendingPathComponent("settings.json"))).flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String: Any] }
        if let i = args.firstIndex(of: "--ui-language"), i + 1 < args.count, ["zh", "en"].contains(args[i + 1]) { code = args[i + 1] }
        else if args.contains("--self-test") { code = "zh" }
        else if let value = saved?["ui_language"] as? String, ["zh", "en"].contains(value) { code = value }
        else { code = Self.detect(Locale.preferredLanguages) }
        let catalog = Bundle.main.url(forResource: "ui-en", withExtension: "json")
            .flatMap { try? Data(contentsOf: $0) }.flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String: Any] } ?? [:]
        exact = catalog["exact"] as? [String: String] ?? [:]
        templates = (catalog["templates"] as? [[String: Any]] ?? []).compactMap { row in
            guard let pattern = row["pattern"] as? String, let regex = try? NSRegularExpression(pattern: pattern, options: .dotMatchesLineSeparators),
                  let parts = row["parts"] as? [String], let en = row["en"] as? String else { return nil }
            return (regex, parts, en)
        }
    }
    func translate(_ text: String) -> String {
        guard code == "en" else { return text }
        if let value = exact[text] { return value }
        if text.contains("邮箱连接失败："), text.contains("\n服务器："), text.contains("\n阶段：") {
            return text.components(separatedBy: "\n").map { line in
                if let marker = line.range(of: "邮箱连接失败：") {
                    let hint = String(line[marker.upperBound...])
                    return String(line[..<marker.lowerBound]) + "Email connection failed: " + (exact[hint] ?? hint)
                }
                for (source, english) in [("服务器：", "Server: "), ("阶段：", "Stage: "), ("具体原因：", "Details: ")] where line.hasPrefix(source) {
                    let value = String(line.dropFirst(source.count))
                    return english + (exact[value] ?? value).replacingOccurrences(of: "[已隐藏凭据]", with: "[credentials hidden]")
                }
                return line
            }.joined(separator: "\n")
        }
        for (regex, _, english) in templates {
            guard let match = regex.firstMatch(in: text, range: NSRange(text.startIndex..., in: text)) else { continue }
            var value = english
            // Replace from the end so inserted user text cannot be treated as another placeholder.
            let placeholders = try! NSRegularExpression(pattern: #"\{(\d+)\}"#)
            for slot in placeholders.matches(in: english, range: NSRange(english.startIndex..., in: english)).reversed() {
                guard let numberRange = Range(slot.range(at: 1), in: english), let number = Int(english[numberRange]),
                      number + 1 < match.numberOfRanges, let capture = Range(match.range(at: number + 1), in: text),
                      let target = Range(slot.range, in: value) else { continue }
                value.replaceSubrange(target, with: text[capture])
            }
            return value
        }
        return text
    }
    @MainActor func select(_ value: String) {
        guard ["zh", "en"].contains(value), value != code else { return }
        let store = MailStore.shared
        let old = store.settings.ui_language
        store.settings.ui_language = value
        do {
            try store.save()
            code = value
            DispatchQueue.main.async { MailHelp.refreshTitle() }
            for window in NSApp.windows where ["邮件小秘书", "Mail Secretary"].contains(window.title) { window.title = T("邮件小秘书") }
        } catch { store.settings.ui_language = old; store.problem = "语言设置保存失败：" + error.localizedDescription }
    }
}
func T(_ text: String) -> String { AppLanguage.shared.translate(text) }

struct LanguageSettings: View {
    @ObservedObject private var language = AppLanguage.shared
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Picker(T("界面语言"), selection: Binding(get: { language.code }, set: { language.select($0) })) {
                Text("中文").tag("zh")
                Text("English").tag("en")
            }.accessibilityIdentifier("ui-language")
            Text(T("语言更改立即生效，下次打开时保留。")).font(.caption).foregroundStyle(.secondary)
        }
    }
}

import AppKit
import SwiftUI
import Vision

/// Exercises production panes against synthetic tool results; no network, credentials or mail access.
@MainActor
enum AssistantToolsSelfTest {
    private final class DisclosureFixture: ObservableObject {
        @Published var expanded = false
    }
    private struct DisclosureFixtureView: View {
        @ObservedObject var fixture: DisclosureFixture
        var body: some View {
            DisclosureGroup("Disclosure hit-area fixture", isExpanded: $fixture.expanded) {
                Text("Expanded fixture content")
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.vertical, 20)
            }
            .disclosureGroupStyle(WideDisclosureStyle())
            .padding(24)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            .background(Color(nsColor: .windowBackgroundColor))
        }
    }
    private static func disclosureHitArea(output: URL) async throws {
        NSApp.accessibilitySetValue(true, forAttribute: NSAccessibility.Attribute(rawValue: "AXEnhancedUserInterface"))
        let fixture = DisclosureFixture()
        let host = NSHostingView(rootView: DisclosureFixtureView(fixture: fixture))
        let window = NSWindow(contentRect: NSRect(x: 120, y: 120, width: 620, height: 250),
                              styleMask: [.titled, .closable], backing: .buffered, defer: false)
        window.appearance = NSAppearance(named: .aqua)
        window.title = "Wide disclosure synthetic fixture"
        window.contentView = host
        window.makeKeyAndOrderFront(nil)
        defer { window.orderOut(nil) }
        try await Task.sleep(nanoseconds: 180_000_000)
        // SwiftUI AccessibilityNode implements the legacy NSObject accessibility
        // methods without declaring NSAccessibilityProtocol conformance.
        func attribute(_ node: NSObject, _ name: NSAccessibility.Attribute) -> Any? {
            if let current = node as? NSAccessibilityProtocol {
                switch name {
                case .role: return current.accessibilityRole()?.rawValue
                case .title: return current.accessibilityTitle()
                case .description: return current.accessibilityLabel()
                case .children: return current.accessibilityChildren()
                case .parent: return current.accessibilityParent()
                case .position: return NSValue(point: current.accessibilityFrame().origin)
                case .size: return NSValue(size: current.accessibilityFrame().size)
                default: break
                }
            }
            let key: String
            switch name {
            case .role: key = "accessibilityRole"
            case .title: key = "accessibilityTitle"
            case .description: key = "accessibilityLabel"
            case .children: key = "accessibilityChildren"
            case .parent: key = "accessibilityParent"
            case .position, .size:
                if node.responds(to: NSSelectorFromString("accessibilityFrame")), let frame = node.value(forKey: "accessibilityFrame") as? NSValue {
                    return name == .position ? NSValue(point: frame.rectValue.origin) : NSValue(size: frame.rectValue.size)
                }
                return nil
            default: return nil
            }
            if node.responds(to: NSSelectorFromString(key)) { return node.value(forKey: key) }
            return node.accessibilityAttributeValue(name)
        }
        func isHeading(_ node: NSObject) -> Bool {
            ["AXButton", "AXDisclosureTriangle"].contains(attribute(node, .role).map { String(describing: $0) } ?? "") &&
                [attribute(node, .title), attribute(node, .description)].compactMap { $0 as? String }.contains { $0.contains("Disclosure hit-area fixture") }
        }
        func button(_ value: Any, depth: Int = 0) -> NSObject? {
            guard depth < 24, let node = value as? NSObject else { return nil }
            if isHeading(node) { return node }
            for child in attribute(node, .children) as? [Any] ?? [] {
                if let match = button(child, depth: depth + 1) { return match }
            }
            return nil
        }
        guard let heading = button(host) ?? button(window),
              let position = attribute(heading, .position) as? NSValue,
              let size = attribute(heading, .size) as? NSValue else {
            var lines: [String] = []
            func dump(_ value: Any, _ depth: Int = 0) {
                guard depth < 12, let node = value as? NSObject else { return }
                lines.append("\(depth) \(type(of: node)) role=\(String(describing: attribute(node, .role))) title=\(String(describing: attribute(node, .title))) desc=\(String(describing: attribute(node, .description))) pos=\(String(describing: attribute(node, .position))) size=\(String(describing: attribute(node, .size)))")
                for child in attribute(node, .children) as? [Any] ?? [] { dump(child, depth + 1) }
            }
            dump(window); dump(host)
            try? lines.joined(separator: "\n").write(to: output.appendingPathComponent("disclosure-ax.txt"), atomically: true, encoding: .utf8)
            throw AppSelfTest.Failure("wide disclosure header is not exposed as an accessible control")
        }
        let frame = NSRect(origin: position.pointValue, size: size.sizeValue)
        guard frame.height >= 39.5, frame.width > 150 else {
            throw AppSelfTest.Failure("wide disclosure header target too small: \(frame)")
        }
        try AppSelfTest.capture(window, to: output.appendingPathComponent("disclosure-collapsed.png"))
        for (name, point, expected) in [
            ("title-expanded", NSPoint(x: frame.minX + 70, y: frame.midY), true),
            ("whitespace-collapsed", NSPoint(x: frame.maxX - 24, y: frame.midY), false)
        ] {
            var hit = host.accessibilityHitTest(point) as? NSObject
            var depth = 0
            while let node = hit, !isHeading(node), depth < 12 {
                hit = attribute(node, .parent) as? NSObject
                depth += 1
            }
            guard let target = hit, isHeading(target) else {
                throw AppSelfTest.Failure("wide disclosure \(name) did not hit an operable heading button")
            }
            let press = NSSelectorFromString("accessibilityPerformPress")
            if target.responds(to: press) {
                typealias Press = @convention(c) (AnyObject, Selector) -> Bool
                let action = unsafeBitCast(target.method(for: press), to: Press.self)
                guard action(target, press) else { throw AppSelfTest.Failure("native accessibility press was rejected") }
            } else { target.accessibilityPerformAction(.press) }
            try await Task.sleep(nanoseconds: 220_000_000)
            guard fixture.expanded == expected else {
                throw AppSelfTest.Failure("wide disclosure \(name) did not toggle the production binding")
            }
            try AppSelfTest.capture(window, to: output.appendingPathComponent("disclosure-" + name + ".png"))
        }
    }

    private final class Fixture {
        var requests: [[String: Any]] = []
        func run(_ request: [String: Any]) async throws -> [String: Any] {
            requests.append(request)
            switch request["action"] as? String {
            case "report_sources":
                return ["sources": [["id": "mail.body", "label": "Original fixture source", "text": "Synthetic source: invoice 123. No private email."]]]
            case "usage_summary", "usage_rates":
                return ["groups": [["model": "fixture-model", "calls": 3, "input_tokens": 1500, "output_tokens": NSNull(), "estimated_cost": NSNull(), "currency": "USD", "unknown_usage_calls": 1]],
                        "rates": ["input_per_million": 2.5, "output_per_million": 10, "currency": "USD"]]
            case "history_preview": return ["preview_id": "synthetic-preview", "count": 7, "already_summarized": 2]
            case "history_start": return ["queued": 7, "count": 7]
            case "reply_draft": return ["draft": "Synthetic reply", "recipient": "fixture@example.invalid", "subject": "Re: Fixture", "sent": false]
            default: throw AppSelfTest.Failure("unexpected synthetic assistant tool")
            }
        }
    }
    static func run(store: MailStore, output: URL) async throws -> [String] {
        guard store.isTest, let report = store.reports.first else { throw AppSelfTest.Failure("isolated report fixture required") }
        let savedTools = store.assistantTools, savedSettings = store.settings
        let language = AppLanguage.shared, savedLanguage = language.code
        let featureLabels = ["草稿与来源", "费用与用量记录", "历史邮件补总结", "启用免打扰时间"]
        var catalogBackups: [URL: Data] = [:]
        for code in ["en", "es"] {
            let path = store.base.appendingPathComponent("languages/" + code + ".json")
            let data = try Data(contentsOf: path)
            catalogBackups[path] = data
            var payload = try JSONSerialization.jsonObject(with: data) as! [String: Any]
            var labels = payload["exact"] as! [String: String]
            for label in featureLabels { labels.removeValue(forKey: label) }
            payload["exact"] = labels
            try JSONSerialization.data(withJSONObject: payload).write(to: path, options: .atomic)
        }
        let backend = Fixture()
        let tools = AssistantTools(base: store.base, executor: backend.run)
        store.assistantTools = tools
        defer {
            store.assistantTools = savedTools; store.settings = savedSettings
            for (path, data) in catalogBackups { try? data.write(to: path, options: .atomic) }
            language.select(savedLanguage)
        }
        // Settings has its own isolated --settings-self-test-only suite; do not nest it
        // inside tool executor/catalog fixtures.
        var checks: [String] = []
        let unknownFixture: [String: Any] = ["input_tokens": NSNull(), "output_tokens": NSNull(), "estimated_cost": NSNull(), "unknown_usage_calls": 0]
        guard UsagePresentation.number(["input_tokens": 1500], "input_tokens") == "1,500",
              UsagePresentation.number(unknownFixture, "input_tokens") == T("未知"),
              UsagePresentation.number(unknownFixture, "output_tokens") == T("未知"),
              UsagePresentation.cost(unknownFixture) == T("未知"),
              UsagePresentation.number([:], "calls") == T("未知") else {
            throw AppSelfTest.Failure("usage formatting inferred missing data from a zero unknown-call count")
        }
        checks.append("usage uses thousands separators and absent tokens/cost stay unknown independently of unknown-call counters")
        func at(_ hour: Int, _ minute: Int) -> Date {
            Calendar.current.date(from: DateComponents(year: 2026, month: 10, day: 20, hour: hour, minute: minute))!
        }
        let quiet = QuietHours(enabled: true, start: "22:00", end: "08:00")
        guard !quiet.contains(at(21, 59)), quiet.contains(at(22, 0)), quiet.contains(at(0, 1)),
              quiet.contains(at(7, 59)), !quiet.contains(at(8, 0)),
              QuietHours(enabled: true, start: "09:00", end: "09:00").contains(at(14, 0)) else {
            throw AppSelfTest.Failure("native quiet-hour overnight boundaries or all-day equality differ from backend")
        }
        store.settings.enabled = true; store.settings.notifications_enabled = false
        guard !store.notificationsAllowed, store.settings.enabled else { throw AppSelfTest.Failure("muting paused monitoring") }
        store.settings.notifications_enabled = true; store.settings.quiet_hours.enabled = false
        guard store.notificationsAllowed else { throw AppSelfTest.Failure("notification resume did not restore native presentation") }
        checks.append("native notification toggle is independent of monitoring; local quiet-hour overnight/start/end/all-day semantics match backend")
        let preview = await tools.perform("history_preview", ["from": "2026-10-01", "to": "2026-10-20"])
        guard preview?["count"] as? Int == 7, backend.requests.count == 1,
              backend.requests.allSatisfy({ $0["action"] as? String == "history_preview" }) else {
            throw AppSelfTest.Failure("historical preview invoked processing before confirmation")
        }
        _ = await tools.perform("history_start", ["preview_id": "synthetic-preview"])
        guard backend.requests.last?["action"] as? String == "history_start" else { throw AppSelfTest.Failure("explicit history confirmation not forwarded") }
        checks.append("historical count preview is separate from the explicit processing confirmation")
        let draft = await tools.perform("reply_draft", ["path": report.id, "tone": "formal", "language": "es"])
        guard draft?["sent"] as? Bool == false, draft?["draft"] as? String == "Synthetic reply" else { throw AppSelfTest.Failure("draft contract dropped content or sending prohibition") }
        checks.append("reply tool preserves editable draft/recipient metadata and explicitly reports sent=false")
        try await disclosureHitArea(output: output)
        checks.append("production disclosure exposes a full-width accessible disclosure target at least 40pt high; native title and blank-header hit targets expand and collapse it, with snapshots")
        for code in ["zh", "en", "es"] {
            language.select(code)
            for label in featureLabels {
                guard T(label) == (AssistantToolsLocalization.translate(label, language: code) ?? label) else {
                    throw AppSelfTest.Failure("current feature label lost to an older language catalog")
                }
            }
            let views: [(String, AnyView, NSSize, String)] = [
                ("reply-sources", AnyView(ReportToolsView(store: store, report: report)), NSSize(width: 900, height: 850), T("草稿与来源")),
                ("usage", AnyView(UsageSettingsView(store: store)), NSSize(width: 760, height: 580), T("费用与用量记录")),
                ("history", AnyView(HistoryBackfillView(store: store)), NSSize(width: 700, height: 430), T("历史邮件补总结")),
                ("notifications", AnyView(VStack(alignment: .leading, spacing: 20) { QuietHoursControl(store: store); AssistantUtilitySettings(store: store) }.padding(24)), NSSize(width: 900, height: 450), T("启用免打扰时间"))
            ]
            for (name, view, size, title) in views {
                let window = NSWindow(contentRect: NSRect(origin: NSPoint(x: 100, y: 100), size: size), styleMask: [.titled, .closable], backing: .buffered, defer: false)
                window.appearance = NSAppearance(named: .aqua)
                window.title = "Synthetic assistant tools"
                window.contentView = NSHostingView(rootView: view.background(Color(nsColor: .windowBackgroundColor)))
                window.makeKeyAndOrderFront(nil)
                try await Task.sleep(nanoseconds: 650_000_000)
                let image = output.appendingPathComponent("assistant-" + name + "-" + code + ".png")
                try AppSelfTest.capture(window, to: image)
                let request = VNRecognizeTextRequest()
                request.recognitionLevel = .accurate
                request.recognitionLanguages = code == "zh" ? ["zh-Hans", "en-US"] : code == "es" ? ["es-ES", "en-US"] : ["en-US"]
                try VNImageRequestHandler(url: image, options: [:]).perform([request])
                let text = (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }.joined(separator: " ")
                window.orderOut(nil)
                func normalized(_ value: String) -> String { value.filter { !$0.isWhitespace }.folding(options: [.diacriticInsensitive, .caseInsensitive], locale: Locale(identifier: code)) }
                guard normalized(text).contains(normalized(title)) else { throw AppSelfTest.Failure("actual tool pane missing localized title: \(name)/\(code): \(text)") }
                if name == "usage", !text.contains("fixture-model") { throw AppSelfTest.Failure("actual usage pane failed to render backend groups") }
                if name == "reply-sources", !normalized(text).contains(normalized("Original fixture source")) { throw AppSelfTest.Failure("actual source pane failed to render source records: " + text) }
            }
        }
        checks.append("twelve real-window captures: reply/source, usage with unknown counters, history confirmation and quiet-hours tools render in Chinese, English and Spanish")
        checks.append("current native feature label fallback takes precedence over installed legacy language packs")
        return checks
    }
}

import AppKit
import SwiftUI

@MainActor
enum SidebarLanguageSelfTest {
    private final class Selection: ObservableObject {
        @Published var page: WorkspacePage? = .ai
    }
    private struct Host: View {
        @ObservedObject var selection: Selection
        var body: some View {
            WorkspaceNavigationList(selection: $selection.page)
        }
    }
    static func run(output: URL) async throws -> [String] {
        NSApp.accessibilitySetValue(true, forAttribute: NSAccessibility.Attribute(rawValue: "AXEnhancedUserInterface"))
        let language = AppLanguage.shared
        let original = language.code
        defer { language.select(original) }
        let selection = Selection()
        let host = NSHostingView(rootView: Host(selection: selection))
        let window = NSWindow(contentRect: NSRect(x: 60, y: 60, width: 340, height: 320),
                              styleMask: [.titled, .closable], backing: .buffered, defer: false)
        window.contentView = host
        window.makeKeyAndOrderFront(nil)
        defer { window.orderOut(nil) }
        func attribute(_ node: NSObject, _ key: String, _ raw: String) -> Any? {
            if node.responds(to: NSSelectorFromString(key)) { return node.value(forKey: key) }
            return node.accessibilityAttributeValue(NSAccessibility.Attribute(rawValue: raw))
        }
        func find(_ value: Any, id: String, depth: Int = 0) -> NSObject? {
            guard depth < 35, let node = value as? NSObject else { return nil }
            if attribute(node, "accessibilityIdentifier", "AXIdentifier") as? String == id { return node }
            for child in attribute(node, "accessibilityChildren", "AXChildren") as? [Any] ?? [] {
                if let result = find(child, id: id, depth: depth + 1) { return result }
            }
            return nil
        }
        for code in ["zh", "en", "es", "chinglish", "en", "zh"] {
            language.select(code)
            try await Task.sleep(nanoseconds: 250_000_000)
            host.layoutSubtreeIfNeeded()
            for page in WorkspacePage.allCases {
                guard let row = find(host, id: "workspace-nav-" + page.id) else {
                    throw AppSelfTest.Failure("Mounted sidebar row missing in " + code + ": " + page.rawValue)
                }
                let labels = [
                    attribute(row, "accessibilityLabel", "AXDescription"),
                    attribute(row, "accessibilityValue", "AXValue"),
                    attribute(row, "accessibilityTitle", "AXTitle")
                ].compactMap { $0 as? String }
                guard labels.contains(T(page.rawValue)) else {
                    throw AppSelfTest.Failure("Mounted sidebar row retained the previous language: \(code), \(page.rawValue), \(labels)")
                }
            }
            guard selection.page == .ai, window.contentView === host else {
                throw AppSelfTest.Failure("Language change reset the sidebar selection or replaced the root view")
            }
        }
        return ["All four mounted sidebar rows follow Chinese, English, Spanish and Chinglish without replacing their List or resetting selection"]
    }
}

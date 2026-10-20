import AppKit
import SwiftUI
import Vision

@MainActor
enum LanguageUIAuditSelfTest {
    static func run(store: MailStore, output: URL) async throws -> [String] {
        let language = AppLanguage.shared
        let original = language.code
        defer { language.select(original) }
        language.select("zh")
        // This host intentionally observes neither MailStore nor AppLanguage.
        // Its actual card titles must update without replacing the root view.
        let host = NSHostingView(rootView: VStack {
            WorkspaceCard("屏蔽邮件") { Text("Fixture content") }
            WorkspaceCard("管理邮箱") { Text("Fixture account content") }
            WorkspaceCard("软件更新") { Text("Fixture update content") }
        }.padding(20).background(Color(nsColor: .windowBackgroundColor)))
        let window = NSWindow(contentRect: NSRect(x: 100, y: 100, width: 680, height: 500),
                              styleMask: [.titled, .closable], backing: .buffered, defer: false)
        window.appearance = NSAppearance(named: .aqua)
        window.title = "Language invalidation fixture"
        window.contentView = host
        window.makeKeyAndOrderFront(nil)
        defer { window.orderOut(nil) }
        for (code, titles) in [
            ("zh", ["屏蔽邮件", "管理邮箱", "软件更新"]),
            ("en", ["Blocked mail", "Manage mailboxes", "Software updates"]),
            ("es", ["Correo bloqueado", "Gestionar buzones", "Actualizaciones del software"]),
            ("zh", ["屏蔽邮件", "管理邮箱", "软件更新"])
        ] {
            language.select(code)
            try await Task.sleep(nanoseconds: 180_000_000)
            let image = output.appendingPathComponent("workspace-card-live-" + code + ".png")
            try AppSelfTest.capture(window, to: image)
            let values = try visibleText(image, language: code)
            for title in titles where !values.contains(title) {
                throw Failure("actual workspace card title did not follow language \(code): \(title); pixels=\(values)")
            }
            if code != "zh", values.contains("屏蔽邮件") {
                throw Failure("actual blocked-mail card retained its Chinese title after language switch")
            }
        }
        // Also test a mounted address picker, which previously depended on its parent's invalidation.
        let policy = SenderPolicyStore(base: store.base, offline: true)
        let picker = NSHostingView(rootView: SenderAddressPicker(policy: policy, candidates: ["fixture@example.invalid"])
            .background(Color(nsColor: .windowBackgroundColor)))
        window.contentView = picker
        for (code, expected) in [("en", "Select from known senders"), ("es", "Seleccionar entre remitentes conocidos"), ("zh", "从已有发件人批量选择")] {
            language.select(code)
            try await Task.sleep(nanoseconds: 180_000_000)
            let image = output.appendingPathComponent("sender-picker-live-" + code + ".png")
            try AppSelfTest.capture(window, to: image)
            guard try visibleText(image, language: code).contains(expected) else {
                throw Failure("mounted sender picker did not react to language: " + code)
            }
        }
        return [
            "real immutable-host workspace card titles switch Chinese/English/Spanish/Chinese without root replacement; blocked-mail heading never remains Chinese in another language",
            "already-mounted bulk sender picker follows language changes independently of its parent"
        ]
    }
    private static func visibleText(_ image: URL, language: String) throws -> String {
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.recognitionLanguages = language == "zh" ? ["zh-Hans", "en-US"] : language == "es" ? ["es-ES", "en-US"] : ["en-US"]
        try VNImageRequestHandler(url: image, options: [:]).perform([request])
        return (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }
            .joined(separator: " ").split(whereSeparator: \.isWhitespace).joined(separator: " ")
    }
    private struct Failure: LocalizedError {
        let message: String
        init(_ message: String) { self.message = message }
        var errorDescription: String? { message }
    }
}

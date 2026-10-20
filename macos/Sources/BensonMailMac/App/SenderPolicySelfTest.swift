import AppKit
import SwiftUI

@MainActor
enum SenderPolicySelfTest {
    private final class Backend {
        var policy = SenderPolicyRule()
        var records: [[String: Any]] = [
            ["id": "blocked-one", "sender": "blocked@example.invalid", "subject": "合同草稿 / Contract draft", "received": "2026-10-20 12:00", "reason": "blacklist", "state": "blocked"],
            ["id": "spam-two", "sender": "spam@example.invalid", "subject": "模拟垃圾邮件 / Fixture spam", "received": "2026-10-20 11:00", "reason": "spam", "state": "blocked"],
        ]
        var calls: [SenderPolicyRequest] = []
        var failNext = false
        func execute(_ request: SenderPolicyRequest) async throws -> Data {
            calls.append(request)
            try await Task.sleep(nanoseconds: 60_000_000)
            if failNext {
                failNext = false
                return Data("{\"ok\":false,\"error\":\"Synthetic policy failure\"}".utf8)
            }
            switch request.action {
            case "save": if let value = request.policy { policy = value }
            case "remove_records": records.removeAll { request.ids?.contains($0["id"] as? String ?? "") == true }
            case "summarize_records":
                for index in records.indices where request.ids?.contains(records[index]["id"] as? String ?? "") == true {
                    records[index]["state"] = "queued"
                }
            default: break
            }
            let encoded = try JSONSerialization.jsonObject(with: JSONEncoder().encode(policy))
            return try JSONSerialization.data(withJSONObject: ["ok": true, "policy": encoded, "records": records, "count": records.count,
                "senders": ["blocked@example.invalid", "spam@example.invalid"]])
        }
    }
    static func run(store: MailStore, output: URL) async throws -> [String] {
        let backend = Backend()
        let policy = SenderPolicyStore(base: store.base, executor: backend.execute)
        var checks: [String] = []
        await policy.refresh()
        guard policy.loaded, policy.records.count == 2, policy.records.map(\.sender).contains("blocked@example.invalid") else {
            throw Failure("local policy status did not load")
        }
        policy.draft.mode = "whitelist"; policy.draft.skip_spam = true
        guard policy.addAddresses(["Example <USER@Example.Invalid>", "user@example.invalid", "Other@Example.Invalid"]),
              policy.draft.addresses == ["user@example.invalid", "other@example.invalid"] else { throw Failure("sender addresses were not normalized and deduplicated") }
        let draft = policy.draft
        guard !policy.addAddresses(["not-an-address"]), policy.draft == draft, !policy.error.isEmpty else { throw Failure("invalid address altered the rule draft") }
        await policy.refresh()
        guard policy.draft == draft, policy.dirty, backend.calls.allSatisfy({ $0.action == "status" }) else { throw Failure("refresh discarded an unsaved draft or wrote rules") }
        var persisted: [Bool] = []
        policy.policyDidSave = { _, save in persisted.append(save) }
        await policy.save()
        guard backend.policy == draft, policy.saved == draft, !policy.dirty, persisted.last == true else { throw Failure("saving mail rules lost mode, addresses, spam option or persistence callback") }
        checks.append("policy status and save contract; case-insensitive exact addresses deduplicated; invalid input and refresh preserve unsaved draft; save requests configuration persistence")
        await policy.summarizeRecords(["blocked-one"])
        guard backend.calls.last?.action == "summarize_records", backend.calls.last?.ids == ["blocked-one"],
              policy.records.first(where: { $0.id == "blocked-one" })?.state == "queued",
              backend.policy == draft else { throw Failure("one-time summary did not queue only the selected record or changed sender rules") }
        await policy.removeRecords(["spam-two"])
        guard policy.records.map(\.id) == ["blocked-one"], backend.calls.last?.action == "remove_records",
              backend.calls.last?.ids == ["spam-two"], backend.policy == draft else { throw Failure("local record removal changed sender rules or the wrong records") }
        checks.append("one-time summary queues only selected records without changing rules; removal targets only local record IDs and never issues mailbox or AI operations")
        policy.removeAddress("other@example.invalid")
        let beforeFailure = policy.draft
        backend.failNext = true
        await policy.save()
        guard policy.error == "Synthetic policy failure", policy.draft == beforeFailure, policy.dirty, !policy.busy else {
            throw Failure("failed policy operation lost the draft, diagnostics or busy reset")
        }
        let beforeCalls = backend.calls.count
        let pending = Task { await policy.refresh() }
        try await Task.sleep(nanoseconds: 10_000_000)
        await policy.removeRecords(["blocked-one"])
        await pending.value
        guard backend.calls.count == beforeCalls + 1, policy.records.count == 1 else { throw Failure("busy guard issued overlapping policy requests") }
        checks.append("backend failure preserves draft and readable diagnostics; concurrent actions are guarded")
        // Mount real controls with the injected local executor. No mailbox or AI credentials are accessed.
        let originalSettings = store.settings
        defer { store.settings = originalSettings }
        backend.records[0]["state"] = "blocked"
        await policy.refresh()
        let window = NSWindow(contentRect: NSRect(x: 100, y: 100, width: 900, height: 920),
                              styleMask: [.titled, .closable, .resizable], backing: .buffered, defer: false)
        window.title = "Sender policy fixture"
        window.contentView = NSHostingView(rootView: ScrollView { SenderPolicyView(store: store, policy: policy, expanded: true).padding(20) })
        window.makeKeyAndOrderFront(nil)
        defer { window.orderOut(nil) }
        try await Task.sleep(nanoseconds: 250_000_000)
        try AppSelfTest.capture(window, to: output.appendingPathComponent("sender-policy-chinese.png"))
        for (code, expected) in [("en", "Blocklist"), ("es", "Lista de bloqueo")] {
            // Simulate an existing downloaded pack that predates all new policy labels.
            let pack = store.base.appendingPathComponent("languages/\(code).json")
            let originalPack = try Data(contentsOf: pack)
            var oldPack = try JSONSerialization.jsonObject(with: originalPack) as! [String: Any]
            var oldExact = oldPack["exact"] as! [String: String]
            for key in SenderPolicyLocalization.keys { oldExact.removeValue(forKey: key) }
            oldPack["exact"] = oldExact
            if let templates = oldPack["templates"] as? [[String: Any]] {
                oldPack["templates"] = templates.filter { !($0["pattern"] as? String ?? "").contains("请输入完整的邮箱地址") }
            }
            try JSONSerialization.data(withJSONObject: oldPack).write(to: pack, options: .atomic)
            defer { try? originalPack.write(to: pack, options: .atomic) }
            AppLanguage.shared.select(code)
            guard T("黑名单") == expected, T("不总结垃圾邮件（部分邮箱可能不支持）") != "不总结垃圾邮件（部分邮箱可能不支持）",
                  T("仅删除本地跳过记录，不会删除邮箱中的邮件。总结一次不会把发件人移出名单。") != "仅删除本地跳过记录，不会删除邮箱中的邮件。总结一次不会把发件人移出名单。",
                  !T("请输入完整的邮箱地址：bad-address").contains("请输入完整"),
                  !T("AI 接口DNS 解析失败，请检查域名和 DNS 设置。\n具体原因：gaierror: synthetic failure").contains("DNS 解析失败") else {
                throw Failure("policy translation or no-delete explanation missing: " + code)
            }
            try await Task.sleep(nanoseconds: 100_000_000)
            try AppSelfTest.capture(window, to: output.appendingPathComponent("sender-policy-" + code + ".png"))
        }
        AppLanguage.shared.select("zh")
        let picker = NSWindow(contentRect: NSRect(x: 140, y: 140, width: 564, height: 470),
                              styleMask: [.titled, .closable], backing: .buffered, defer: false)
        picker.title = "Bulk sender picker fixture"
        picker.contentView = NSHostingView(rootView: SenderAddressPicker(policy: policy, candidates: ["new@example.invalid", "known@example.invalid"]))
        picker.makeKeyAndOrderFront(nil)
        defer { picker.orderOut(nil) }
        try await Task.sleep(nanoseconds: 200_000_000)
        try AppSelfTest.capture(picker, to: output.appendingPathComponent("sender-policy-add-bulk.png"))
        checks.append("actual macOS policy card and bulk sender picker mounted with local fixture; Chinese, English and Spanish captures; old language packs missing new keys still localize policy controls, spam limitation, no-delete text and AI network diagnostics without downloads")
        return checks
    }
    private struct Failure: LocalizedError {
        let message: String
        init(_ message: String) { self.message = message }
        var errorDescription: String? { message }
    }
}

import AppKit
import SwiftUI

@MainActor enum SettingsDraftSelfTest {
    static func run(store: MailStore, output: URL) async throws -> [String] {
        guard store.isTest else { throw AppSelfTest.Failure("settings fixture must be isolated") }
        let original = store.settings, originalPage = store.workspacePage, originalLogin = store.loginEnabled, originalMailAccount = store.mailAccount
        let settingsBytes = try? Data(contentsOf: store.settingsURL)
        let ratesURL = store.base.appendingPathComponent("usage-rates.json")
        let ratesBytes = try? Data(contentsOf: ratesURL)
        let activeLanguage = AppLanguage.shared.code
        defer {
            store.settings = original; store.workspacePage = originalPage; store.loginEnabled = originalLogin; store.mailAccount = originalMailAccount
            if let settingsBytes { try? settingsBytes.write(to: store.settingsURL, options: .atomic) }
            else { try? FileManager.default.removeItem(at: store.settingsURL) }
            if let ratesBytes { try? ratesBytes.write(to: ratesURL, options: .atomic) }
            else { try? FileManager.default.removeItem(at: ratesURL) }
            AppLanguage.shared.applySettingsLanguage(activeLanguage); store.settingsDraft.reload()
        }
        func require(_ condition: @autoclosure () throws -> Bool, _ text: String) throws {
            guard try condition() else { throw AppSelfTest.Failure(text) }
        }
        var connection = MailConnection(); connection.account = "fixture@example.com"; connection.host = "imap.example.com"
        store.settings.enabled = false; store.settings.mailbox = connection
        store.settings.mailboxes = [MailboxProfile(connection: connection, enabled: true)]
        store.settings.ai_provider = "api"; store.settings.api_base = "https://example.com/v1"; store.settings.api_model = "fixture"
        try store.save()
        let before = try Data(contentsOf: store.settingsURL)
        let draft = SettingsDraft(store: store); draft.reload(); store.workspacePage = .mailbox
        var saveCount = 0
        draft.persistOverride = { saveCount += 1; try store.save() }
        defer { draft.persistOverride = nil }
        // Six independent controls remain in memory, then share exactly one config commit.
        draft.accounts[0].connection.host = "imap.changed.example.com"
        draft.accounts[0].secret = "synthetic-test-secret"
        draft.accounts[0].connection.proxy_mode = "socks5"
        draft.accounts[0].proxyPort = "10809"
        draft.value.mail_policy.skip_spam = true
        draft.interval = "120"
        try require(draft.dirty(.mailbox) && !draft.dirty(.ai) && !draft.dirty(.general), "mailbox dirty scope is wrong")
        try require((try? Data(contentsOf: store.settingsURL)) == before && saveCount == 0, "staged changes leaked before Save")
        try require(!draft.navigate(.ai, confirmDiscard: { false }) && draft.interval == "120", "cancel navigation discarded draft")
        await draft.save(.mailbox)
        try require(saveCount == 1 && !draft.dirty(.mailbox), "six settings did not share one Save: count=\(saveCount), dirty=\(draft.dirty(.mailbox)), message=\(draft.message), phase=\(store.status.phase), enabled=\(store.settings.enabled), requested=\(store.checkRequested)")
        try require(store.settings.interval_seconds == 120 && store.settings.mail_policy.skip_spam && store.settings.mailbox?.proxy_port == 10809, "mailbox Save lost staged values")
        try require(!String(decoding: try Data(contentsOf: store.settingsURL), as: UTF8.self).contains("synthetic-test-secret"), "credential leaked into settings")
        draft.reload(); store.workspacePage = .ai
        draft.value.api_base = "https://example.com/other"; draft.value.api_model = "fixture-2"
        draft.apiKey = "synthetic-api-key"; draft.inputRate = "1.2"; draft.outputRate = "3.4"; draft.currency = "CNY"
        try require(draft.dirty(.ai) && !draft.dirty(.general), "AI fields contaminated general dirty state")
        await draft.save(.ai)
        try require(saveCount == 2 && !draft.dirty(.ai), "AI settings and rates did not share one commit")
        let rates = try Data(contentsOf: ratesURL)
        try require(String(decoding: rates, as: UTF8.self).contains("fixture-2"), "AI rates did not bind to selected model")
        // Failed config persistence rolls rates back and preserves edits for retry.
        draft.inputRate = "9.9"
        draft.persistOverride = { throw CocoaError(.fileWriteNoPermission) }
        await draft.save(.ai)
        try require(draft.dirty(.ai) && (try? Data(contentsOf: ratesURL)) == rates && store.settings.api_model == "fixture-2", "failed Save did not roll back rates/config")
        draft.persistOverride = { saveCount += 1; try store.save() }
        try require(draft.navigate(.general, confirmDiscard: { true }), "discard navigation failed")
        try require(!draft.dirty(.general) && draft.inputRate != "9.9", "discard did not reset draft")
        // Latest runtime state survives a staged General save.
        draft.value.notifications_enabled = false; draft.value.quiet_hours.enabled = true
        draft.value.quiet_hours.start = "21:30"; draft.value.quiet_hours.end = "07:00"
        draft.value.output_dir = output.appendingPathComponent("staged-reports").path
        draft.login = !store.loginEnabled; draft.value.ui_language = "zh"
        store.settings.enabled = true
        await draft.save(.general)
        try require(saveCount == 3 && !draft.dirty(.general) && store.settings.enabled, "General Save lost runtime state or stayed dirty")
        try require(!store.settings.notifications_enabled && store.settings.quiet_hours.start == "21:30", "General Save lost staged notification controls")
        draft.reload(); store.workspacePage = .mailbox; draft.interval = "bad"
        let validBytes = try Data(contentsOf: store.settingsURL)
        await draft.save(.mailbox)
        try require(saveCount == 3 && draft.dirty(.mailbox) && (try? Data(contentsOf: store.settingsURL)) == validBytes, "invalid page changed persisted settings")
        draft.reload()
        for code in ["zh", "en", "es"] {
            AppLanguage.shared.applySettingsLanguage(code)
            for page in [WorkspacePage.mailbox, .ai, .general] {
                store.workspacePage = page
                let window = NSWindow(contentRect: NSRect(x: 100, y: 100, width: 1080, height: 840), styleMask: [.titled, .closable], backing: .buffered, defer: false)
                window.contentView = NSHostingView(rootView: StagedSettingsPage(store: store, draft: draft, page: page).disclosureGroupStyle(WideDisclosureStyle()))
                window.makeKeyAndOrderFront(nil)
                try await Task.sleep(nanoseconds: 120_000_000)
                try AppSelfTest.capture(window, to: output.appendingPathComponent("settings-page-" + page.id + "-" + code + ".png"))
                window.orderOut(nil)
            }
        }
        return ["settings-staged-six-controls-one-save", "settings-navigation-cancel-discard", "settings-rates-rollback", "settings-page-language-snapshots"]
    }
}

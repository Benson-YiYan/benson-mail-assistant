import AppKit
import SwiftUI
import Security
import CryptoKit

/// Workspace edits never touch live settings until the page's single Save is pressed.
@MainActor final class SettingsDraft: ObservableObject {
    struct Account: Identifiable, Codable {
        var id = UUID().uuidString
        var connection: MailConnection
        var original: MailConnection?
        var enabled = true
        var secret = ""
        var port: String
        var proxyPort: String
        init(_ c: MailConnection, enabled: Bool = true, existing: Bool = true) {
            connection = MailAccountDraft.load(c); original = existing ? c : nil
            self.enabled = enabled; port = String(c.port); proxyPort = String(c.proxy_port)
        }
    }
    unowned let store: MailStore
    var persistOverride: (() throws -> Void)?
    @Published var value = MailSettings()
    @Published var accounts: [Account] = []
    @Published var selected = ""
    @Published var interval = "60"
    @Published var apiKey = ""
    @Published var inputRate = "0"
    @Published var outputRate = "0"
    @Published var currency = "USD"
    private var rateBaseline = ""
    private var loadedRatesConfigured = false
    @Published var login = false
    @Published var message = ""
    @Published var saving = false
    @Published var generation = UUID()
    private var baseline: [WorkspacePage: Data] = [:]
    init(store: MailStore) { self.store = store; reload() }
    private func fingerprint(_ page: WorkspacePage) -> Data {
        let encoder = JSONEncoder(); encoder.outputFormatting = .sortedKeys
        switch page {
        case .mailbox: return (try? encoder.encode(accounts)) ?? Data()
        case .ai: return Data([value.ai_provider, value.api_base, value.api_model, value.harness_path, apiKey, inputRate, outputRate, currency].joined(separator: "\u{0}").utf8)
        case .general:
            struct General: Encodable { let output: String; let language: String?; let notifications: Bool; let quiet: QuietHours }
            return (try? encoder.encode(General(output: value.output_dir, language: value.ui_language, notifications: value.notifications_enabled, quiet: value.quiet_hours))) ?? Data()
        case .reports: return Data()
        }
    }
    private func signature(_ page: WorkspacePage) -> Data {
        var data = fingerprint(page)
        if page == .mailbox {
            let encoder = JSONEncoder(); encoder.outputFormatting = .sortedKeys
            data.append((try? encoder.encode(value.mail_policy)) ?? Data()); data.append(Data(interval.utf8))
        }
        if page == .general { data.append(Data(login ? [1] : [0])) }
        return data
    }
    func dirty(_ page: WorkspacePage) -> Bool { baseline[page] != signature(page) }
    func reload() {
        value = store.settings
        accounts = store.mailboxProfiles.map { Account($0.connection, enabled: $0.enabled) }
        selected = accounts.first(where: { $0.connection.identity == store.settings.mailbox?.identity })?.id ?? accounts.first?.id ?? ""
        interval = String(value.interval_seconds); apiKey = ""; login = store.loginEnabled; message = ""
        loadRates()
        for page in WorkspacePage.allCases { baseline[page] = signature(page) }
        generation = UUID()
    }
    func mayLeave(confirmDiscard: (() -> Bool)? = nil) -> Bool {
        guard !saving else { return false }
        guard dirty(store.workspacePage) else { return true }
        if let confirmDiscard { return confirmDiscard() }
        let alert = NSAlert(); alert.messageText = T("你有未保存的设置，确定要离开吗？")
        alert.addButton(withTitle: T("继续编辑")); alert.addButton(withTitle: T("放弃更改并离开"))
        return alert.runModal() == .alertSecondButtonReturn
    }
    @discardableResult func navigate(_ page: WorkspacePage, confirmDiscard: (() -> Bool)? = nil) -> Bool {
        guard page != store.workspacePage, mayLeave(confirmDiscard: confirmDiscard) else { return false }
        reload(); store.workspacePage = page; return true
    }
    func chooseFolder() {
        let panel = NSOpenPanel(); panel.canChooseFiles = false; panel.canChooseDirectories = true; panel.canCreateDirectories = true
        if panel.runModal() == .OK, let url = panel.url { value.output_dir = url.path }
    }
    func addAccount() { let row = Account(MailConnection(), existing: false); accounts.append(row); selected = row.id }
    func save(_ page: WorkspacePage) async {
        guard !saving else { return }; saving = true; message = ""; defer { saving = false }
        let old = store.settings
        var next = old
        // Each keychain mutation has an undo snapshot; plaintext is never persisted in the draft file.
        var undo: [(String, String, Data?)] = []
        var policyChanged = false
        var ratesChanged = false
        let ratesURL = store.base.appendingPathComponent("usage-rates.json")
        let previousRates = try? Data(contentsOf: ratesURL)
        let legacyStateURL = store.data.appendingPathComponent("state.json")
        let previousLegacyState = try? Data(contentsOf: legacyStateURL)
        var legacyStateChanged = false
        let previousLogin = try? Data(contentsOf: store.loginURL)
        do {
            switch page {
            case .mailbox:
                guard let seconds = Int(interval), (10...86400).contains(seconds) else { throw MailCredentials.Failure("请输入10至86400秒的检查间隔。") }
                var profiles: [MailboxProfile] = []
                for row in accounts {
                    var c = row.connection
                    guard let port = Int(row.port), let proxy = Int(row.proxyPort) else { throw MailCredentials.Failure("请输入有效的端口。") }
                    c.port = port; c.proxy_port = proxy; c = try c.validated()
                    let secret = row.secret.trimmingCharacters(in: .whitespacesAndNewlines)
                    if row.original?.identity != c.identity && secret.isEmpty { throw MailCredentials.Failure("请填写密码、客户端授权码或 OAuth2 访问令牌。") }
                    guard !profiles.contains(where: { $0.id == c.identity }) else { throw MailCredentials.Failure("此邮箱连接已经添加，请从账号列表中选择。") }
                    if !secret.isEmpty { c.secret_service = "BensonMail-IMAP"; c.secret_account = c.identity + "-" + UUID().uuidString }
                    profiles.append(MailboxProfile(connection: c, enabled: row.enabled))
                }
                let original = store.mailboxProfiles.map { MailboxProfile(connection: MailAccountDraft.load($0.connection), enabled: $0.enabled) }
                if profiles != original && (old.enabled || ["checking", "analyzing"].contains(store.status.phase) || store.checkRequested) { throw MailCredentials.Failure("请先暂停全部监听，等当前邮件处理完成后再编辑或添加邮箱。") }
                next.mailboxes = profiles
                if let index = accounts.firstIndex(where: { $0.original?.identity == old.mailbox?.identity }), profiles.indices.contains(index) { next.mailbox = profiles[index].connection }
                else { next.mailbox = profiles.first?.connection }
                next.interval_seconds = seconds; next.mail_policy = value.mail_policy
                for (index, row) in accounts.enumerated() where !row.secret.isEmpty {
                    let c = profiles[index].connection
                    try writeSecret(c.secret_service, c.secret_account, row.secret, undo: &undo)
                }
            case .ai:
                guard let input = Double(inputRate), let output = Double(outputRate), input.isFinite, output.isFinite,
                      (0...1_000_000).contains(input), (0...1_000_000).contains(output),
                      currency.range(of: "^[A-Za-z]{3}$", options: .regularExpression) != nil else { throw MailCredentials.Failure("请输入有效的非负单价和三位币种代码。") }
                guard ["api", "codex", "deepseek_harness"].contains(value.ai_provider) else { throw MailCredentials.Failure("请选择分析方式。") }
                if value.ai_provider == "api" {
                    let endpoint = try MailCredentials.apiEndpoint(value.api_base)
                    guard !value.api_model.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { throw MailCredentials.Failure("请填写模型名。") }
                    guard !apiKey.isEmpty || store.isTest || MailCredentials.hasAPIKey(endpoint: endpoint) else { throw MailCredentials.Failure("请填写此基础地址的 API Key。") }
                    if !apiKey.isEmpty { try writeSecret("BensonMail-AI-API", endpoint, apiKey, undo: &undo) }
                }
                next.ai_provider = value.ai_provider; next.api_base = value.api_base.trimmingCharacters(in: .whitespacesAndNewlines)
                next.api_model = value.api_model.trimmingCharacters(in: .whitespacesAndNewlines); next.harness_path = value.harness_path
            case .general:
                guard await AppLanguage.shared.prepareSettingsLanguage(value.ui_language ?? AppLanguage.shared.code) else { return }
                guard validClock(value.quiet_hours.start), validClock(value.quiet_hours.end) else { throw MailCredentials.Failure("请输入有效的时间（HH:mm）。") }
                let folder = URL(fileURLWithPath: value.output_dir)
                try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
                guard FileManager.default.isWritableFile(atPath: folder.path) else { throw CocoaError(.fileWriteNoPermission) }
                next.output_dir = value.output_dir; next.ui_language = value.ui_language
                next.notifications_enabled = value.notifications_enabled; next.quiet_hours = value.quiet_hours
                try store.writeLoginSetting(login)
            case .reports: return
            }
            if page == .mailbox && next.mail_policy != old.mail_policy {
                let policy = SenderPolicyStore(base: store.base, offline: store.isTest)
                policy.draft = next.mail_policy; await policy.save()
                guard policy.error.isEmpty else { throw MailCredentials.Failure(policy.error) }
                policyChanged = true
            }
            if page == .mailbox, let previousLegacyState,
               var state = try JSONSerialization.jsonObject(with: previousLegacyState) as? [String: Any],
               state["mailbox_key"] == nil, let identity = old.mailbox?.identity ?? store.mailboxProfiles.first?.connection.identity {
                state["mailbox_key"] = identity
                try JSONSerialization.data(withJSONObject: state).write(to: legacyStateURL, options: .atomic)
                legacyStateChanged = true
            }
            if page == .ai && (rateBaseline != [inputRate, outputRate, currency].joined(separator: "|") || (loadedRatesConfigured && (next.api_base != old.api_base || next.api_model != old.api_model))) {
                var document = (previousRates.flatMap { try? JSONSerialization.jsonObject(with: $0) } as? [String: Any]) ?? [:]
                var entries = document["rates"] as? [String: Any] ?? [:]
                entries[rateKey(base: next.api_base, model: next.api_model)] = ["input_per_million": Double(inputRate)!, "output_per_million": Double(outputRate)!, "currency": currency.uppercased(), "configured": true, "model": next.api_model]
                document["rates"] = entries
                try FileManager.default.createDirectory(at: store.base, withIntermediateDirectories: true)
                try JSONSerialization.data(withJSONObject: document).write(to: ratesURL, options: .atomic)
                ratesChanged = true
            }
            store.settings = next
            do { if let persistOverride { try persistOverride() } else { try store.save() } } catch { store.settings = old; throw error }
            if page == .general { AppLanguage.shared.applySettingsLanguage(next.ui_language ?? AppLanguage.shared.code); store.loginEnabled = login }
            store.mailAccount = next.mailbox?.account ?? ""
            try? Data().write(to: store.base.appendingPathComponent("check.request"), options: .atomic)
            reload(); message = "已保存"
        } catch {
            store.settings = old
            if policyChanged {
                let policy = SenderPolicyStore(base: store.base, offline: store.isTest)
                policy.draft = old.mail_policy; await policy.save()
                if !policy.error.isEmpty { store.problem = policy.error }
            }
            if legacyStateChanged, let previousLegacyState { try? previousLegacyState.write(to: legacyStateURL, options: .atomic) }
            if ratesChanged {
                if let bytes = previousRates { try? bytes.write(to: ratesURL, options: .atomic) }
                else { try? FileManager.default.removeItem(at: ratesURL) }
            }
            for (service, account, bytes) in undo.reversed() { restoreSecret(service, account, bytes) }
            if page == .general && !store.isTest {
                if let bytes = previousLogin { try? bytes.write(to: store.loginURL, options: .atomic) }
                else { try? FileManager.default.removeItem(at: store.loginURL) }
            }
            message = error.localizedDescription
        }
    }
    private func rateKey(base: String, model: String) -> String {
        let normalized = base.trimmingCharacters(in: .whitespacesAndNewlines).replacingOccurrences(of: #"/+$"#, with: "", options: .regularExpression)
        return SHA256.hash(data: Data((normalized + "\u{0}" + model).utf8)).map { String(format: "%02x", $0) }.joined()
    }
    private func loadRates() {
        let bytes = try? Data(contentsOf: store.base.appendingPathComponent("usage-rates.json"))
        let document = bytes.flatMap { try? JSONSerialization.jsonObject(with: $0) } as? [String: Any]
        let entries = document?["rates"] as? [String: [String: Any]] ?? [:]
        let rate = entries[rateKey(base: value.api_base, model: value.api_model)] ?? entries[rateKey(base: "", model: "")] ?? [:]
        loadedRatesConfigured = rate["configured"] as? Bool ?? false
        inputRate = String(describing: rate["input_per_million"] ?? 0); outputRate = String(describing: rate["output_per_million"] ?? 0)
        currency = rate["currency"] as? String ?? "USD"
        rateBaseline = [inputRate, outputRate, currency].joined(separator: "|")
    }
    private func validClock(_ text: String) -> Bool { let p = text.split(separator: ":"); return p.count == 2 && p.allSatisfy { $0.count == 2 } && (0...23).contains(Int(p[0]) ?? -1) && (0...59).contains(Int(p[1]) ?? -1) }
    private func query(_ service: String, _ account: String) -> [String: Any] { [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service, kSecAttrAccount as String: account] }
    private func writeSecret(_ service: String, _ account: String, _ secret: String, undo: inout [(String, String, Data?)]) throws {
        if store.isTest { return }
        var q = query(service, account); q[kSecReturnData as String] = true
        var result: CFTypeRef?; let status = SecItemCopyMatching(q as CFDictionary, &result)
        guard status == errSecSuccess || status == errSecItemNotFound else { throw MailCredentials.Failure("无法读取钥匙串凭据。") }
        undo.append((service, account, result as? Data))
        try MailCredentials.save(address: account, code: secret, serviceName: service, exactAccount: true)
    }
    private func restoreSecret(_ service: String, _ account: String, _ data: Data?) {
        let q = query(service, account)
        if let data { SecItemUpdate(q as CFDictionary, [kSecValueData as String: data] as CFDictionary) }
        else { SecItemDelete(q as CFDictionary) }
    }
}

import AppKit
import SwiftUI

@MainActor
final class MailStore: ObservableObject {
    static let shared = MailStore()
    let base: URL
    let isTest: Bool
    var uninstalling = false
    var updating = false
    lazy var reportConversation = ReportConversationStore(base: base, offline: isTest)
    @Published var workspacePage: WorkspacePage = .reports
    @Published var settings = MailSettings()
    @Published var status = ServiceStatus()
    @Published var reports: [Report] = []
    @Published var selected: Report?
    @Published var reportText = ""
    @Published var problem: String?
    @Published var working = false
    @Published var checkRequested = false
    @Published var checkFeedback = ""
    @Published var mailAccount = ""
    @Published var needsAccountSetup = false
    @Published var savingAccount = false
    @Published var testingMailbox = false
    @Published var mailboxTestResult = ""
    private var requestedAfterCheck: String?
    private var requestTime: Date?
    @Published var loginEnabled = false
    @Published var alive = false
    @Published var filter = ReportFilter()
    @Published var dateFilterEnabled = false
    @Published var fromDate = Calendar.current.date(byAdding: .day, value: -7, to: Date()) ?? Date()
    @Published var toDate = Date()
    private var timer: Timer?
    private var lastScan = Date.distantPast
    private var scanning = false
    var settingsURL: URL { base.appendingPathComponent("settings.json") }
    var data: URL { base.appendingPathComponent("mail_watch") }
    var output: URL { URL(fileURLWithPath: settings.output_dir) }
    var loginURL: URL { FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/LaunchAgents/com.benson.mail-ui.plist") }
    var filteredReports: [Report] {
        var value = filter
        if dateFilterEnabled {
            value.fromDay = dayString(fromDate); value.toDay = dayString(toDate)
        }
        return reports.filter { value.matches($0) }
    }
    var senders: [String] { Array(Set(reports.map(\.sender).filter { !$0.isEmpty })).sorted() }
    func dayString(_ date: Date) -> String {
        let formatter = DateFormatter(); formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX"); formatter.timeZone = TimeZone(identifier: "Asia/Shanghai")
        formatter.dateFormat = "yyyy-MM-dd"; return formatter.string(from: date)
    }
    func resetFilters() { filter = ReportFilter(); dateFilterEnabled = false; reconcileSelection() }
    func reconcileSelection() {
        let visible = filteredReports
        if let selected, let updated = visible.first(where: { $0.id == selected.id }) { select(updated); return }
        if let first = visible.first { select(first) } else { selected = nil; reportText = "" }
    }
    var statusTitle: String {
        if !settings.enabled { return status.phase == "analyzing" ? "暂停中 · 正在完成当前邮件" : "已暂停" }
        if !alive { return "后台服务未运行" }
        switch status.phase {
        case "analyzing": return "正在分析新邮件"
        case "checking": return "正在检查邮箱"
        case "error": return "需要检查连接"
        default: return "正在监听"
        }
    }
    var statusIcon: String { !settings.enabled ? "pause.circle.fill" : (!alive || status.error != nil ? "exclamationmark.circle.fill" : "checkmark.circle.fill") }
    var lastCheck: String {
        guard let raw = status.last_check, let date = Self.parseDate(raw) else { return "尚未检查" }
        return date.formatted(.dateTime.hour().minute().second().locale(Locale(identifier: AppLanguage.shared.localeIdentifier)))
    }
    var intervalLabel: String {
        settings.interval_seconds % 60 == 0 ? "每 \(settings.interval_seconds / 60) 分钟检查" : "每 \(settings.interval_seconds) 秒检查"
    }
    func setInterval(_ text: String) {
        guard let seconds = Int(text.trimmingCharacters(in: .whitespaces)), (10...86400).contains(seconds) else {
            problem = "请输入 10 到 86400 之间的整数秒数。"; return
        }
        let old = settings
        settings.interval_seconds = seconds
        do { try save() } catch { settings = old; problem = "检查间隔保存失败：\(error.localizedDescription)" }
    }
    nonisolated static func parseDate(_ raw: String) -> Date? {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter.date(from: raw) ?? ISO8601DateFormatter().date(from: raw)
    }
    init() {
        let args = CommandLine.arguments
        isTest = args.contains("--self-test")
        if let index = args.firstIndex(of: "--fixture"), args.indices.contains(index + 1) {
            base = URL(fileURLWithPath: args[index + 1])
        } else {
            base = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/BensonMail")
        }
        if !isTest && !FileManager.default.fileExists(atPath: settingsURL.path) {
            settings.enabled = false
            do { try save() } catch { problem = "无法创建配置：\(error.localizedDescription)" }
        }
        // Load existing settings before migrating the new preference.
        refresh()
        if settings.ui_language == nil && AppLanguage.shared.canPersistInitialLanguage {
            settings.ui_language = AppLanguage.shared.code
            if !isTest { do { try save() } catch { problem = error.localizedDescription } }
        }
        if !isTest {
            mailAccount = settings.mailbox?.account ?? (settings.mailboxes == nil ? MailCredentials.account() ?? "" : "")
            needsAccountSetup = mailAccount.isEmpty || (settings.ai_provider == "api" &&
                (settings.api_base.isEmpty || settings.api_model.isEmpty))
            // Start the bundled paused service on fresh installs as well.
            startWorker()
        }
        timer = Timer.scheduledTimer(withTimeInterval: 0.5, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.refresh() }
        }
    }
    func refresh() {
        if let bytes = try? Data(contentsOf: settingsURL), let value = try? JSONDecoder().decode(MailSettings.self, from: bytes) { settings = value }
        if let bytes = try? Data(contentsOf: data.appendingPathComponent("service.json")), let value = try? JSONDecoder().decode(ServiceStatus.self, from: bytes) { status = value }
        if checkRequested {
            if status.last_check != requestedAfterCheck {
                checkRequested = false
                checkFeedback = status.error == nil ? "检查完成 · \(lastCheck)" : "检查遇到问题，请查看运行记录"
                requestTime = nil
            } else if status.phase == "checking" { checkFeedback = "正在检查邮箱…" }
            else if status.phase == "analyzing" { checkFeedback = "发现新邮件，正在分析…" }
            else if let requestTime, Date().timeIntervalSince(requestTime) > 200 {
                checkRequested = false; checkFeedback = "检查超时，请查看运行记录"
                self.requestTime = nil
            }
        }
        if let raw = status.heartbeat ?? status.last_check, let heartbeat = Self.parseDate(raw) {
            alive = Date().timeIntervalSince(heartbeat) < (status.phase == "analyzing" ? 1100 : (status.phase == "checking" ? 220 : 100))
        } else { alive = false }
        loginEnabled = FileManager.default.fileExists(atPath: loginURL.path)
        if Date().timeIntervalSince(lastScan) > 8 { scanReports() }
    }
    func save() throws {
        try FileManager.default.createDirectory(at: base, withIntermediateDirectories: true)
        try JSONEncoder().encode(settings).write(to: settingsURL, options: .atomic)
        try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: settingsURL.path)
    }
    func saveAI(provider: String, base: String, model: String, key: String, harnessPath: String = "") throws {
        guard ["api", "codex", "deepseek_harness"].contains(provider) else { throw MailCredentials.Failure("请选择分析方式。") }
        let address = base.trimmingCharacters(in: .whitespacesAndNewlines)
        let modelName = model.trimmingCharacters(in: .whitespacesAndNewlines)
        if provider == "api" {
            let destination = try MailCredentials.apiEndpoint(address)
            guard !modelName.isEmpty else { throw MailCredentials.Failure("请填写模型名。") }
            let secret = key.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !secret.isEmpty || (!isTest && MailCredentials.hasAPIKey(endpoint: destination)) else {
                throw MailCredentials.Failure("请填写此基础地址的 API Key。")
            }
            if !secret.isEmpty {
                guard !isTest else { throw MailCredentials.Failure("模拟测试不会写入真实钥匙串。") }
                try MailCredentials.save(address: destination, code: secret, serviceName: "BensonMail-AI-API", exactAccount: true)
            }
        }
        let old = settings
        settings.harness_path = harnessPath.trimmingCharacters(in: .whitespacesAndNewlines)
        settings.ai_provider = provider; settings.api_base = address; settings.api_model = modelName
        do { try save() } catch { settings = old; throw error }
    }
    func testAPI(completion: @escaping (String) -> Void) {
        guard !isTest else { completion("模拟测试不会请求真实 AI 服务。"); return }
        let executable = ServiceInstaller.worker
        let home = base.path
        Task {
            let result = await Task.detached {
                let process = Process()
                process.executableURL = executable
                process.arguments = ["--home", home, "--test-api"]
                let output = Pipe()
                process.standardOutput = output; process.standardError = FileHandle.nullDevice
                do {
                    try process.run()
                    let bytes = output.fileHandleForReading.readDataToEndOfFile()
                    process.waitUntilExit()
                    return String(data: bytes, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? "AI 连接测试失败。"
                } catch { return "无法启动连接测试，请检查后台组件。" }
            }.value
            completion(result.isEmpty ? "AI 连接测试失败，请检查后台组件。" : result)
        }
    }
    func testMailbox() {
        guard !isTest, !testingMailbox else { return }
        testingMailbox = true; mailboxTestResult = "正在连接已保存的邮箱…"
        let executable = ServiceInstaller.worker
        let home = base.path
        Task {
            let result = await Task.detached { () -> String in
                let process = Process()
                process.executableURL = executable
                process.arguments = ["--home", home, "--test-mail"]
                let output = Pipe(); process.standardOutput = output; process.standardError = FileHandle.nullDevice
                do {
                    try process.run()
                    let bytes = output.fileHandleForReading.readDataToEndOfFile()
                    process.waitUntilExit()
                    return String(data: bytes, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? "无法读取测试结果。"
                } catch { return "无法启动邮箱连接测试，请重新安装完整应用。" }
            }.value
            testingMailbox = false; mailboxTestResult = result
        }
    }
    var mailboxProfiles: [MailboxProfile] {
        if let profiles = settings.mailboxes { return profiles }
        var legacy = settings.mailbox ?? MailConnection()
        legacy.account = mailAccount
        return legacy.account.isEmpty ? [] : [MailboxProfile(connection: legacy)]
    }
    func selectMailbox(_ id: String) {
        guard let profile = mailboxProfiles.first(where: { $0.id == id }) else { return }
        let old = settings
        settings.mailbox = profile.connection
        do { try save(); mailAccount = profile.connection.account }
        catch { settings = old; problem = error.localizedDescription }
    }
    func setMailboxEnabled(_ id: String, enabled: Bool) {
        var profiles = mailboxProfiles
        guard let index = profiles.firstIndex(where: { $0.id == id }) else { return }
        profiles[index].enabled = enabled
        let old = settings
        settings.mailboxes = profiles
        do {
            try save()
            try FileManager.default.createDirectory(at: data, withIntermediateDirectories: true)
            try Data().write(to: data.appendingPathComponent("check.request"), options: .atomic)
        } catch { settings = old; problem = error.localizedDescription }
    }
    func removeMailbox(_ id: String) {
        guard !settings.enabled, !["checking", "analyzing"].contains(status.phase) else {
            problem = "请先暂停全部监听，等待当前处理完成后再移除邮箱。"; return
        }
        let old = settings
        settings.mailboxes = mailboxProfiles.filter { $0.id != id }
        if settings.mailbox?.identity == id { settings.mailbox = settings.mailboxes?.first?.connection }
        do { try save(); mailAccount = settings.mailbox?.account ?? "" }
        catch { settings = old; problem = error.localizedDescription }
    }
    func saveAccount(address raw: String, code rawCode: String, connection proposed: MailConnection? = nil,
                     adding: Bool = false, completion: @escaping (Result<Void, Error>) -> Void) {
        let address = raw.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let code = rawCode.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !isTest else { completion(.failure(MailCredentials.Failure("模拟测试不会修改真实钥匙串。"))); return }
        var previous = settings.mailbox ?? MailConnection()
        previous.account = mailAccount
        var next = proposed ?? previous
        next.account = address
        do { next = try next.validated() }
        catch { completion(.failure(error)); return }
        let switching = adding || (!mailAccount.isEmpty && previous.identity != next.identity)
        do { try MailCredentials.validate(address: address, code: code, existing: switching ? nil : mailAccount) }
        catch { completion(.failure(error)); return }
        if settings.enabled || status.phase == "checking" || status.phase == "analyzing" || checkRequested {
            completion(.failure(MailCredentials.Failure("请先暂停全部监听，等当前邮件处理完成后再编辑或添加邮箱。"))); return
        }
        savingAccount = true
        Task {
            let originalSettings = settings
            do {
                var profiles = mailboxProfiles
                if profiles.contains(where: { $0.id == next.identity && (adding || $0.id != previous.identity) }) {
                    throw MailCredentials.Failure("此邮箱连接已经添加，请从账号列表中选择。")
                }
                let legacyState = data.appendingPathComponent("state.json")
                if !mailAccount.isEmpty, let bytes = try? Data(contentsOf: legacyState),
                   var value = try? JSONSerialization.jsonObject(with: bytes) as? [String: Any],
                   value["mailbox_key"] == nil {
                    value["mailbox_key"] = previous.identity
                    try JSONSerialization.data(withJSONObject: value).write(to: legacyState, options: .atomic)
                }
                if !code.isEmpty {
                    next.secret_service = "BensonMail-IMAP"
                    next.secret_account = next.identity
                    try MailCredentials.save(address: next.secret_account, code: code, serviceName: next.secret_service, exactAccount: true)
                } else {
                    next.secret_service = previous.secret_service
                    next.secret_account = previous.secret_account
                }
                settings.mailbox = next
                let wasEnabled = adding ? true : (profiles.first(where: { $0.id == previous.identity })?.enabled ?? true)
                if !adding { profiles.removeAll { $0.id == previous.identity } }
                profiles.append(MailboxProfile(connection: next, enabled: wasEnabled))
                settings.mailboxes = profiles
                try save()
                mailAccount = address
                startWorker()
                savingAccount = false
                completion(.success(()))
            } catch {
                settings = originalSettings
                savingAccount = false
                startWorker()
                completion(.failure(error))
            }
        }
    }
    func toggle() {
        if !settings.enabled && !isTest && (mailAccount.isEmpty ||
            (settings.ai_provider == "api" && (settings.api_base.isEmpty || settings.api_model.isEmpty))) {
            needsAccountSetup = true
            return
        }
        let old = settings
        settings.enabled.toggle()
        do {
            try save()
            if settings.enabled { startWorker() }
        } catch { settings = old; problem = "无法保存监听设置：\(error.localizedDescription)" }
    }
    func pauseForUpdate() throws -> Bool {
        let wasEnabled = settings.enabled
        settings.enabled = false
        do { try save() } catch { settings.enabled = wasEnabled; throw error }
        return wasEnabled
    }
    func restoreAfterUpdate(_ enabled: Bool) throws {
        settings.enabled = enabled
        try save()
    }
    func prepareForExit() throws {
        let old = settings
        settings.enabled = false
        do { try save() }
        catch { settings = old; throw error }
    }
    func checkNow() {
        guard settings.enabled, !checkRequested else { return }
        do {
            try FileManager.default.createDirectory(at: data, withIntermediateDirectories: true)
            try Data().write(to: data.appendingPathComponent("check.request"), options: .atomic)
            requestedAfterCheck = status.last_check
            requestTime = Date()
            checkRequested = true
            checkFeedback = "已请求检查，正在连接邮箱…"
            if !alive { startWorker() }
        } catch { problem = "无法请求检查：\(error.localizedDescription)" }
    }
    func startWorker() {
        guard !isTest else { return }
        working = true
        Task {
            let home = base
            let failure = await Task.detached { () -> String? in
                do { try ServiceInstaller.launch(base: home); return nil }
                catch { return error.localizedDescription }
            }.value
            working = false
            if let failure { problem = failure }
        }
    }
    nonisolated static func run(_ executable: String, _ arguments: [String]) -> Int32 {
        let process = Process(); process.executableURL = URL(fileURLWithPath: executable); process.arguments = arguments
        process.standardOutput = FileHandle.nullDevice; process.standardError = FileHandle.nullDevice
        do { try process.run(); process.waitUntilExit(); return process.terminationStatus } catch { return -1 }
    }
    func scanReports() {
        guard !scanning else { return }
        scanning = true
        lastScan = Date()
        let directory = output
        let metadataDirectory = data
        let cached = Dictionary(uniqueKeysWithValues: reports.map { ($0.id, $0) })
        Task {
            let found = await Task.detached { ReportIndex.reports(in: directory, data: metadataDirectory, cached: cached) }.value
            scanning = false
            guard output == directory else { scanReports(); return }
            reports = found
            reconcileSelection()
        }
    }
    func select(_ report: Report) {
        selected = report
        reportText = report.text.isEmpty ? "报告无法读取，请检查文件权限。" : report.text
    }
    func applyRegeneratedReport(_ originalPath: String, url: URL, text: String) {
        guard let original = reports.first(where: { $0.id == originalPath }) else { return }
        let stamp = (try? url.resourceValues(forKeys: [.contentModificationDateKey]))?.contentModificationDate ?? Date()
        let updated = Report(url: url, modified: stamp, metadataModified: original.metadataModified,
            sender: original.sender, body: original.body, attachmentNames: original.attachmentNames,
            hasAttachments: original.hasAttachments, text: text, subject: original.subject, receivedAt: original.receivedAt)
        reports = reports.map { $0.id == originalPath ? updated : $0 }
        if selected?.id == originalPath { select(updated) }
    }
    func openFolder() {
        do { try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true); NSWorkspace.shared.open(output) }
        catch { problem = "无法打开保存文件夹：\(error.localizedDescription)" }
    }
    func chooseFolder() {
        let panel = NSOpenPanel(); panel.title = T("选择邮件报告保存文件夹"); panel.canChooseFiles = false
        panel.canChooseDirectories = true; panel.canCreateDirectories = true; panel.allowsMultipleSelection = false
        panel.directoryURL = output; panel.prompt = T("选择此文件夹")
        panel.begin { [weak self] response in
            guard response == .OK, let url = panel.url, let self else { return }
            let old = self.settings
            do {
                try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
                guard FileManager.default.isWritableFile(atPath: url.path) else { throw CocoaError(.fileWriteNoPermission) }
                self.settings.output_dir = url.path; try self.save()
                self.selected = nil; self.reportText = ""; self.scanReports()
            } catch { self.settings = old; self.problem = "无法使用此文件夹：\(error.localizedDescription)" }
        }
    }
    func setLogin(_ enabled: Bool) {
        guard !isTest else { return }
        do {
            if enabled {
                let value: [String: Any] = ["Label": "com.benson.mail-ui", "ProgramArguments": ["/usr/bin/open", "-g", Bundle.main.bundlePath, "--args", "--background"], "RunAtLoad": true]
                try FileManager.default.createDirectory(at: loginURL.deletingLastPathComponent(), withIntermediateDirectories: true)
                try PropertyListSerialization.data(fromPropertyList: value, format: .xml, options: 0).write(to: loginURL, options: .atomic)
            } else if FileManager.default.fileExists(atPath: loginURL.path) { try FileManager.default.removeItem(at: loginURL) }
            loginEnabled = enabled
        } catch { problem = "无法保存登录启动设置：\(error.localizedDescription)" }
    }
}

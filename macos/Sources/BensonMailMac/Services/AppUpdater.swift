import AppKit
import Foundation
import SwiftUI

struct MailUpdate: Equatable {
    let version: String
    let url: URL
    let sha256: String
    let notes: String
    let size: Int64?
    let translations: [String: String]
    var mirrors: [URL] = []
    func localizedNotes(for language: String) -> String { translations[language] ?? notes }
}

@MainActor final class AppUpdater: ObservableObject {
    static let interval: TimeInterval = 5 * 60 * 60
    static let canonicalManifest = "https://raw.githubusercontent.com/Benson-YiYan/benson-mail-assistant/main/distribution/manifest.json"
    static let manifestAPI = "https://api.github.com/repos/Benson-YiYan/benson-mail-assistant/contents/distribution/manifest.json?ref=main"
    static let latestRelease = URL(string: "https://github.com/Benson-YiYan/benson-mail-assistant/releases/latest")!
    static let shared = AppUpdater()
    @Published private(set) var checking = false
    @Published private(set) var status = ""
    @Published private(set) var detail = ""
    @Published private(set) var checkFailed = false
    @Published private(set) var available: MailUpdate?
    private let defaults: UserDefaults
    private let currentVersion: String
    private let transferFactory: () -> UpdateTransfer
    private let downloadRoot: URL
    private let endpoint: () -> URL?
    private let fetch: (URLRequest) async throws -> (Data, HTTPURLResponse)
    @Published private(set) var downloading = false
    @Published private(set) var installing = false
    @Published private(set) var downloaded: URL?
    @Published private(set) var verifiedRelease: MailUpdate?
    @Published private(set) var received: Int64 = 0
    @Published private(set) var total: Int64 = 0
    @Published private(set) var completionNotice = ""
    private var transfer: UpdateTransfer?
    private var workspace: URL?
    private var timer: Timer?
    private static let lastCheckKey = "BensonMail.update.lastCheck"
    static var platform: String {
        #if arch(arm64)
        return "macos-arm64"
        #else
        return "macos-x86_64"
        #endif
    }
    init(defaults: UserDefaults = .standard,
         currentVersion: String = Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "000000000000",
         downloadRoot: URL = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0].appendingPathComponent("BensonMail/Updates"),
         transferFactory: @escaping () -> UpdateTransfer = { UpdateTransfer() },
         endpoint: @escaping () -> URL? = {
             let configured = Bundle.main.infoDictionary?["BensonMailUpdateManifestURL"] as? String
             if configured == nil || configured?.contains("/benson-mail-updates/") == true {
                 return URL(string: AppUpdater.canonicalManifest)
             }
             return configured.flatMap(URL.init(string:))
         },
         fetch: @escaping (URLRequest) async throws -> (Data, HTTPURLResponse) = { request in
             let (data, response) = try await URLSession.shared.data(for: request)
             guard let http = response as? HTTPURLResponse else { throw UpdateError.invalid(T("更新服务器未返回 HTTP 响应。")) }
             return (data, http)
         }) {
        self.defaults = defaults; self.currentVersion = currentVersion; self.endpoint = endpoint; self.fetch = fetch
        self.transferFactory = transferFactory; self.downloadRoot = downloadRoot
    }
    private func fetchManifest(_ request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        // The raw and API routes are in the same public repository. Custom/test endpoints never leak to GitHub.
        guard request.url?.absoluteString == Self.canonicalManifest else { return try await fetch(request) }
        do {
            let result = try await fetch(request)
            if result.1.statusCode == 200 { return result }
        } catch { /* Try the independent GitHub API route if the raw host is unreachable. */ }
        var fallback = URLRequest(url: URL(string: Self.manifestAPI)!, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 25)
        fallback.setValue("application/vnd.github.raw+json", forHTTPHeaderField: "Accept")
        return try await fetch(fallback)
    }
    var lastCheck: Date? {
        let stamp = defaults.double(forKey: Self.lastCheckKey)
        return stamp > 0 ? Date(timeIntervalSince1970: stamp) : nil
    }
    func isDue(at now: Date = Date()) -> Bool { lastCheck.map { now.timeIntervalSince($0) >= Self.interval || $0 > now } ?? true }
    func start() {
        guard timer == nil else { return }
        schedule()
        inspectInstallationResults()
    }
    private func schedule() {
        timer?.invalidate()
        let delay = isDue() ? 1 : (lastCheck.map { max(1, Self.interval - Date().timeIntervalSince($0)) } ?? 1)
        timer = Timer.scheduledTimer(withTimeInterval: min(Self.interval, delay), repeats: false) { [weak self] _ in
            Task { @MainActor in
                guard let self else { return }
                await self.check(manual: false)
                self.schedule()
            }
        }
    }
    func check(manual: Bool) async {
        guard !checking, !downloading, !installing, manual || isDue() else { return }
        checking = true
        checkFailed = false
        if manual { detail = "" }
        defaults.set(Date().timeIntervalSince1970, forKey: Self.lastCheckKey)
        defer { checking = false }
        do {
            guard let address = endpoint(), Self.secure(address) else { throw UpdateError.endpoint }
            var request = URLRequest(url: address, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 25)
            request.setValue("application/json", forHTTPHeaderField: "Accept")
            let (data, response) = try await fetchManifest(request)
            guard response.statusCode == 200 else { throw UpdateError.invalid(T("更新服务器返回 HTTP 状态：") + String(response.statusCode)) }
            guard response.url.map(Self.secure) == true else { throw UpdateError.invalid(T("更新响应地址必须使用 HTTPS。")) }
            guard data.count <= 1_048_576 else { throw UpdateError.invalid(T("更新清单超过 1 MB。")) }
            let update = try Self.parse(data, platform: Self.platform, current: currentVersion)
            available = update
            if update != nil { status = "发现新版本" }
            else if manual { status = "当前已是最新版本。" }
        } catch {
            checkFailed = true
            if manual {
                status = "检查更新失败，请检查网络后重试。"
                if let network = error as? URLError { detail = T("网络错误代码：") + String(network.errorCode) + " · " + network.localizedDescription }
                else { detail = error.localizedDescription }
            }
        }
    }
    func download() {
        guard !downloading, !installing, let update = available else { return }
        downloading = true; downloaded = nil; verifiedRelease = nil; received = 0; total = update.size ?? 0; detail = ""
        status = "正在下载更新…"
        let operation = transferFactory(); transfer = operation
        Task { [self] in
            do {
                let root = downloadRoot.appendingPathComponent(UUID().uuidString)
                try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
                workspace = root
                downloaded = try await operation.run(url: update.url, mirrors: update.mirrors, destination: root.appendingPathComponent("update.dmg"), sha256: update.sha256, size: update.size) { [weak self] bytes, total in
                    Task { @MainActor in self?.received = bytes; self?.total = total }
                }
                verifiedRelease = update
                status = "下载已完成并通过 SHA256 校验。"
            } catch {
                if let root = workspace { try? FileManager.default.removeItem(at: root) }
                workspace = nil; downloaded = nil
                if (error as? URLError)?.code == .cancelled { status = "下载已取消。" }
                else { status = "下载失败，可重试。"; detail = error.localizedDescription }
            }
            downloading = false; transfer = nil
        }
    }
    func cancelDownload() { transfer?.cancel() }
    func restartDownload() {
        guard !downloading, !installing else { return }
        if available == nil { available = verifiedRelease }
        if let root = workspace { try? FileManager.default.removeItem(at: root) }
        workspace = nil; downloaded = nil; verifiedRelease = nil
        download()
    }
    func install() {
        guard !installing, let update = verifiedRelease, let image = downloaded, let root = workspace else { return }
        installing = true; status = "正在准备安装…"; detail = ""
        Task {
            let store = MailStore.shared
            let wasEnabled = store.settings.enabled
            var paused = false
            var preparedPlan: String?
            do {
                let targetPath = Bundle.main.bundleURL.path
                let markerPath = store.base.appendingPathComponent("worker-installation.json").path
                let architecture = Self.platform == "macos-arm64" ? "arm64" : "x86_64"
                let prepared = try await Task.detached { () throws -> [String: String] in
                    try UpdateTransfer.verify(image, sha256: update.sha256, size: update.size)
                    let request: [String: Any] = ["workspace": root.path, "dmg": image.path,
                        "target": targetPath, "version": update.version,
                        "arch": architecture,
                        "parent_pid": ProcessInfo.processInfo.processIdentifier,
                        "marker": markerPath, "sha256": update.sha256, "size": update.size.map { NSNumber(value: $0) } ?? NSNull()]
                    let input = root.appendingPathComponent("prepare.json"), output = root.appendingPathComponent("prepared.json")
                    try JSONSerialization.data(withJSONObject: request).write(to: input, options: .atomic)
                    let process = Process(); process.executableURL = ServiceInstaller.worker
                    process.arguments = ["--update-install", "prepare", input.path, output.path]
                    process.standardOutput = FileHandle.nullDevice; process.standardError = FileHandle.nullDevice
                    try process.run(); process.waitUntilExit()
                    guard let result = try JSONSerialization.jsonObject(with: Data(contentsOf: output)) as? [String: Any],
                          result["ok"] as? Bool == true, let helper = result["helper"] as? String, let plan = result["plan"] as? String else {
                        let value = (try? Data(contentsOf: output)).flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String: Any] }
                        throw UpdateError.invalid(value?["error"] as? String ?? "Update preparation failed")
                    }
                    return ["helper": helper, "plan": plan]
                }.value
                preparedPlan = prepared["plan"]
                _ = try store.pauseForUpdate(); paused = true
                status = "等待当前邮件任务完成…"
                let deadline = Date().addingTimeInterval(920)
                try await Task.sleep(nanoseconds: 1_500_000_000)
                while Self.mailBusy(at: store.data.appendingPathComponent("service.json")) {
                    guard Date() < deadline else { throw UpdateError.invalid("Timed out waiting for the current mail task") }
                    try await Task.sleep(nanoseconds: 500_000_000)
                }
                try await Task.detached { try ServiceInstaller.stop() }.value
                try store.restoreAfterUpdate(wasEnabled)
                let helper = Process(); helper.executableURL = URL(fileURLWithPath: prepared["helper"]!)
                helper.arguments = ["--update-install", "install", prepared["plan"]!]
                helper.currentDirectoryURL = root.deletingLastPathComponent()
                helper.standardInput = FileHandle.nullDevice; helper.standardOutput = FileHandle.nullDevice; helper.standardError = FileHandle.nullDevice
                try helper.run()
                store.updating = true
                NSApp.terminate(nil)
            } catch {
                if let plan = preparedPlan {
                    await Task.detached {
                        let process = Process(); process.executableURL = ServiceInstaller.worker
                        process.arguments = ["--update-install", "abort", plan]
                        process.standardOutput = FileHandle.nullDevice; process.standardError = FileHandle.nullDevice
                        try? process.run(); process.waitUntilExit()
                    }.value
                }
                if paused { try? store.restoreAfterUpdate(wasEnabled); store.startWorker() }
                installing = false; status = "更新安装失败，原应用已保留。"; detail = error.localizedDescription
            }
        }
    }
    func recordUpdateReceipt() {
        let args = CommandLine.arguments
        guard let index = args.firstIndex(of: "--update-receipt"), index + 1 < args.count,
              let ni = args.firstIndex(of: "--update-nonce"), ni + 1 < args.count else { return }
        let file = URL(fileURLWithPath: args[index + 1]).resolvingSymlinksInPath()
        let cache = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0].appendingPathComponent("BensonMail/Updates").resolvingSymlinksInPath()
        guard file.path.hasPrefix(cache.path + "/"), file.lastPathComponent == "startup-receipt.json",
              let data = try? Data(contentsOf: file.deletingLastPathComponent().appendingPathComponent("install-plan.json")),
              let plan = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              plan["nonce"] as? String == args[ni + 1], plan["version"] as? String == currentVersion,
              plan["target"] as? String == Bundle.main.bundleURL.resolvingSymlinksInPath().path else { return }
        let receipt: [String: Any] = ["version": currentVersion, "nonce": args[ni + 1], "pid": ProcessInfo.processInfo.processIdentifier]
        if let bytes = try? JSONSerialization.data(withJSONObject: receipt), (try? bytes.write(to: file, options: .atomic)) != nil {
            completionNotice = "更新安装完成。"; status = "更新安装完成。"; detail = currentVersion
        }
    }
    private func inspectInstallationResults() {
        let root = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0].appendingPathComponent("BensonMail/Updates")
        for directory in (try? FileManager.default.contentsOfDirectory(at: root, includingPropertiesForKeys: nil)) ?? [] {
            let acknowledgement = directory.appendingPathComponent("notice-shown")
            guard !FileManager.default.fileExists(atPath: acknowledgement.path),
                  let data = try? Data(contentsOf: directory.appendingPathComponent("installation-result.json")),
                  let result = try? JSONSerialization.jsonObject(with: data) as? [String: Any], result["ok"] as? Bool == false else { continue }
            completionNotice = "更新失败，已保留或恢复原应用。"; status = completionNotice
            detail = result["error"] as? String ?? ""
            try? Data().write(to: acknowledgement)
        }
    }
    func dismissCompletionNotice() { completionNotice = "" }
    nonisolated static func mailBusy(at file: URL) -> Bool {
        guard let data = try? Data(contentsOf: file), let value = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return false }
        return ["checking", "analyzing"].contains(value["phase"] as? String ?? "")
    }
    nonisolated static func secure(_ url: URL) -> Bool {
        url.scheme?.lowercased() == "https" && url.host?.isEmpty == false && url.user == nil && url.password == nil
    }
    nonisolated static func parse(_ data: Data, platform: String, current: String) throws -> MailUpdate? {
        let value: [String: Any]
        do {
            guard let root = try JSONSerialization.jsonObject(with: data) as? [String: Any] else { throw UpdateError.invalid(T("更新清单根节点必须为对象。")) }
            value = root
        } catch let failure as UpdateError { throw failure }
          catch { throw UpdateError.invalid(T("更新清单不是有效 JSON。")) }
        guard value["schema_version"] as? Int == 1 else { throw UpdateError.invalid(T("不支持的更新清单版本：schema_version 应为 1。")) }
        guard let platforms = value["platforms"] as? [String: Any], let entry = platforms[platform] as? [String: Any] else { throw UpdateError.invalid(T("更新清单缺少平台：") + platform) }
        guard let version = entry["version"] as? String, version.range(of: #"^\d{12}$"#, options: .regularExpression) != nil else { throw UpdateError.invalid(T("更新清单 version 必须为 12 位年月日时分。")) }
        guard let link = entry["url"] as? String, let url = URL(string: link), secure(url) else { throw UpdateError.invalid(T("更新清单下载地址必须为不含账号密码的 HTTPS URL。")) }
        guard let sha = entry["sha256"] as? String, sha.range(of: #"^[A-Fa-f0-9]{64}$"#, options: .regularExpression) != nil else { throw UpdateError.invalid(T("更新清单 sha256 必须为 64 位十六进制字符。")) }
        let translations = entry["notes"] as? [String: String] ?? [:]
        guard let notes = (entry["notes"] as? String) ?? translations["zh"] ?? translations["en"] ?? translations.values.first,
              notes.count <= 20000, translations.values.allSatisfy({ $0.count <= 20000 }) else { throw UpdateError.invalid(T("更新清单 notes 必须为文字或中英文对象，每项不超过 20000 字符。")) }
        guard version > current else { return nil }
        let size = (entry["size"] as? NSNumber)?.int64Value
        if let size, size <= 0 { throw UpdateError.invalid("Manifest size must be positive") }
        var mirrors: [URL] = []
        if let raw = entry["mirrors"] {
            guard let values = raw as? [String], values.count <= 3 else { throw UpdateError.invalid("Manifest mirrors must contain at most 3 HTTPS URLs") }
            for value in values {
                guard let mirror = URL(string: value), secure(mirror) else { throw UpdateError.invalid("Mirror URL must use HTTPS") }
                if mirror != url && !mirrors.contains(mirror) { mirrors.append(mirror) }
            }
        }
        return MailUpdate(version: version, url: url, sha256: sha.lowercased(), notes: notes, size: size, translations: translations, mirrors: mirrors)
    }
    enum UpdateError: LocalizedError {
        case invalid(String), endpoint
        var errorDescription: String? {
            switch self {
            case .invalid(let message): return message
            case .endpoint: return T("更新清单地址必须使用 HTTPS。")
            }
        }
    }
}

struct UpdateSettings: View {
    @ObservedObject private var updater = AppUpdater.shared
    @ObservedObject private var language = AppLanguage.shared
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(T("每 5 小时自动检查更新，无新版时不打扰。"))
                .font(.caption).foregroundStyle(.secondary)
            Button(updater.checking ? T("正在检查更新…") : T("检查更新")) {
                Task { await updater.check(manual: true) }
            }.disabled(updater.checking || updater.downloading || updater.installing).accessibilityIdentifier("check-app-updates")
            if !updater.status.isEmpty { Text(T(updater.status)).font(.callout).textSelection(.enabled) }
            if !updater.detail.isEmpty { Text(updater.detail).font(.caption).textSelection(.enabled) }
            if updater.checkFailed {
                Link(T("前往 GitHub 下载最新版"), destination: AppUpdater.latestRelease)
                    .buttonStyle(.bordered)
                    .accessibilityIdentifier("update-github-fallback")
            }
            if let update = updater.verifiedRelease ?? updater.available {
                Text(T("新版本") + " " + update.version).font(.headline)
                Text(update.localizedNotes(for: language.code)).textSelection(.enabled)
                UpdateActions()
                Text(T("在应用内下载并校验，确认后安装并重新打开。"))
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
    }
}

struct UpdateActions: View {
    @ObservedObject private var updater = AppUpdater.shared
    @ObservedObject private var language = AppLanguage.shared
    var showStatus = false
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if showStatus {
                Text(T(updater.status)).font(.caption)
                if !updater.detail.isEmpty { Text(updater.detail).font(.caption).lineLimit(3).textSelection(.enabled) }
            }
            if updater.downloading {
                if updater.total > 0 { ProgressView(value: Double(updater.received), total: Double(updater.total)) }
                else { ProgressView() }
                if updater.total > 0 {
                    Text(String(format: "%.0f%% · %.1f / %.1f MB", 100*Double(updater.received)/Double(updater.total), Double(updater.received)/1048576, Double(updater.total)/1048576))
                } else { Text(String(format: "%.1f MB", Double(updater.received)/1048576)) }
                Button(T("取消下载")) { updater.cancelDownload() }
            } else if updater.downloaded != nil {
                HStack {
                    Button(updater.installing ? T("正在安装…") : T("安装并重新打开")) { updater.install() }.disabled(updater.installing)
                    Button(T("重新下载")) { updater.restartDownload() }.disabled(updater.installing)
                }
            } else { Button(T("下载／重试更新")) { updater.download() }.disabled(updater.installing) }
        }
    }
}

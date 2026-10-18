import AppKit
import UserNotifications

struct MailNotice: Codable {
    let id: String
    let title: String
    let body: String
    let created: Double
    let report: String?
}

@MainActor
final class MailNotifications: NSObject, UNUserNotificationCenterDelegate {
    static let shared = MailNotifications()
    private let center = UNUserNotificationCenter.current()
    private var timer: Timer?
    private var processing = false
    private var askedPermission = false
    var showMainWindow: (() -> Void)?
    var userOpenedWindow = false
    private var queue: URL {
        MailStore.shared.base.appendingPathComponent("notifications/pending", isDirectory: true)
    }
    private var state: URL {
        MailStore.shared.base.appendingPathComponent("notifications/status.json")
    }

    func start() {
        guard !MailStore.shared.isTest else { return }
        center.delegate = self
        timer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { [weak self] _ in
            Task { @MainActor in await self?.drain() }
        }
        Task { await drain() }
    }

    static func content(_ notice: MailNotice) -> UNMutableNotificationContent {
        let content = UNMutableNotificationContent()
        content.title = T(notice.title)
        content.body = T(notice.body)
        content.sound = .default
        content.threadIdentifier = "benson-mail"
        if let report = notice.report { content.userInfo["reportPath"] = report }
        return content
    }

    private func record(permission: UNAuthorizationStatus, extra: [String: String] = [:]) {
        let name: String
        switch permission {
        case .authorized: name = "authorized"
        case .provisional: name = "provisional"
        case .denied: name = "denied"
        case .notDetermined: name = "notDetermined"
        default: name = "unknown"
        }
        var value = (try? JSONSerialization.jsonObject(with: Data(contentsOf: state))) as? [String: String] ?? [:]
        let previous = value
        value["permission"] = name
        value["bundle"] = Bundle.main.bundleIdentifier ?? ""
        value.merge(extra) { _, latest in latest }
        guard value != previous else { return }
        if let bytes = try? JSONSerialization.data(withJSONObject: value) {
            try? FileManager.default.createDirectory(at: state.deletingLastPathComponent(), withIntermediateDirectories: true)
            try? bytes.write(to: state, options: .atomic)
            try? FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: state.path)
        }
    }

    func drain() async {
        guard !processing else { return }
        processing = true
        defer { processing = false }
        var authorization = (await center.notificationSettings()).authorizationStatus
        if authorization == .notDetermined && !askedPermission {
            askedPermission = true
            _ = try? await center.requestAuthorization(options: [.alert, .sound, .badge])
            authorization = (await center.notificationSettings()).authorizationStatus
        }
        record(permission: authorization)
        guard authorization == .authorized || authorization == .provisional else { return }
        let files = (try? FileManager.default.contentsOfDirectory(at: queue, includingPropertiesForKeys: nil)) ?? []
        for file in files.filter({ $0.pathExtension == "json" }).sorted(by: { $0.lastPathComponent < $1.lastPathComponent }) {
            guard let data = try? Data(contentsOf: file),
                  let notice = try? JSONDecoder().decode(MailNotice.self, from: data) else { continue }
            guard Date().timeIntervalSince1970 - notice.created < 86400 else {
                try? FileManager.default.removeItem(at: file)
                continue
            }
            do {
                try await center.add(UNNotificationRequest(identifier: notice.id, content: Self.content(notice), trigger: nil))
                try FileManager.default.removeItem(at: file)
                record(permission: authorization, extra: ["lastPosted": notice.id, "lastError": ""])
            } catch {
                record(permission: authorization, extra: ["lastError": error.localizedDescription])
            }
        }
    }

    func openWindow(report: String? = nil) {
        userOpenedWindow = true
        NSApp.unhide(nil)
        NSApp.activate(ignoringOtherApps: true)
        let store = MailStore.shared
        store.refresh()
        store.scanReports()
        if let report, let match = store.reports.first(where: { $0.url.path == report }) { store.select(match) }
        if let window = NSApp.windows.first(where: { ["邮件小秘书", "Mail Secretary"].contains($0.title) }) {
            window.makeKeyAndOrderFront(nil)
            window.orderFrontRegardless()
        } else { showMainWindow?() }
    }

    nonisolated func userNotificationCenter(_ center: UNUserNotificationCenter,
                                           willPresent notification: UNNotification,
                                           withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        completionHandler([.banner, .list, .sound])
    }

    nonisolated func userNotificationCenter(_ center: UNUserNotificationCenter,
                                           didReceive response: UNNotificationResponse,
                                           withCompletionHandler completionHandler: @escaping () -> Void) {
        let report = response.notification.request.content.userInfo["reportPath"] as? String
        Task { @MainActor in
            self.openWindow(report: report)
            completionHandler()
        }
    }
}

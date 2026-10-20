import SwiftUI
import AppKit

struct MailMenu: View {
    @ObservedObject private var language = AppLanguage.shared
    @ObservedObject var store: MailStore
    @Environment(\.openWindow) private var openWindow
    var body: some View {
        Text(T(store.statusTitle))
        Text(T("最近检查：\(T(store.lastCheck))"))
        Text(T(store.intervalLabel))
        Divider()
        Button(T("打开邮件小秘书")) {
            if let window = NSApp.windows.first(where: { AppLanguage.appNames.contains($0.title) && $0.canBecomeMain }) {
                window.makeKeyAndOrderFront(nil)
            } else { openWindow(id: "main") }
            NSApp.activate(ignoringOtherApps: true)
        }
        Button(store.settings.enabled ? T("暂停监听") : T("开始监听")) { store.toggle() }.disabled(store.working)
        Button(T(store.settings.notifications_enabled ? "暂停系统通知" : "开启系统通知")) { store.toggleNotifications() }
        Button(store.checkRequested ? T("检查中…") : T("立即检查")) { store.checkNow() }.disabled(!store.settings.enabled || store.checkRequested || store.status.phase == "analyzing" || store.status.phase == "checking")
        if !store.checkFeedback.isEmpty { Text(T(store.checkFeedback)) }
        Button(T("打开报告文件夹")) { store.openFolder() }
        if let first = store.reports.first {
            Button(T("打开最新报告")) { NSWorkspace.shared.open(first.url) }
        }
        Divider()
        Button(T("设置……")) {
            if store.settingsDraft.navigate(.general) || store.workspacePage == .general {
                openWindow(id: "main"); NSApp.activate(ignoringOtherApps: true)
            }
        }
        Button(T("退出邮件小秘书")) { NSApp.terminate(nil) }
    }
}

import SwiftUI
import AppKit

final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        DispatchQueue.main.async { MailHelp.refreshTitle() }
        MailNotifications.shared.start()
        if !MailStore.shared.isTest { AppUpdater.shared.start(); AppUpdater.shared.recordUpdateReceipt() }
        if CommandLine.arguments.contains("--background") {
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.7) {
                if !MailNotifications.shared.userOpenedWindow {
                    NSApp.windows.filter { ["邮件小秘书", "Mail Secretary"].contains($0.title) }.forEach { $0.orderOut(nil) }
                }
            }
        } else { NSApp.activate(ignoringOtherApps: true) }
        if CommandLine.arguments.contains("--self-test") {
            DispatchQueue.main.asyncAfter(deadline: .now() + 2) { Task { await AppSelfTest.run() } }
        }
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        let store = MailStore.shared
        guard !store.isTest, !store.uninstalling, !store.updating else { return .terminateNow }
        do { try store.prepareForExit() }
        catch {
            store.problem = "无法保存退出状态：\(error.localizedDescription)"
            return .terminateCancel
        }
        do {
            try ServiceInstaller.stop()
            return .terminateNow
        } catch {
            store.problem = "停止后台服务失败：\(error.localizedDescription)"
            return .terminateCancel
        }
    }
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        MailNotifications.shared.openWindow()
        return true
    }
}

@main
struct BensonMailMacApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @StateObject private var language = AppLanguage.shared
    @StateObject private var store = MailStore.shared
    var body: some Scene {
        WindowGroup(T("邮件小秘书"), id: "main") { ContentView(store: store).environment(\.locale, Locale(identifier: language.code == "zh" ? "zh_CN" : "en_US")) }
            .defaultSize(width: 1120, height: 760)
            .commands {
                CommandGroup(replacing: .newItem) {}
                MailHelpCommands()
            }
        MenuBarExtra {
            MailMenu(store: store).environment(\.locale, Locale(identifier: language.code == "zh" ? "zh_CN" : "en_US"))
        } label: {
            Image(systemName: store.settings.enabled ? "envelope" : "envelope.badge").accessibilityLabel(T("邮件小秘书"))
        }
        Settings { SettingsView(store: store).environment(\.locale, Locale(identifier: language.code == "zh" ? "zh_CN" : "en_US")) }
    }
}

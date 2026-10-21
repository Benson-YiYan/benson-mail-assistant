import AppKit
import SwiftUI

struct MailHelpCommands: Commands {
    @ObservedObject private var language = AppLanguage.shared
    var body: some Commands {
        CommandGroup(replacing: .help) {
            Button(language.translate("使用指南")) { MailHelp.openQuickStart() }
                .help(language.translate("查看所有功能和设置的逐步说明，包括通知、草稿、邮件问答、历史总结、费用、诊断和更新。"))
            Button(language.translate("如何获取授权码？")) { MailHelp.openAccountGuide() }
            Divider()
            Button(language.translate("检查更新")) {
                MailNotifications.shared.openWindow()
                Task { await AppUpdater.shared.check(manual: true) }
            }
            Divider()
            Button(language.translate("关于邮件小秘书")) { MailHelp.about() }
        }
    }
}

@MainActor
enum MailHelp {
    static func quickStartURL(language: String = AppLanguage.shared.code) -> URL? {
        AppLanguage.shared.guideURL("quick_start", language: language)
    }
    static func refreshTitle() {
        if let appItem = NSApp.mainMenu?.items.first {
            appItem.title = T("邮件小秘书")
            appItem.submenu?.title = T("邮件小秘书")
        }
        guard let help = NSApp.helpMenu,
              let item = NSApp.mainMenu?.items.first(where: { $0.submenu === help }) else { return }
        item.title = T("帮助")
        help.title = T("帮助")
        // AppKit can defer rebuilding SwiftUI commands while the app is inactive.
        let labels = ["使用指南", "如何获取授权码？", "检查更新", "关于邮件小秘书"]
        let actions = help.items.filter { !$0.isSeparatorItem }
        if actions.count == labels.count {
            for (action, label) in zip(actions, labels) { action.title = T(label) }
        }
    }
    static func openQuickStart() {
        guard let file = quickStartURL(), NSWorkspace.shared.open(file) else {
            MailStore.shared.problem = T("请先下载当前语言包，再打开指南。")
            return
        }
    }
    static func openAccountGuide() {
        do { try MailAccountGuide.open() }
        catch { MailStore.shared.problem = error.localizedDescription }
    }
    static func about() {
        let alert = NSAlert()
        alert.messageText = T("关于邮件小秘书")
        #if arch(arm64)
        let architecture = "Apple silicon (arm64)"
        #else
        let architecture = "Intel (x86_64)"
        #endif
        let version = Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "—"
        alert.informativeText = T("邮件小秘书") + "\n" + T("版本") + ": " + version + "\n" + architecture
        alert.addButton(withTitle: T("好"))
        NSApp.activate(ignoringOtherApps: true)
        alert.runModal()
    }
}

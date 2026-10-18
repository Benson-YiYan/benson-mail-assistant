import AppKit
import SwiftUI

struct MailHelpCommands: Commands {
    @ObservedObject private var language = AppLanguage.shared
    var body: some Commands {
        CommandGroup(replacing: .help) {
            Button(language.translate("使用指南")) { MailHelp.openQuickStart() }
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
        Bundle.main.url(forResource: "Quick-start-" + (language == "en" ? "en" : "zh"), withExtension: "txt")
    }
    static func refreshTitle() {
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
            MailStore.shared.problem = T("无法打开使用指南，请重新安装邮件小秘书。")
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

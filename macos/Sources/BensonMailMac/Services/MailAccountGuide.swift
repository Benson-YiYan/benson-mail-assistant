import AppKit
import Foundation

/// Ships with the application; opening help never sends account information online.
enum MailAccountGuide {
    static func url(language: String = AppLanguage.shared.code) -> URL? {
        Bundle.main.url(forResource: "Mail-account-setup-" + (language == "en" ? "en" : "zh"), withExtension: "txt")
            ?? Bundle.main.url(forResource: "Mail-account-setup-zh", withExtension: "txt")
    }
    static func tokenURL() -> URL? {
        Bundle.main.url(forResource: "Get-Outlook-Token", withExtension: "command")
    }
    static func offersToken(_ authentication: String) -> Bool { authentication == "oauth2" }
    @MainActor static func openToken() throws {
        guard let file = tokenURL(), NSWorkspace.shared.open(file) else {
            throw NSError(domain: "BensonMail", code: 2, userInfo: [NSLocalizedDescriptionKey: T("无法打开取令牌工具，请重新安装邮件小秘书。")])
        }
    }
    @MainActor static func open() throws {
        guard let file = url(), NSWorkspace.shared.open(file) else {
            throw NSError(domain: "BensonMail", code: 1,
                userInfo: [NSLocalizedDescriptionKey: T("无法打开邮箱设置教程，请重新安装邮件小秘书。")])
        }
    }
}

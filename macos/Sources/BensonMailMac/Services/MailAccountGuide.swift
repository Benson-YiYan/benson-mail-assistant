import AppKit
import Foundation

/// Guide text is part of the selected downloaded language pack; reading it never sends account data.
enum MailAccountGuide {
    static func url(language: String = AppLanguage.shared.code) -> URL? {
        AppLanguage.shared.guideURL("mail_account", language: language)
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
                userInfo: [NSLocalizedDescriptionKey: T("请先下载当前语言包，再打开指南。")])
        }
    }
}

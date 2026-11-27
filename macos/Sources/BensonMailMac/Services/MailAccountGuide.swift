import AppKit
import Foundation

/// Guide text is part of the selected downloaded language pack; reading it never sends account data.
enum MailAccountGuide {
    static func credentialPage(for provider: String) -> URL? {
        let address: String
        switch provider {
        case "163": address = "https://mail.163.com/"
        case "126": address = "https://mail.126.com/"
        case "yeah": address = "https://www.yeah.net/"
        case "qq": address = "https://mail.qq.com/"
        case "exmail": address = "https://exmail.qq.com/"
        case "icloud": address = "https://account.apple.com/"
        case "yahoo": address = "https://login.yahoo.com/account/security"
        default: return nil
        }
        return URL(string: address)
    }
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

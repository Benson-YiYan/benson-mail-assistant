import Foundation
import CryptoKit
import Network

struct MailboxProfile: Codable, Equatable, Identifiable {
    var connection: MailConnection
    var enabled = true
    var id: String { connection.identity }
}

struct MailPreset: Decodable, Identifiable {
    let id: String
    let name: String
    let host: String
    var mail_auth: String?
    static var all: [MailPreset] {
        guard let url = Bundle.main.url(forResource: "mail-presets", withExtension: "json"),
              let bytes = try? Data(contentsOf: url), let values = try? JSONDecoder().decode([MailPreset].self, from: bytes) else {
            return [MailPreset(id: "163", name: "网易163", host: "imap.163.com"),
                    MailPreset(id: "custom", name: "其他邮箱（自定义 IMAP）", host: "")]
        }
        return values
    }
}

struct MailConnection: Codable, Equatable {
    var mail_provider = "163"
    var account = ""
    var username = ""
    var host = "imap.163.com"
    var port = 993
    var security = "ssl"
    var mail_folder = "INBOX"
    var mail_auth = "password"
    var secret_service = "Codex-Mail-163"
    var secret_account = ""
    var login: String { username.isEmpty ? account : username }
    var identity: String {
        let raw = [account.lowercased(), login, host.lowercased(), String(port), security, mail_folder, mail_auth].joined(separator: "\u{1f}")
        return SHA256.hash(data: Data(raw.utf8)).map { String(format: "%02x", $0) }.joined()
    }
    func validated() throws -> MailConnection {
        var value = self
        value.account = account.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        value.username = username.trimmingCharacters(in: .whitespacesAndNewlines)
        value.host = host.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        value.mail_folder = mail_folder.trimmingCharacters(in: .whitespacesAndNewlines)
        if value.mail_folder.isEmpty { value.mail_folder = "INBOX" }
        guard value.account.count <= 254,
              value.account.range(of: #"^[^\s@\x00-\x1f]+@[^\s@/\\\x00-\x1f]+\.[^\s@/\\\x00-\x1f]+$"#, options: .regularExpression) != nil else {
            throw MailCredentials.Failure("请输入完整的邮箱地址，例如 name@example.com。")
        }
        let isIP = IPv4Address(value.host) != nil || IPv6Address(value.host) != nil
        let validHost = value.host.split(separator: ".", omittingEmptySubsequences: false).allSatisfy {
            $0.range(of: #"^[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?$"#, options: .regularExpression) != nil
        }
        guard !value.host.isEmpty, value.host.count <= 253, isIP || validHost else {
            throw MailCredentials.Failure("IMAP 服务器只填写域名或 IP，不要包含 https://、端口或路径。")
        }
        guard (1...65535).contains(value.port), ["ssl", "starttls"].contains(value.security),
              ["password", "oauth2"].contains(value.mail_auth) else {
            throw MailCredentials.Failure("请检查端口、加密方式和登录方式。")
        }
        guard !(value.login + value.mail_folder).unicodeScalars.contains(where: { $0.value < 32 || $0.value == 127 }) else {
            throw MailCredentials.Failure("登录用户名和文件夹名称不能包含换行或控制字符。")
        }
        return value
    }
}

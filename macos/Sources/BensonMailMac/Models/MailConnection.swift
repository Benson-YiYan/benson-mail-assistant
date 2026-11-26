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
    var read_all_mail = false
    var mail_auth = "password"
    /// Gmail and Outlook can use either managed browser OAuth or a manual token.
    var oauth_mode = "managed"
    var oauth_client_id = ""
    var oauth_tenant = "common"
    var secret_service = "Codex-Mail-163"
    var secret_account = ""
    var proxy_mode = "direct"
    var proxy_host = "127.0.0.1"
    var proxy_port = 10808

    init() {}
    enum CodingKeys: String, CodingKey {
        case mail_provider, account, username, host, port, security, mail_folder, read_all_mail, mail_auth
        case oauth_mode, oauth_client_id, oauth_tenant
        case secret_service, secret_account, proxy_mode, proxy_host, proxy_port
    }
    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        mail_provider = try values.decodeIfPresent(String.self, forKey: .mail_provider) ?? "163"
        account = try values.decodeIfPresent(String.self, forKey: .account) ?? ""
        username = try values.decodeIfPresent(String.self, forKey: .username) ?? ""
        host = try values.decodeIfPresent(String.self, forKey: .host) ?? "imap.163.com"
        port = try values.decodeIfPresent(Int.self, forKey: .port) ?? 993
        security = try values.decodeIfPresent(String.self, forKey: .security) ?? "ssl"
        mail_folder = try values.decodeIfPresent(String.self, forKey: .mail_folder) ?? "INBOX"
        read_all_mail = try values.decodeIfPresent(Bool.self, forKey: .read_all_mail) ?? false
        mail_auth = try values.decodeIfPresent(String.self, forKey: .mail_auth) ?? "password"
        oauth_mode = try values.decodeIfPresent(String.self, forKey: .oauth_mode) ?? "manual"
        oauth_client_id = try values.decodeIfPresent(String.self, forKey: .oauth_client_id) ?? ""
        oauth_tenant = try values.decodeIfPresent(String.self, forKey: .oauth_tenant) ?? "common"
        secret_service = try values.decodeIfPresent(String.self, forKey: .secret_service) ?? "Codex-Mail-163"
        secret_account = try values.decodeIfPresent(String.self, forKey: .secret_account) ?? ""
        proxy_mode = try values.decodeIfPresent(String.self, forKey: .proxy_mode) ?? "direct"
        proxy_host = try values.decodeIfPresent(String.self, forKey: .proxy_host) ?? "127.0.0.1"
        proxy_port = try values.decodeIfPresent(Int.self, forKey: .proxy_port) ?? 10808
    }
    var login: String { username.isEmpty ? account : username }
    var offersBrowserLogin: Bool { ["gmail", "outlook"].contains(mail_provider) }
    mutating func changeAuthentication(to method: String) {
        mail_auth = method
        oauth_mode = method == "oauth2" && offersBrowserLogin ? "managed" : "manual"
    }
    var identity: String {
        // OAuth client metadata does not change the mailbox itself or its
        // IMAP progress identity. Keep this aligned with the Python worker.
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
        if value.offersBrowserLogin {
            value.mail_auth = "oauth2"
            if value.oauth_mode == "managed" {
                let provider = value.mail_provider == "gmail" ? "google" : "microsoft"
                let appClientID = MailOAuthApplicationCredentials.clientID(for: provider)
                if !appClientID.isEmpty { value.oauth_client_id = appClientID }
                value.oauth_tenant = "common"
            }
        }
        guard (1...65535).contains(value.port), ["ssl", "starttls"].contains(value.security),
              ["password", "oauth2"].contains(value.mail_auth),
              ["manual", "managed"].contains(value.oauth_mode) else {
            throw MailCredentials.Failure("请检查端口、加密方式和登录方式。")
        }
        if value.oauth_mode == "managed" {
            value.oauth_client_id = value.oauth_client_id.trimmingCharacters(in: .whitespacesAndNewlines)
            guard value.mail_auth == "oauth2", value.offersBrowserLogin, !value.oauth_client_id.isEmpty else {
                throw MailCredentials.Failure("浏览器登录功能暂未配置，请稍后再试。")
            }
            value.oauth_tenant = value.oauth_tenant.trimmingCharacters(in: .whitespacesAndNewlines)
            if value.oauth_tenant.isEmpty || value.mail_provider == "gmail" { value.oauth_tenant = "common" }
            if value.mail_provider == "outlook",
               !["common", "consumers", "organizations"].contains(value.oauth_tenant.lowercased()),
               UUID(uuidString: value.oauth_tenant) == nil,
               value.oauth_tenant.range(of: #"^[A-Za-z0-9.-]{1,255}$"#, options: .regularExpression) == nil {
                throw MailCredentials.Failure("Microsoft 租户无效。")
            }
            guard value.host == MailPreset.all.first(where: { $0.id == value.mail_provider })?.host,
                  value.port == 993, value.security == "ssl",
                  value.login.caseInsensitiveCompare(value.account) == .orderedSame else {
                throw MailCredentials.Failure("浏览器登录需使用服务商默认的 IMAP 服务器、993 端口、SSL/TLS 和完整邮箱地址。")
            }
        }
        guard !(value.login + value.mail_folder).unicodeScalars.contains(where: { $0.value < 32 || $0.value == 127 }) else {
            throw MailCredentials.Failure("登录用户名和文件夹名称不能包含换行或控制字符。")
        }
        guard ["direct", "system", "http", "socks5"].contains(value.proxy_mode) else {
            throw MailCredentials.Failure("请选择有效的邮箱代理方式。")
        }
        if ["http", "socks5"].contains(value.proxy_mode) {
            value.proxy_host = proxy_host.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            let proxyIsIP = IPv4Address(value.proxy_host) != nil || IPv6Address(value.proxy_host) != nil
            let proxyIsDomain = value.proxy_host.split(separator: ".", omittingEmptySubsequences: false).allSatisfy {
                $0.range(of: #"^[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?$"#, options: .regularExpression) != nil
            }
            guard !value.proxy_host.isEmpty, value.proxy_host.count <= 253, proxyIsIP || proxyIsDomain else {
                throw MailCredentials.Failure("代理地址只填写域名或 IP，不要包含协议、端口或路径。")
            }
            guard (1...65535).contains(value.proxy_port) else {
                throw MailCredentials.Failure("请输入有效的代理端口（1–65535）。")
            }
        }
        return value
    }
}

import Foundation
import Security

enum MailCredentials {
    static let service = "Codex-Mail-163"
    static func account() -> String? {
        let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service, kSecReturnAttributes as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne]
        var result: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess,
              let attributes = result as? [String: Any] else { return nil }
        return attributes[kSecAttrAccount as String] as? String
    }
    static func validate(address: String, code: String, existing: String?) throws {
        guard address.range(of: #"^[^\s@\x00-\x1f]+@[^\s@/\\\x00-\x1f]+\.[^\s@/\\\x00-\x1f]+$"#, options: .regularExpression) != nil else {
            throw Failure("请输入完整的邮箱地址，例如 name@example.com。")
        }
        guard !code.isEmpty || existing == address else {
            throw Failure("请填写密码、客户端授权码或 OAuth2 访问令牌。")
        }
    }
    static func save(address: String, code: String, serviceName: String = service, exactAccount: Bool = false) throws {
        var query: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: serviceName]
        if exactAccount { query[kSecAttrAccount as String] = address }
        let attributes: [String: Any] = [kSecAttrAccount as String: address, kSecValueData as String: Data(code.utf8)]
        var status = SecItemUpdate(query as CFDictionary, attributes as CFDictionary)
        if status == errSecItemNotFound {
            status = SecItemAdd(query.merging(attributes) { _, new in new } as CFDictionary, nil)
        }
        guard status == errSecSuccess else {
            throw Failure("钥匙串保存失败：\(SecCopyErrorMessageString(status, nil) as String? ?? String(status))")
        }
    }
    static func hasAPIKey(endpoint: String) -> Bool {
        let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: "BensonMail-AI-API", kSecAttrAccount as String: endpoint,
            kSecReturnAttributes as String: true]
        return SecItemCopyMatching(query as CFDictionary, nil) == errSecSuccess
    }
    static func apiEndpoint(_ raw: String) throws -> String {
        let base = raw.trimmingCharacters(in: .whitespacesAndNewlines).replacingOccurrences(of: #"/+$"#, with: "", options: .regularExpression)
        guard let parts = URLComponents(string: base), let host = parts.host,
              parts.user == nil, parts.password == nil, parts.query == nil, parts.fragment == nil,
              parts.scheme == "https" || (parts.scheme == "http" && ["localhost", "127.0.0.1", "::1", "[::1]"].contains(host)) else {
            throw Failure("请填写服务商提供的 HTTPS 基础地址；本机服务可使用 HTTP。地址中不要包含密钥。")
        }
        return parts.path.hasSuffix("/chat/completions") ? base : base + "/chat/completions"
    }
    struct Failure: LocalizedError {
        let message: String
        init(_ message: String) { self.message = message }
        var errorDescription: String? { message }
    }
}

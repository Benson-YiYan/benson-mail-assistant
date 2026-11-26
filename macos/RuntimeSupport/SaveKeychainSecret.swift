import Foundation
import Security
import Darwin

guard CommandLine.arguments.count == 3 else {
    fputs("Invalid arguments.\n", stderr)
    exit(2)
}

let service = CommandLine.arguments[1]
let account = CommandLine.arguments[2]
guard ["Codex-Mail-163", "BensonMail-IMAP"].contains(service),
      !account.isEmpty, account.utf8.count <= 512,
      !account.contains("\n"), !account.contains("\r") else {
    fputs("Invalid Keychain item.\n", stderr)
    exit(2)
}

let data = FileHandle.standardInput.readDataToEndOfFile()
guard !data.isEmpty, data.count <= 1_000_000,
      let bundle = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
      bundle["schema"] as? Int == 1,
      let provider = bundle["provider"] as? String,
      ["google", "microsoft"].contains(provider),
      let email = bundle["email"] as? String, !email.isEmpty,
      let accessToken = bundle["access_token"] as? String, !accessToken.isEmpty,
      let refreshToken = bundle["refresh_token"] as? String, !refreshToken.isEmpty else {
    fputs("Invalid OAuth credential bundle.\n", stderr)
    exit(2)
}

let item: [String: Any] = [
    kSecClass as String: kSecClassGenericPassword,
    kSecAttrService as String: service,
    kSecAttrAccount as String: account
]
let attributes: [String: Any] = [kSecValueData as String: data]
var status = SecItemUpdate(item as CFDictionary, attributes as CFDictionary)
if status == errSecItemNotFound {
    status = SecItemAdd(item.merging(attributes) { _, new in new } as CFDictionary, nil)
}
guard status == errSecSuccess else {
    fputs("Keychain update failed (\(status)).\n", stderr)
    exit(1)
}

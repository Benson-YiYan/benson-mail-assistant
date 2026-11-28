import Foundation
import Security
import Darwin

let args = Array(CommandLine.arguments.dropFirst())
let reading = args.first == "--read"
let background = args.first == "--read-background" || args.first == "--write-background"
let credentials = (reading || background) ? Array(args.dropFirst()) : args
guard credentials.count == 2 else { exit(2) }
let service = credentials[0]
let account = credentials[1]
guard ["Codex-Mail-163", "BensonMail-IMAP"].contains(service),
      account.utf8.count <= 512, !account.contains("\n"), !account.contains("\r"),
      !account.isEmpty || service == "Codex-Mail-163" else { exit(2) }

if background {
    guard SecKeychainSetUserInteractionAllowed(false) == errSecSuccess else { exit(1) }
}
var item: [String: Any] = [
    kSecClass as String: kSecClassGenericPassword,
    kSecAttrService as String: service
]
if !account.isEmpty { item[kSecAttrAccount as String] = account }
if reading || args.first == "--read-background" {
    item[kSecReturnData as String] = true
    item[kSecMatchLimit as String] = kSecMatchLimitOne
    var result: CFTypeRef?
    let status = SecItemCopyMatching(item as CFDictionary, &result)
    guard status == errSecSuccess, let data = result as? Data else {
        fputs("Keychain read failed (\(status)).\n", stderr)
        exit(1)
    }
    FileHandle.standardOutput.write(data)
    exit(0)
}
guard !account.isEmpty else { exit(2) }

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

let attributes: [String: Any] = [kSecValueData as String: data]
var status = SecItemUpdate(item as CFDictionary, attributes as CFDictionary)
if status == errSecItemNotFound {
    status = SecItemAdd(item.merging(attributes) { _, new in new } as CFDictionary, nil)
}
guard status == errSecSuccess else {
    fputs("Keychain update failed (\(status)).\n", stderr)
    exit(1)
}

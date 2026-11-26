import Foundation

enum MailOAuthApplicationCredentials {
    static func clientID(for provider: String) -> String {
        let key = provider == "google" ? "BensonMailGoogleOAuthClientID" : "BensonMailMicrosoftOAuthClientID"
        return (Bundle.main.object(forInfoDictionaryKey: key) as? String)?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    }

    static func clientSecret(for provider: String) -> String {
        guard provider == "google" else { return "" }
        return (Bundle.main.object(forInfoDictionaryKey: "BensonMailGoogleOAuthClientSecret") as? String)?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    }
}

enum MailOAuthLogin {
    static func credentialBundle(worker: URL = ServiceInstaller.worker, home: URL,
                                 connection: MailConnection) async throws -> String {
        var connection = connection
        let providerName = connection.mail_provider == "gmail" ? "google" : "microsoft"
        connection.mail_auth = "oauth2"
        connection.oauth_mode = "managed"
        let appClientID = MailOAuthApplicationCredentials.clientID(for: providerName)
        if !appClientID.isEmpty { connection.oauth_client_id = appClientID }
        connection.oauth_tenant = "common"
        guard !connection.oauth_client_id.isEmpty else {
            throw MailCredentials.Failure("浏览器登录功能暂未配置，请稍后再试。")
        }
        connection = try connection.validated()
        guard connection.oauth_mode == "managed" else {
            throw MailCredentials.Failure("请使用 Google 或 Microsoft 浏览器登录。")
        }
        guard worker.isFileURL else {
            throw MailCredentials.Failure("找不到 OAuth 登录工具，请重新安装完整应用。")
        }
        let workerPath = worker.path
        let homePath = home.path
        let privateInput = try JSONSerialization.data(withJSONObject: [
            "client_secret": MailOAuthApplicationCredentials.clientSecret(for: providerName),
            "mailbox_proxy": ["proxy_mode": connection.proxy_mode, "proxy_host": connection.proxy_host,
                              "proxy_port": connection.proxy_port]
        ])
        return try await Task.detached(priority: .userInitiated) {
            let process = Process()
            process.executableURL = URL(fileURLWithPath: workerPath)
            process.arguments = ["--home", homePath, "--oauth-login", providerName, connection.account,
                                 connection.oauth_client_id, "--tenant", connection.oauth_tenant, "--private-input"]
            let input = Pipe(), output = Pipe()
            process.standardInput = input
            process.standardOutput = output
            process.standardError = FileHandle.nullDevice
            do {
                try process.run()
                try input.fileHandleForWriting.write(contentsOf: privateInput)
                try input.fileHandleForWriting.close()
                let bytes = output.fileHandleForReading.readDataToEndOfFile()
                process.waitUntilExit()
                guard let object = (try? JSONSerialization.jsonObject(with: bytes)) as? [String: Any] else {
                    throw MailCredentials.Failure("OAuth 登录工具返回了无法识别的结果。")
                }
                if let message = object["error"] as? String {
                    throw MailCredentials.Failure(message)
                }
                guard process.terminationStatus == 0, matches(object, connection: connection) else {
                    throw MailCredentials.Failure("OAuth 登录未完成或登录的邮箱与填写地址不一致。")
                }
                let compact = try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])
                guard let result = String(data: compact, encoding: .utf8) else {
                    throw MailCredentials.Failure("无法准备安全保存的 OAuth 凭据。")
                }
                return result
            } catch let error as MailCredentials.Failure {
                throw error
            } catch {
                try? input.fileHandleForWriting.close()
                if process.isRunning { process.terminate() }
                throw MailCredentials.Failure("无法启动 OAuth 登录工具：\(error.localizedDescription)")
            }
        }.value
    }

    private static func matches(_ object: [String: Any], connection: MailConnection) -> Bool {
        let provider = connection.mail_provider == "gmail" ? "google" : "microsoft"
        return object["schema"] as? Int == 1 && object["provider"] as? String == provider &&
            (object["email"] as? String)?.caseInsensitiveCompare(connection.account) == .orderedSame &&
            object["client_id"] as? String == connection.oauth_client_id &&
            (provider == "google" || object["tenant"] as? String == connection.oauth_tenant) &&
            (object["access_token"] as? String)?.isEmpty == false &&
            (object["refresh_token"] as? String)?.isEmpty == false && object["expires_at"] is NSNumber
    }

    static func validateCredential(_ secret: String, connection: MailConnection, previous: MailConnection?) throws {
        if connection.oauth_mode == "managed" {
            if secret.isEmpty, let previous, previous.oauth_mode == "managed",
               previous.identity == connection.identity, previous.mail_provider == connection.mail_provider,
               previous.oauth_client_id == connection.oauth_client_id, previous.oauth_tenant == connection.oauth_tenant {
                return
            }
            if let object = (try? JSONSerialization.jsonObject(with: Data(secret.utf8))) as? [String: Any],
               matches(object, connection: connection) { return }
            throw MailCredentials.Failure("请先完成 Google 或 Microsoft 登录，或改用手动 OAuth2 令牌。")
        }
        if previous?.oauth_mode == "managed", secret.isEmpty {
            throw MailCredentials.Failure("请填写密码、客户端授权码或 OAuth2 访问令牌。")
        }
    }
}

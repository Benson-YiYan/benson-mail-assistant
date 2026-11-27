import SwiftUI
import AppKit

private typealias AccountState<Value> = SwiftUI.State<Value>

// UI-only normalization. The persisted connection, identity and mail progress are unchanged.
enum MailAccountDraft {
    static func browserLoginConfigured(provider: String, appClientID: String, savedClientID: String) -> Bool {
        ["gmail", "outlook"].contains(provider) &&
            (!appClientID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ||
             !savedClientID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
    }

    static func normalizeLogin(_ connection: inout MailConnection, appClientID suppliedClientID: String? = nil) {
        guard connection.offersBrowserLogin else {
            connection.mail_auth = "password"
            connection.oauth_mode = "manual"
            connection.oauth_client_id = ""
            connection.oauth_tenant = "common"
            return
        }
        connection.mail_auth = "oauth2"
        connection.oauth_mode = "managed"
        let provider = connection.mail_provider == "gmail" ? "google" : "microsoft"
        let appClientID = suppliedClientID ?? MailOAuthApplicationCredentials.clientID(for: provider)
        if !appClientID.isEmpty { connection.oauth_client_id = appClientID }
        connection.oauth_tenant = "common"
    }

    private static func followsAddress(_ value: MailConnection) -> Bool {
        value.username.trimmingCharacters(in: .whitespacesAndNewlines)
            .caseInsensitiveCompare(value.account.trimmingCharacters(in: .whitespacesAndNewlines)) == .orderedSame
    }
    static func load(_ saved: MailConnection, account: String? = nil) -> MailConnection {
        var value = saved
        if followsAddress(value) { value.username = "" }
        if let account { value.account = account }
        if value.offersBrowserLogin {
            value.mail_auth = "oauth2"
            if !["manual", "managed"].contains(value.oauth_mode) { value.oauth_mode = "managed" }
        } else {
            normalizeLogin(&value)
        }
        return value
    }
    static func changingAccount(_ saved: MailConnection, to account: String) -> MailConnection {
        var value = saved
        if followsAddress(value) { value.username = "" }
        value.account = account
        return value
    }
    static func inferringProvider(_ saved: MailConnection, to address: String, explicit: Bool) -> MailConnection {
        var value = changingAccount(saved, to: address)
        guard !explicit else {
            normalizeLogin(&value)
            return value
        }
        let domain = address.trimmingCharacters(in: .whitespacesAndNewlines)
            .split(separator: "@", omittingEmptySubsequences: false).last.map(String.init)?.lowercased() ?? ""
        let detected: String?
        switch domain {
        case "gmail.com", "googlemail.com": detected = "gmail"
        case "outlook.com", "hotmail.com", "live.com", "msn.com": detected = "outlook"
        default: detected = nil
        }
        if let detected, detected == value.mail_provider { return value }
        if explicit {
            if value.offersBrowserLogin {
                value.mail_auth = "oauth2"
                if !["manual", "managed"].contains(value.oauth_mode) { value.oauth_mode = "managed" }
            } else {
                normalizeLogin(&value)
            }
            return value
        }
        if let detected, let preset = MailPreset.all.first(where: { $0.id == detected }) {
            if value.mail_provider != detected { value.oauth_client_id = "" }
            value.mail_provider = detected
            value.host = preset.host
            value.port = 993
            value.security = "ssl"
            normalizeLogin(&value)
        } else if ["gmail", "outlook"].contains(value.mail_provider) {
            value.mail_provider = "custom"
            value.host = ""
            normalizeLogin(&value)
        }
        return value
    }
}

struct BrowserMailboxLoginFields: View {
    let provider: String
    let canSignIn: Bool
    let configured: Bool
    let authorized: Bool
    let signIn: () async throws -> Void
    @AccountState private var busy = false
    @AccountState private var message = ""
    @AccountState private var signInSucceeded = false
    var body: some View {
        HStack {
            if authorized {
                Label(T("已授权"), systemImage: "checkmark.circle")
            } else {
            Button(busy ? T("正在等待网页登录…") : (provider == "gmail" ? T("登录 Google") : T("登录 Microsoft"))) {
                busy = true; message = ""
                Task {
                    defer { busy = false }
                    do {
                        try await signIn()
                        signInSucceeded = true
                    } catch { message = error.localizedDescription }
                }
            }.buttonStyle(.borderedProminent)
                .tint(.blue)
                .disabled(!canSignIn || !configured || busy)
                .accessibilityIdentifier("mail-oauth-login")
            }
            if busy { ProgressView().controlSize(.small) }
        }
        .alert(provider == "gmail" ? T("登录 Google") : T("登录 Microsoft"), isPresented: $signInSucceeded) {
            Button(T("好"), role: .cancel) {}
        } message: {
            Text(T("登录已完成；凭据将在点击保存后安全写入钥匙串。"))
        }
        if !configured {
            Text(T("浏览器登录功能暂未配置，请稍后再试。"))
                .font(.caption).foregroundStyle(.secondary)
                .accessibilityIdentifier("mail-oauth-not-configured")
        }
        Text(provider == "gmail" ? T("Gmail OAuth 会请求完整邮箱访问权限；本软件只用只读 IMAP 操作。")
             : T("Microsoft IMAP 授权可能允许读写邮件；本软件只执行只读操作。"))
            .font(.caption).foregroundStyle(.secondary)
        if !message.isEmpty { Text(T(message)).font(.caption).textSelection(.enabled) }
    }
}

struct MailAccountView: View {
    @ObservedObject private var language = AppLanguage.shared
    @ObservedObject var store: MailStore
    var onboarding = false
    var workspace = false
    @AccountState private var draft = MailConnection()
    @AccountState private var port = "993"
    @AccountState private var proxyPort = "10808"
    @AccountState private var code = ""
    @AccountState private var saved = false
    @AccountState private var error: String?
    @AccountState private var adding = false
    @AccountState private var removing = false
    @AccountState private var providerExplicitlySelected = false
    @AccountState private var draftID = UUID()
    private var fields: some View {
        VStack(alignment: .leading, spacing: 12) {
            if onboarding {
                Text(T("欢迎使用邮件小秘书")).font(.title2.bold())
                Text(T("连接邮箱，收到新邮件后自动整理六项报告。"))
            }
            if !store.mailboxProfiles.isEmpty {
                Picker(T("已添加的邮箱"), selection: Binding(get: { adding ? "" : (store.settings.mailbox?.identity ?? store.mailboxProfiles.first?.id ?? "") },
                    set: { id in
                        store.selectMailbox(id); adding = false
                        loadDraft()
                    })) {
                    if adding { Text(T("正在添加新邮箱")).tag("") }
                    ForEach(store.mailboxProfiles) { profile in
                        Text(profile.connection.account + (profile.enabled ? T(" · 已启用") : T(" · 已暂停"))).tag(profile.id)
                    }
                }
                HStack {
                    Button(T("添加邮箱")) { adding = true; draft = MailConnection(); port = "993"; proxyPort = "10808"; code = ""; saved = false; providerExplicitlySelected = false; draftID = UUID() }
                    if !adding, let profile = store.mailboxProfiles.first(where: { $0.id == draft.identity }) {
                        Button(profile.enabled ? T("暂停此邮箱") : T("启用此邮箱")) {
                            store.setMailboxEnabled(profile.id, enabled: !profile.enabled)
                        }
                        Button(T("移除此邮箱"), role: .destructive) { removing = true }
                    }
                }
                Text(T("可监听多个账号；各账号独立记录收信进度，共用 AI、报告目录和检查间隔。"))
                    .font(.caption).foregroundStyle(.secondary)
            }
            Picker(T("邮箱服务商"), selection: Binding(get: { draft.mail_provider }, set: { selected in
                guard selected != draft.mail_provider else { return }
                code = ""
                draft.mail_provider = selected
                if let preset = MailPreset.all.first(where: { $0.id == selected }), preset.id != "custom" {
                    draft.host = preset.host; draft.port = 993; port = "993"
                    draft.security = "ssl"
                    draft.oauth_client_id = ""
                } else if selected == "custom" {
                    draft.host = ""
                    draft.oauth_client_id = ""
                }
                MailAccountDraft.normalizeLogin(&draft)
                providerExplicitlySelected = true
                saved = false
            })) {
                ForEach(MailPreset.all) { preset in Text(T(preset.name)).tag(preset.id) }
            }
            TextField(T("邮箱地址，例如 name@example.com"), text: Binding(get: { draft.account }, set: {
                if $0.trimmingCharacters(in: .whitespacesAndNewlines).caseInsensitiveCompare(draft.account) != .orderedSame {
                    code = ""
                }
                let provider = draft.mail_provider
                draft = MailAccountDraft.inferringProvider(draft, to: $0, explicit: providerExplicitlySelected)
                if draft.mail_provider != provider { port = String(draft.port) }
            }))
                .textContentType(.username).accessibilityLabel(T("邮箱地址"))
            TextField(T("IMAP 收件服务器，例如 imap.example.com"), text: $draft.host)
                .accessibilityLabel(T("IMAP 收件服务器"))
            HStack {
                TextField(T("端口"), text: $port).frame(width: 90).accessibilityLabel(T("IMAP 端口"))
                Picker(T("加密"), selection: Binding(get: { draft.security }, set: { value in
                    draft.security = value; port = value == "ssl" ? "993" : "143"
                })) {
                    Text("SSL/TLS").tag("ssl")
                    Text("STARTTLS").tag("starttls")
                }
            }
            if draft.offersBrowserLogin {
                Picker(T("登录方式"), selection: Binding(get: { draft.oauth_mode }, set: { mode in
                    guard mode != draft.oauth_mode else { return }
                    code = ""
                    draft.oauth_mode = mode
                })) {
                    Text(T("浏览器登录")).tag("managed")
                    Text(T("手动访问令牌")).tag("manual")
                }
                if draft.oauth_mode == "managed" {
                    BrowserMailboxLoginFields(provider: draft.mail_provider,
                        canSignIn: !draft.account.isEmpty && !store.isTest,
                        configured: MailAccountDraft.browserLoginConfigured(
                            provider: draft.mail_provider,
                            appClientID: MailOAuthApplicationCredentials.clientID(for: draft.mail_provider == "gmail" ? "google" : "microsoft"),
                            savedClientID: draft.oauth_client_id),
                        authorized: MailOAuthLogin.isAuthorized(code, connection: draft,
                            previous: adding ? nil : store.settings.mailbox),
                        signIn: startOAuthLogin)
                        .id(draft.mail_provider + draftID.uuidString)
                } else {
                    SecureField(T("OAuth2 访问令牌"), text: $code)
                        .accessibilityLabel(T("OAuth2 访问令牌"))
                }
            } else {
                SecureField(T("密码／客户端授权码"), text: $code)
                    .accessibilityLabel(T("邮箱密码或授权码"))
                Button(T("如何获取授权码？")) {
                    do { try MailAccountGuide.open() }
                    catch { self.error = error.localizedDescription }
                }.accessibilityIdentifier("mail-account-guide")
            }
            Picker(T("邮箱代理"), selection: $draft.proxy_mode) {
                Text(T("直连（不使用代理）")).tag("direct")
                Text(T("使用系统代理")).tag("system")
                Text("HTTP CONNECT").tag("http")
                Text("SOCKS5").tag("socks5")
            }.accessibilityIdentifier("mail-proxy-mode")
            if ["http", "socks5"].contains(draft.proxy_mode) {
                HStack {
                    TextField(T("代理地址，例如 127.0.0.1"), text: $draft.proxy_host)
                        .accessibilityIdentifier("mail-proxy-host")
                    TextField(T("代理端口"), text: $proxyPort).frame(width: 100)
                        .accessibilityIdentifier("mail-proxy-port")
                }
                Text(T("v2rayN 的代理地址、端口和协议必须与客户端实际设置一致。10808 仅为示例；本版不支持需要用户名或密码的代理。"))
                    .font(.caption).foregroundStyle(.secondary)
            }
            if draft.proxy_mode == "system" {
                Text(T("读取 macOS 系统代理设置。先在 v2rayN 开启系统代理；无需为收邮件开启 TUN。未找到可用代理时会提示错误，不会改用直连。"))
                    .font(.caption).foregroundStyle(.secondary)
            }
            if draft.proxy_mode != "direct" {
                Text(T("此代理仅用于当前邮箱的连接测试和收信；请先保存邮箱设置，再测试连接。代理不可用时不会改用直连。"))
                    .font(.caption).foregroundStyle(.secondary)
            }
            DisclosureGroup {
                VStack(alignment: .leading, spacing: 10) {
                    TextField(T("登录用户名；留空使用邮箱地址"), text: $draft.username)
                        .accessibilityLabel(T("登录用户名"))
                    if draft.username.isEmpty {
                        Text(T("登录用户名默认跟随邮箱地址；仅在服务商要求时填写不同用户名。"))
                            .font(.caption).foregroundStyle(.secondary)
                    } else {
                        Text(T("当前使用自定义登录用户名：") + draft.username)
                            .font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
                    }
                    TextField(T("邮件文件夹"), text: $draft.mail_folder)
                    Toggle(T("读取所有邮件文件夹"), isOn: $draft.read_all_mail)
                    Text(T("开启后会监视 IMAP 中所有可读取的文件夹，并分别保存进度；关闭时只读取上方设置的文件夹。"))
                        .font(.caption).foregroundStyle(.secondary)
                }.padding(.top, 8)
            } label: {
                Text(T("高级连接选项")).background {
                    if store.isTest { NativeTestAnchor(identifier: "mail-advanced-disclosure") }
                }
            }
            if !draft.offersBrowserLogin {
                Text(T("请启用 IMAP，并按服务商要求填写客户端授权码或应用专用密码。"))
                    .font(.caption).foregroundStyle(.secondary)
            }
            Text(T("凭据保存在系统钥匙串。更换账号、服务器、登录用户名或文件夹前，请先暂停监听；旧报告保留。"))
                .font(.caption).foregroundStyle(.secondary)
        }

    }
    private var actions: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Button(store.savingAccount ? T("正在保存…") : (onboarding ? T("保存并开始使用") : T("保存邮箱设置"))) {
                    saved = false; error = nil
                    guard let number = Int(port) else { error = "请输入有效的 IMAP 端口。"; return }
                    draft.port = number
                    if ["http", "socks5"].contains(draft.proxy_mode) {
                        guard let proxyNumber = Int(proxyPort) else { error = "请输入有效的代理端口（1–65535）。"; return }
                        draft.proxy_port = proxyNumber
                    }
                    store.saveAccount(address: draft.account, code: code, connection: draft, adding: adding) { result in
                        switch result {
                        case .success: code = ""; saved = true; adding = false
                        case .failure(let failure): error = failure.localizedDescription
                        }
                    }
                }.buttonStyle(.borderedProminent).disabled(store.savingAccount)
                Button(store.testingMailbox ? T("正在测试…") : T("测试邮箱连接")) { store.testMailbox() }
                    .disabled(store.savingAccount || store.testingMailbox || store.mailAccount.isEmpty)
                if saved { Text(T("已保存")).foregroundStyle(.green) }
            }
            if !store.mailboxTestResult.isEmpty { ScrollView { Text(T(store.mailboxTestResult)).font(.callout).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading) }.frame(maxHeight: 100) }
            if let error { Text(T(error)).font(.callout).foregroundStyle(.red).textSelection(.enabled) }
        }
    }
    var body: some View {
        Group {
            if workspace {
                StagedSettingsPage(store: store, draft: store.settingsDraft, page: .mailbox)
            } else { VStack(alignment: .leading, spacing: 12) { fields; actions } }
        }.textFieldStyle(.roundedBorder)
        .onAppear { loadDraft() }
        .onChange(of: store.needsAccountSetup) { old, new in
            if workspace && old && !new {
                loadDraft(); adding = false
            }
        }
        .onChange(of: draft) { _, _ in saved = false }
        .onChange(of: code) { _, value in if !value.isEmpty { saved = false } }
        .onChange(of: proxyPort) { _, _ in saved = false }
        .confirmationDialog(T("移除此邮箱？历史报告会保留。"), isPresented: $removing) {
            Button(T("移除"), role: .destructive) {
                store.removeMailbox(draft.identity)
                loadDraft()
            }
            Button(T("取消"), role: .cancel) {}
        }
    }
    private func loadDraft() {
        draftID = UUID()
        draft = MailAccountDraft.load(store.settings.mailbox ?? MailConnection(), account: store.mailAccount)
        port = String(draft.port); proxyPort = String(draft.proxy_port); code = ""; saved = false
        providerExplicitlySelected = !store.mailAccount.isEmpty
    }
    private func startOAuthLogin() async throws {
        error = nil
        let started = draft, startedID = draftID, chosenPort = port, chosenProxyPort = proxyPort
        guard let imapPort = Int(chosenPort) else { throw MailCredentials.Failure("请输入有效的 IMAP 端口。") }
        var connection = started; connection.port = imapPort
        if ["http", "socks5"].contains(connection.proxy_mode) {
            guard let value = Int(chosenProxyPort) else { throw MailCredentials.Failure("请输入有效的代理端口（1–65535）。") }
            connection.proxy_port = value
        }
        let bundle = try await MailOAuthLogin.credentialBundle(home: store.base, connection: connection)
        guard draftID == startedID, draft == started, port == chosenPort, proxyPort == chosenProxyPort else {
            throw MailCredentials.Failure("邮箱登录设置已改变，请重新登录。")
        }
        code = bundle
        saved = false
    }
}

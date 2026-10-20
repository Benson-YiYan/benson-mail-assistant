import SwiftUI
import AppKit

private typealias AccountState<Value> = SwiftUI.State<Value>

// UI-only normalization. The persisted connection, identity and mail progress are unchanged.
enum MailAccountDraft {
    private static func followsAddress(_ value: MailConnection) -> Bool {
        value.username.trimmingCharacters(in: .whitespacesAndNewlines)
            .caseInsensitiveCompare(value.account.trimmingCharacters(in: .whitespacesAndNewlines)) == .orderedSame
    }
    static func load(_ saved: MailConnection, account: String? = nil) -> MailConnection {
        var value = saved
        if followsAddress(value) { value.username = "" }
        if let account { value.account = account }
        return value
    }
    static func changingAccount(_ saved: MailConnection, to account: String) -> MailConnection {
        var value = saved
        if followsAddress(value) { value.username = "" }
        value.account = account
        return value
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
                    Button(T("添加邮箱")) { adding = true; draft = MailConnection(); port = "993"; proxyPort = "10808"; code = ""; saved = false }
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
                draft.mail_provider = selected
                if let preset = MailPreset.all.first(where: { $0.id == selected }), preset.id != "custom" {
                    draft.host = preset.host; draft.port = 993; port = "993"
                    draft.security = "ssl"; draft.mail_auth = preset.mail_auth ?? "password"
                }
                saved = false
            })) {
                ForEach(MailPreset.all) { preset in Text(T(preset.name)).tag(preset.id) }
            }
            TextField(T("邮箱地址，例如 name@example.com"), text: Binding(get: { draft.account }, set: {
                draft = MailAccountDraft.changingAccount(draft, to: $0)
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
            SecureField(T("密码／授权码／OAuth2 访问令牌；未改连接时可留空"), text: $code)
                .accessibilityLabel(T("邮箱密码或授权码"))
            HStack {
                Button(T("如何获取授权码？")) {
                    do { try MailAccountGuide.open() }
                    catch { self.error = error.localizedDescription }
                }.accessibilityIdentifier("mail-account-guide")
                if MailAccountGuide.offersToken(draft.mail_auth) {
                    Button(T("获取微软 OAuth2 Token")) {
                        do { try MailAccountGuide.openToken() }
                        catch { self.error = error.localizedDescription }
                    }.accessibilityIdentifier("mail-oauth-token")
                }
            }
            if MailAccountGuide.offersToken(draft.mail_auth) {
                Text(T("取令牌工具仅适用于 Outlook / Microsoft 365。"))
                    .font(.caption).foregroundStyle(.secondary)
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
                    Picker(T("登录方式"), selection: $draft.mail_auth) {
                        Text(T("密码／客户端授权码")).tag("password")
                        Text(T("OAuth2 访问令牌")).tag("oauth2")
                    }
                }.padding(.top, 8)
            } label: {
                Text(T("高级连接选项")).background {
                    if store.isTest { NativeTestAnchor(identifier: "mail-advanced-disclosure") }
                }
            }
            Text(T("请启用 IMAP，并按服务商要求填写客户端授权码或应用专用密码。所有预设都可修改服务器和端口。"))
                .font(.caption).foregroundStyle(.secondary)
            if draft.mail_auth == "oauth2" {
                Text(T("请填写已获得的 OAuth2 访问令牌；过期后需手动更新。本版不自动进行 OAuth 登录或续期。"))
                    .font(.caption).foregroundStyle(.orange)
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
                VStack(spacing: 0) {
                    ScrollView {
                        VStack(alignment: .leading, spacing: 18) {
                            WorkspaceCard("管理邮箱") { fields }
                            WorkspaceCard("屏蔽邮件") { SenderPolicyView(store: store) }
                            WorkspaceCard("检查与报告") {
                                IntervalControl(store: store)
                                Text(T("10 秒至 24 小时；保存后自动生效。60 秒 = 1 分钟，300 秒 = 5 分钟。"))
                                    .font(.caption).foregroundStyle(.secondary)
                                Button(T("打开运行记录"), systemImage: "doc.text.magnifyingglass") { NSWorkspace.shared.open(store.base.appendingPathComponent("daemon.log")) }
                            }
                        }.padding(20)
                    }
                    Divider()
                    actions.padding(18).frame(maxWidth: .infinity, alignment: .leading).background(Color(nsColor: .windowBackgroundColor))
                }
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
        draft = MailAccountDraft.load(store.settings.mailbox ?? MailConnection(), account: store.mailAccount)
        port = String(draft.port); proxyPort = String(draft.proxy_port); code = ""; saved = false
    }
}

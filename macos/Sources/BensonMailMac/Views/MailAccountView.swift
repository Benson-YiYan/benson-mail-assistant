import SwiftUI
import AppKit

private typealias AccountState<Value> = SwiftUI.State<Value>

struct MailAccountView: View {
    @ObservedObject private var language = AppLanguage.shared
    @ObservedObject var store: MailStore
    var onboarding = false
    var workspace = false
    @AccountState private var draft = MailConnection()
    @AccountState private var port = "993"
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
                        draft = store.settings.mailbox ?? MailConnection(); port = String(draft.port); code = ""; saved = false
                    })) {
                    if adding { Text(T("正在添加新邮箱")).tag("") }
                    ForEach(store.mailboxProfiles) { profile in
                        Text(profile.connection.account + (profile.enabled ? T(" · 已启用") : T(" · 已暂停"))).tag(profile.id)
                    }
                }
                HStack {
                    Button(T("添加邮箱")) { adding = true; draft = MailConnection(); port = "993"; code = ""; saved = false }
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
            TextField(T("邮箱地址，例如 name@example.com"), text: $draft.account)
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
            DisclosureGroup(T("高级连接选项")) {
                VStack(alignment: .leading, spacing: 10) {
                    TextField(T("登录用户名；留空使用邮箱地址"), text: $draft.username)
                    TextField(T("邮件文件夹"), text: $draft.mail_folder)
                    Picker(T("登录方式"), selection: $draft.mail_auth) {
                        Text(T("密码／客户端授权码")).tag("password")
                        Text(T("OAuth2 访问令牌")).tag("oauth2")
                    }
                }.padding(.top, 8)
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
        .onAppear {
            draft = store.settings.mailbox ?? MailConnection()
            draft.account = store.mailAccount
            port = String(draft.port)
        }
        .onChange(of: store.needsAccountSetup) { old, new in
            if workspace && old && !new {
                draft = store.settings.mailbox ?? MailConnection()
                draft.account = store.mailAccount
                port = String(draft.port); code = ""; saved = false; adding = false
            }
        }
        .onChange(of: draft) { _, _ in saved = false }
        .onChange(of: code) { _, value in if !value.isEmpty { saved = false } }
        .confirmationDialog(T("移除此邮箱？历史报告会保留。"), isPresented: $removing) {
            Button(T("移除"), role: .destructive) {
                store.removeMailbox(draft.identity)
                draft = store.settings.mailbox ?? MailConnection(); draft.account = store.mailAccount
                port = String(draft.port); code = ""
            }
            Button(T("取消"), role: .cancel) {}
        }
    }
}

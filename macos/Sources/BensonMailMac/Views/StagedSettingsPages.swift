import SwiftUI
import AppKit

private typealias StagedState<Value> = SwiftUI.State<Value>

struct StagedSettingsPage: View {
    @StagedState private var showUsage = false
    @ObservedObject var store: MailStore
    @ObservedObject var draft: SettingsDraft
    @ObservedObject private var language = AppLanguage.shared
    let page: WorkspacePage
    var body: some View {
        VStack(spacing: 0) {
            ScrollView {
                VStack(spacing: 18) {
                    switch page {
                    case .mailbox: mailbox
                    case .ai: ai
                    case .general: general
                    case .reports: EmptyView()
                    }
                }.padding(20)
            }
            Divider()
            HStack {
                Button(T(draft.saving ? "正在保存…" : "保存")) { Task { await draft.save(page) } }
                    .buttonStyle(.borderedProminent).disabled(draft.saving || !draft.dirty(page))
                    .accessibilityIdentifier("settings-page-save-" + page.id)
                if draft.dirty(page) { Text(T("有未保存的设置")).font(.callout).foregroundStyle(.orange).accessibilityIdentifier("settings-page-dirty") }
                Spacer()
                if !draft.message.isEmpty { Text(T(draft.message)).font(.callout).textSelection(.enabled) }
            }.padding(18)
        }.textFieldStyle(.roundedBorder).disabled(draft.saving)
        .sheet(isPresented: $showUsage) { UsageSettingsView(store: store) }
    }
    private var mailbox: some View {
        Group {
            WorkspaceCard("管理邮箱") {
                Picker(T("已添加的邮箱"), selection: $draft.selected) {
                    ForEach(draft.accounts) { account in Text(account.connection.account.isEmpty ? T("正在添加新邮箱") : account.connection.account).tag(account.id) }
                }
                HStack {
                    Button(T("添加邮箱")) { draft.addAccount() }
                    if let index = draft.accounts.firstIndex(where: { $0.id == draft.selected }) {
                        Button(T("移除此邮箱"), role: .destructive) { draft.accounts.remove(at: index); draft.selected = draft.accounts.first?.id ?? "" }
                    }
                }
                if let index = draft.accounts.firstIndex(where: { $0.id == draft.selected }) {
                    StagedAccountFields(account: $draft.accounts[index])
                }
                Text(T("凭据保存在系统钥匙串。更换账号、服务器、登录用户名或文件夹前，请先暂停监听；旧报告保留。"))
                    .font(.caption).foregroundStyle(.secondary)
                Button(store.testingMailbox ? T("正在测试…") : T("测试邮箱连接")) { store.testMailbox() }
                    .disabled(draft.dirty(.mailbox) || store.testingMailbox || store.mailAccount.isEmpty)
                    .accessibilityIdentifier("settings-test-mailbox")
                if !store.mailboxTestResult.isEmpty { Text(T(store.mailboxTestResult)).textSelection(.enabled).font(.caption) }
                if draft.dirty(.mailbox) { Text(T("请先保存设置，再测试连接。")).font(.caption).foregroundStyle(.secondary) }
            }
            WorkspaceCard("屏蔽邮件") { SenderPolicyView(store: store, staged: draft).id(draft.generation) }
            WorkspaceCard("检查与报告") {
                HStack {
                    Text(T("自定义检查间隔")); TextField(T("秒数"), text: $draft.interval).frame(width: 90); Text(T("秒"))
                }
                Text(T("10 秒至 24 小时；保存后自动生效。60 秒 = 1 分钟，300 秒 = 5 分钟。"))
                    .font(.caption).foregroundStyle(.secondary)
                Button(T("打开运行记录")) { NSWorkspace.shared.open(store.base.appendingPathComponent("daemon.log")) }
            }
        }
    }
    private var ai: some View {
        VStack(spacing: 18) {
        WorkspaceCard("选择您喜欢的 AI") {
            Picker(T("分析方式"), selection: $draft.value.ai_provider) {
                Text(T("API（无需安装 Codex）")).tag("api")
                Text(T("Codex（使用已登录的应用）")).tag("codex")
                Text(T("DeepSeek Harness（使用已安装的应用）")).tag("deepseek_harness")
            }
            if draft.value.ai_provider == "api" {
                TextField(T("基础地址，例如 https://服务商地址/v1"), text: $draft.value.api_base).accessibilityLabel(T("AI 基础地址"))
                TextField(T("模型名（按服务商提供的名称填写）"), text: $draft.value.api_model).accessibilityLabel(T("AI 模型名"))
                SecureField(T("API Key；留空保留此地址已保存的 Key"), text: $draft.apiKey)
                Text(T("支持 OpenAI 兼容的 Chat Completions 接口，自动补全 /chat/completions。API Key 保存在系统钥匙串。"))
                    .font(.caption).foregroundStyle(.secondary)
            }
            if draft.value.ai_provider == "deepseek_harness" {
                HStack {
                    TextField(T("dsh 路径；留空自动查找"), text: $draft.value.harness_path)
                    Button(T("浏览……")) { let panel = NSOpenPanel(); panel.canChooseDirectories = false; if panel.runModal() == .OK, let url = panel.url { draft.value.harness_path = url.path } }
                    Button(T("检测安装")) {
                        let candidates = [draft.value.harness_path, "/Applications/DeepSeek Harness.app/Contents/Resources/runtime/cli/bin/dsh", NSHomeDirectory() + "/Applications/DeepSeek Harness.app/Contents/Resources/runtime/cli/bin/dsh", "/opt/homebrew/bin/dsh", "/usr/local/bin/dsh", NSHomeDirectory() + "/.local/bin/dsh"]
                        if let found = candidates.first(where: { !$0.isEmpty && FileManager.default.isExecutableFile(atPath: $0) }) { draft.value.harness_path = found; draft.message = "已找到 Harness。可保存后测试连接。" }
                        else { draft.message = "未找到 dsh，请先安装 Harness，或浏览选择其 dsh 启动器。" }
                    }
                }
                Text(T("使用本机已安装的 Harness 及其登录、模型配置；请先在 Harness 中完成配置。不会捆绑或下载运行时。"))
                    .font(.caption).foregroundStyle(.secondary)
            }
            Text(T("新报告使用所选界面语言，六项分析要求保持一致。无新邮件不调用 AI；手动测试连接会发送一条简短测试消息，可能消耗少量 Token。"))
                .font(.caption).foregroundStyle(.secondary)
            Button(T("测试 AI 连接")) { store.testAPI { draft.message = $0 } }.disabled(draft.dirty(.ai))
            if draft.dirty(.ai) { Text(T("请先保存设置，再测试连接。")).font(.caption).foregroundStyle(.secondary) }
        }
        WorkspaceCard("费用单价") {
            HStack {
                Text(T("币种")); TextField("USD", text: $draft.currency).frame(width: 70)
                Text(T("每百万输入 Token 单价")); TextField("0", text: $draft.inputRate).frame(width: 90)
                Text(T("每百万输出 Token 单价")); TextField("0", text: $draft.outputRate).frame(width: 90)
            }
            Button(T("查看用量记录")) { showUsage = true }
            Text(T("这些是估算费用使用的单价，不是用量限额。"))
                .font(.caption).foregroundStyle(.secondary)
            Text(T("单价随本页设置统一保存，应用于当前基础地址和模型。"))
                .font(.caption).foregroundStyle(.secondary)
            Text(T("仅记录新发生的调用。接口未返回用量时标为未知；订阅和本地工具的账单无法推算。"))
                .font(.caption).foregroundStyle(.secondary)
        }
        }
    }
    private var general: some View {
        Group {
            WorkspaceCard("界面语言") {
                Picker(T("界面语言"), selection: Binding(get: { draft.value.ui_language ?? language.code }, set: { draft.value.ui_language = $0 })) {
                    Text("简体中文").tag("zh"); Text("English").tag("en"); Text("Español").tag("es")
                }
            }
            WorkspaceCard("报告保存位置") {
                HStack { Text(draft.value.output_dir).lineLimit(2).textSelection(.enabled); Spacer(); Button(T("浏览……")) { draft.chooseFolder() } }
                Text(T("新报告保存在所选文件夹／日期／邮件标题-收到时间.md。旧报告保留在原位置。"))
                    .font(.caption).foregroundStyle(.secondary)
            }
            WorkspaceCard("启动与运行") {
                Toggle(T("登录 Mac 时显示菜单栏图标"), isOn: $draft.login)
                Text(T("关闭窗口后继续在菜单栏监听。通过 Dock、菜单或 ⌘Q 退出时，停止后台并保存暂停状态；再次打开后点“开始监听”恢复。"))
                    .font(.caption).foregroundStyle(.secondary)
            }
            WorkspaceCard("通知与免打扰") {
                Toggle(T("系统通知"), isOn: $draft.value.notifications_enabled)
                Toggle(T("启用免打扰时间"), isOn: $draft.value.quiet_hours.enabled)
                HStack {
                    Text(T("开始时间")); TextField("HH:mm", text: $draft.value.quiet_hours.start).frame(width: 80)
                    Text(T("结束时间")); TextField("HH:mm", text: $draft.value.quiet_hours.end).frame(width: 80)
                }
                Text(T("使用电脑本地时间，支持跨午夜；期间继续收信和总结，静音通知不补发。"))
                    .font(.caption).foregroundStyle(.secondary)
                Text(T("相同起止时间表示全天免打扰。")).font(.caption).foregroundStyle(.secondary)
            }
            WorkspaceCard("邮件工具") { AssistantUtilitySettings(store: store) }
            WorkspaceCard("软件更新") { UpdateSettings() }
            WorkspaceCard("帮助") {
                Button(T("使用指南")) { MailHelp.openQuickStart() }
                Button(T("如何获取授权码？")) { try? MailAccountGuide.open() }
            }
            WorkspaceCard("卸载") {
                Button(T("卸载邮件小秘书……"), role: .destructive) { if !store.isTest { ServiceInstaller.uninstall(base: store.base) } }
            }
        }
    }
}

private struct StagedAccountFields: View {
    @Binding var account: SettingsDraft.Account
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Toggle(T("启用此邮箱"), isOn: $account.enabled)
            Picker(T("邮箱服务商"), selection: Binding(get: { account.connection.mail_provider }, set: { id in
                account.connection.mail_provider = id
                if let preset = MailPreset.all.first(where: { $0.id == id }), id != "custom" {
                    account.connection.host = preset.host; account.connection.mail_auth = preset.mail_auth ?? "password"
                    account.connection.security = "ssl"; account.port = "993"
                }
            })) { ForEach(MailPreset.all) { Text(T($0.name)).tag($0.id) } }
            TextField(T("邮箱地址，例如 name@example.com"), text: Binding(
                get: { account.connection.account },
                set: { account.connection = MailAccountDraft.changingAccount(account.connection, to: $0) }
            )).accessibilityLabel(T("邮箱地址"))
            TextField(T("IMAP 收件服务器，例如 imap.example.com"), text: $account.connection.host)
            HStack {
                TextField(T("端口"), text: $account.port).frame(width: 90)
                Picker(T("加密"), selection: $account.connection.security) { Text("SSL/TLS").tag("ssl"); Text("STARTTLS").tag("starttls") }
            }
            SecureField(T("密码／授权码／OAuth2 访问令牌；未改连接时可留空"), text: $account.secret)
            HStack {
                Button(T("如何获取授权码？")) { try? MailAccountGuide.open() }
                if MailAccountGuide.offersToken(account.connection.mail_auth) { Button(T("获取微软 OAuth2 Token")) { try? MailAccountGuide.openToken() } }
            }
            Picker(T("邮箱代理"), selection: $account.connection.proxy_mode) {
                Text(T("直连（不使用代理）")).tag("direct"); Text(T("使用系统代理")).tag("system"); Text("HTTP CONNECT").tag("http"); Text("SOCKS5").tag("socks5")
            }
            if ["http", "socks5"].contains(account.connection.proxy_mode) {
                HStack { TextField(T("代理地址，例如 127.0.0.1"), text: $account.connection.proxy_host); TextField(T("代理端口"), text: $account.proxyPort).frame(width: 90) }
            }
            DisclosureGroup {
                VStack(spacing: 12) {
                    TextField(T("登录用户名；留空使用邮箱地址"), text: $account.connection.username)
                    TextField(T("邮件文件夹"), text: $account.connection.mail_folder)
                    Picker(T("登录方式"), selection: $account.connection.mail_auth) { Text(T("密码／客户端授权码")).tag("password"); Text(T("OAuth2 访问令牌")).tag("oauth2") }
                }.padding(.top, 8)
            } label: {
                Text(T("高级连接选项")).background {
                    if CommandLine.arguments.contains("--self-test") { NativeTestAnchor(identifier: "mail-advanced-disclosure") }
                }
            }
        }
    }
}

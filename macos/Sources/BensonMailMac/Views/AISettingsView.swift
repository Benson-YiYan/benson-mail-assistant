import SwiftUI
import AppKit

private typealias AIState<Value> = SwiftUI.State<Value>

struct AISettingsView: View {
    @ObservedObject private var language = AppLanguage.shared
    @ObservedObject var store: MailStore
    var workspace = false
    @AIState private var provider = "api"
    @AIState private var harnessPath = ""
    @AIState private var base = ""
    @AIState private var model = ""
    @AIState private var key = ""
    @AIState private var message = ""
    @AIState private var testing = false
    private var fields: some View {
        VStack(alignment: .leading, spacing: 12) {
            Picker(T("分析方式"), selection: $provider) {
                Text(T("API（无需安装 Codex）")).tag("api")
                Text(T("Codex（使用已登录的应用）")).tag("codex")
                Text(T("DeepSeek Harness（使用已安装的应用）")).tag("deepseek_harness")
            }
            if provider == "api" {
                TextField(T("基础地址，例如 https://服务商地址/v1"), text: $base)
                    .accessibilityLabel(T("AI 基础地址"))
                TextField(T("模型名（按服务商提供的名称填写）"), text: $model)
                    .accessibilityLabel(T("AI 模型名"))
                SecureField(T("API Key；留空保留此地址已保存的 Key"), text: $key)
                    .accessibilityLabel("AI API Key")
                Text(T("支持 OpenAI 兼容的 Chat Completions 接口，自动补全 /chat/completions。API Key 保存在系统钥匙串。"))
                    .font(.caption).foregroundStyle(.secondary)
            }
            if provider == "deepseek_harness" {
                HStack {
                    TextField(T("dsh 路径；留空自动查找"), text: $harnessPath)
                    Button(T("浏览……")) {
                        let panel = NSOpenPanel()
                        panel.canChooseDirectories = false
                        panel.allowsMultipleSelection = false
                        if panel.runModal() == .OK, let url = panel.url { harnessPath = url.path }
                    }
                    Button(T("检测安装")) {
                        let candidates = [harnessPath, "/Applications/DeepSeek Harness.app/Contents/Resources/runtime/cli/bin/dsh", NSHomeDirectory() + "/Applications/DeepSeek Harness.app/Contents/Resources/runtime/cli/bin/dsh", "/opt/homebrew/bin/dsh", "/usr/local/bin/dsh", NSHomeDirectory() + "/.local/bin/dsh"]
                        if let found = candidates.first(where: { !$0.isEmpty && FileManager.default.isExecutableFile(atPath: $0) }) {
                            harnessPath = found; message = "已找到 Harness。可保存后测试连接。"
                        } else { message = "未找到 dsh，请先安装 Harness，或浏览选择其 dsh 启动器。" }
                    }
                }
                Text(T("使用本机已安装的 Harness 及其登录、模型配置；请先在 Harness 中完成配置。不会捆绑或下载运行时。"))
                    .font(.caption).foregroundStyle(.secondary)
            }
            Text(T("新报告使用所选界面语言，六项分析要求保持一致。无新邮件不调用 AI；手动测试连接会发送一条简短测试消息，可能消耗少量 Token。"))
                .font(.caption).foregroundStyle(.secondary)
        }
    }
    private var actions: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Button(T("保存 AI 设置")) { save() }.buttonStyle(.borderedProminent)
                if provider != "codex" {
                    Button(testing ? T("正在测试…") : T("测试 AI 连接")) {
                        guard save() else { return }
                        testing = true
                        store.testAPI { result in message = result; testing = false }
                    }.disabled(testing)
                }
            }
            if !message.isEmpty { Text(T(message)).font(.callout).textSelection(.enabled) }
        }
    }
    var body: some View {
        Group {
            if workspace {
                VStack(spacing: 0) {
                    ScrollView { WorkspaceCard("选择您喜欢的 AI") { fields }.padding(20) }
                    Divider()
                    actions.padding(18).frame(maxWidth: .infinity, alignment: .leading).background(Color(nsColor: .windowBackgroundColor))
                }
            } else { VStack(alignment: .leading, spacing: 12) { fields; actions } }
        }.textFieldStyle(.roundedBorder)
        .onAppear {
            harnessPath = store.settings.harness_path
            provider = store.settings.ai_provider
            base = store.settings.api_base
            model = store.settings.api_model
        }
        .onChange(of: store.needsAccountSetup) { old, new in
            if workspace && old && !new {
                harnessPath = store.settings.harness_path; provider = store.settings.ai_provider
                base = store.settings.api_base; model = store.settings.api_model
                key = ""; message = ""
            }
        }
    }
    @discardableResult private func save() -> Bool {
        do {
            try store.saveAI(provider: provider, base: base, model: model, key: key, harnessPath: harnessPath)
            key = ""; message = "已保存，下封邮件使用此配置。"
            return true
        } catch { message = error.localizedDescription; return false }
    }
}

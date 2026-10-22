import SwiftUI
private typealias SetupState<Value> = SwiftUI.State<Value>

struct SetupView: View {
    @ObservedObject private var language = AppLanguage.shared
    @ObservedObject var store: MailStore
    @SetupState private var error = ""
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text(T("欢迎使用邮件小秘书")).font(.title2.bold())
            Text(T("连接邮箱、选好 AI，即可自动整理新来信。无需安装 Python 或其他开发工具。"))
                .foregroundStyle(.secondary)
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    GroupBox(T("1 · 连接邮箱")) { MailAccountView(store: store).padding(10) }
                    GroupBox(T("2 · 选择 AI")) { AISettingsView(store: store).padding(10) }
                    GroupBox(T("3 · 报告保存位置")) {
                        HStack {
                            Text(store.settings.output_dir).textSelection(.enabled)
                            Spacer()
                            Button(T("浏览……")) { store.chooseFolder() }
                        }.padding(10)
                    }
                }
            }
            if !error.isEmpty { Text(T(error)).foregroundStyle(.red) }
            HStack {
                Button(T("稍后配置")) { store.completeAccountSetup() }
                Spacer()
                Button(T("完成配置并开始监听")) {
                    guard !store.mailAccount.isEmpty else { error = "请先保存邮箱地址与授权码。"; return }
                    if store.settings.ai_provider == "api" {
                        guard !store.settings.api_base.isEmpty, !store.settings.api_model.isEmpty else {
                            error = "请先保存 AI 设置。"; return
                        }
                    }
                    store.completeAccountSetup()
                    if !store.settings.enabled { store.toggle() }
                }.buttonStyle(.borderedProminent).disabled(store.savingAccount || store.working)
            }
            Text(T("首次检查只记录现有邮件，之后的新来信才会生成报告。没有新邮件时不调用 AI。"))
                .font(.caption).foregroundStyle(.secondary)
        }.padding(24).frame(width: 600, height: 690)
    }
}

import SwiftUI
import AppKit
private typealias SetupState<Value> = SwiftUI.State<Value>

struct SetupView: View {
    @ObservedObject private var language = AppLanguage.shared
    @ObservedObject var store: MailStore
    @SetupState private var error = ""
    @SetupState private var acceptedLegal = false
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text(T("欢迎使用邮件小秘书")).font(.title2.bold())
            Text(T("连接邮箱、选好 AI，即可自动整理新来信。无需安装 Python 或其他开发工具。"))
                .foregroundStyle(.secondary)
            if !store.settings.legal_documents_accepted {
                GroupBox(T("开始前请阅读")) {
                    VStack(alignment: .leading, spacing: 14) {
                        Text(T("请先阅读隐私政策和服务条款。邮件小秘书会在你使用 AI 功能时，将相关邮件内容发送给你配置的 AI 服务；邮箱授权和 AI 数据使用由你分别控制。"))
                        HStack {
                            Button(T("阅读隐私政策")) { openLegalPage("privacy.html") }
                            Button(T("阅读服务条款")) { openLegalPage("terms.html") }
                        }
                        Toggle(T("我已阅读并同意隐私政策和服务条款。"), isOn: $acceptedLegal)
                        Button(T("同意并继续配置")) {
                            store.acceptLegalDocuments()
                        }.buttonStyle(.borderedProminent).disabled(!acceptedLegal)
                    }.padding(8)
                }
            } else {
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
            }
        }.padding(24).frame(width: 600, height: 690)
    }
    private func openLegalPage(_ name: String) {
        if let url = URL(string: "https://benson-yiyan.github.io/benson-mail-assistant/\(name)") { NSWorkspace.shared.open(url) }
    }
}

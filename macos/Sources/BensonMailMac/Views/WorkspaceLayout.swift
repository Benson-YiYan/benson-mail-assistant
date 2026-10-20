import SwiftUI
import AppKit

enum WorkspacePage: String, CaseIterable, Identifiable {
    case reports = "邮件报告", mailbox = "邮箱与检查", ai = "AI 服务", general = "通用设置"
    var id: String { rawValue }
    var icon: String { switch self { case .reports: "tray"; case .mailbox: "envelope.badge"; case .ai: "sparkles"; case .general: "gearshape" } }
}

struct WorkspaceCard<Content: View>: View {
    @ObservedObject private var language = AppLanguage.shared
    let title: String
    @ViewBuilder var content: Content
    init(_ title: String, @ViewBuilder content: () -> Content) { self.title = title; self.content = content() }
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text(T(title)).font(.headline).accessibilityIdentifier("workspace-card-" + title)
            content
        }.frame(maxWidth: .infinity, alignment: .leading).padding(20)
            .background(Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: 12))
            .overlay(RoundedRectangle(cornerRadius: 12).stroke(Color.primary.opacity(0.08)))
    }
}

struct GeneralSettingsPage: View {
    @ObservedObject var store: MailStore
    @ObservedObject private var language = AppLanguage.shared
    var body: some View {
        ScrollView {
            VStack(spacing: 18) {
                WorkspaceCard("界面语言") { LanguageSettings() }
                WorkspaceCard("报告保存位置") {
                    HStack { Text(store.settings.output_dir).textSelection(.enabled).lineLimit(2); Spacer(); Button(T("浏览……")) { store.chooseFolder() } }
                    Text(T("新报告保存在所选文件夹／日期／邮件标题-收到时间.md。旧报告保留在原位置。"))
                        .font(.caption).foregroundStyle(.secondary)
                }
                WorkspaceCard("启动与运行") {
                    Toggle(T("登录 Mac 时显示菜单栏图标"), isOn: Binding(get: { store.loginEnabled }, set: { store.setLogin($0) }))
                    Text(T("关闭窗口后继续在菜单栏监听。通过 Dock、菜单或 ⌘Q 退出时，停止后台并保存暂停状态；再次打开后点“开始监听”恢复。"))
                        .font(.callout).foregroundStyle(.secondary)
                }
                WorkspaceCard("软件更新") { UpdateSettings() }
                WorkspaceCard("帮助") {
                    Button(T("使用指南")) { MailHelp.openQuickStart() }
                    Button(T("如何获取授权码？")) { try? MailAccountGuide.open() }
                }
                WorkspaceCard("卸载") {
                    Button(T("卸载邮件小秘书……"), role: .destructive) { if !store.isTest { ServiceInstaller.uninstall(base: store.base) } }
                    Text(T("停止后台服务并移除应用和缓存。卸载时可分别选择保留配置和邮件报告。"))
                        .font(.caption).foregroundStyle(.secondary)
                }
            }.padding(20)
        }
    }
}

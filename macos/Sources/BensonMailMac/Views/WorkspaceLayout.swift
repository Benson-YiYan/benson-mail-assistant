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
    var body: some View { StagedSettingsPage(store: store, draft: store.settingsDraft, page: .general) }
}

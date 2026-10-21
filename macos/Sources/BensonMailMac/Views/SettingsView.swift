import SwiftUI
import AppKit

// Explicit property-wrapper alias also works with SDKs that export a State macro.
private typealias DraftState<Value> = SwiftUI.State<Value>

struct IntervalControl: View {
    @ObservedObject private var language = AppLanguage.shared
    @ObservedObject var store: MailStore
    @DraftState private var draft = "60"
    @DraftState private var saved = false
    var body: some View {
        HStack {
            Text(T("自定义检查间隔"))
            TextField(T("秒数"), text: $draft).frame(width: 72)
                .accessibilityLabel(T("自定义检查间隔秒数"))
                .onSubmit { apply() }
                .onChange(of: draft) { _, _ in saved = false }
            Text(T("秒"))
            Button(T("应用间隔")) { apply() }
            if saved { Text(T("已保存")).font(.caption).foregroundStyle(.green) }
        }
        .onAppear { draft = String(store.settings.interval_seconds) }
        .help(T("输入10至86400秒，点击应用间隔后立即生效"))
    }
    private func apply() {
        store.setInterval(draft)
        saved = Int(draft.trimmingCharacters(in: .whitespaces)) == store.settings.interval_seconds
    }
}

struct SettingsView: View {
    @ObservedObject private var language = AppLanguage.shared
    @ObservedObject var store: MailStore
    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            Text(T("设置……")).font(.title2.bold())
            ForEach([WorkspacePage.mailbox, .ai, .general]) { page in
                Button(T(page.rawValue)) { open(page) }
            }
        }.padding(24).frame(width: 420, height: 240)
        .onAppear { open(.general) }
    }
    private func open(_ page: WorkspacePage) {
        if store.settingsDraft.navigate(page) || store.workspacePage == page { MailNotifications.shared.openWindow() }
    }
}

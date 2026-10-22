import SwiftUI

private typealias ToolState<Value> = SwiftUI.State<Value>
import AppKit

struct ContentView: View {
    @ObservedObject private var language = AppLanguage.shared
    @ObservedObject private var updater = AppUpdater.shared
    @ObservedObject var store: MailStore
    @Environment(\.openWindow) private var openWindow
    var body: some View {
        HSplitView {
            VStack(alignment: .leading, spacing: 16) {
                Label(T("邮件小秘书"), systemImage: "envelope.fill").font(.headline).padding(.horizontal, 16).padding(.top, 20)
                List(selection: Binding<WorkspacePage?>(get: { store.workspacePage }, set: { if let page = $0 { store.settingsDraft.navigate(page) } })) {
                    ForEach(WorkspacePage.allCases) { page in Label(T(page.rawValue), systemImage: page.icon).tag(page) }
                }.listStyle(.sidebar)
                VStack(alignment: .leading, spacing: 12) {
                    Button(T("打开报告文件夹"), systemImage: "folder") { store.openFolder() }
                    Button(T("退出邮件小秘书"), systemImage: "power") { NSApp.terminate(nil) }
                    Text(T("无新邮件不调用 AI")).font(.caption).foregroundStyle(.secondary)
                }.padding(16)
            }.frame(minWidth: 175, idealWidth: 190, maxWidth: 230)
            VStack(spacing: 0) {
                HStack {
                    VStack(alignment: .leading, spacing: 5) {
                        Text(T(store.workspacePage.rawValue)).font(.title2.bold())
                        HStack { Label(T(store.statusTitle), systemImage: store.statusIcon); Text(T("最近检查：\(T(store.lastCheck))")) }.font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer()
                    Button(store.settings.enabled ? T("暂停监听") : T("开始监听"), systemImage: store.settings.enabled ? "pause.fill" : "play.fill") { store.toggle() }.disabled(store.working)
                    Button(T(store.settings.notifications_enabled ? "暂停系统通知" : "开启系统通知"), systemImage: store.settings.notifications_enabled ? "bell" : "bell.slash") { store.toggleNotifications() }
                        .help(T("只控制系统通知，邮件监听和总结继续运行。"))
                    Button(store.checkRequested ? T("检查中…") : T("立即检查"), systemImage: "arrow.clockwise") { store.checkNow() }
                        .disabled(!store.settings.enabled || store.working || store.checkRequested || store.status.phase == "analyzing" || store.status.phase == "checking")
                }.padding(18)
                if !store.checkFeedback.isEmpty { Text(T(store.checkFeedback)).font(.caption).foregroundStyle(.secondary).frame(maxWidth: .infinity, alignment: .leading).padding(.horizontal, 18).padding(.bottom, 8) }
                if let subject = store.status.current_subject, store.status.phase == "analyzing" {
                    HStack { ProgressView().controlSize(.small); Text(subject).lineLimit(1); Spacer() }.padding(.horizontal, 18).padding(.bottom, 8)
                }
            if !updater.completionNotice.isEmpty {
                HStack {
                    VStack(alignment: .leading) {
                        Text(T(updater.completionNotice)).font(.headline)
                        Text(T(updater.detail)).font(.caption).lineLimit(3)
                    }
                    Spacer()
                    Button(T("知道了")) { updater.dismissCompletionNotice() }
                }.padding(12).background(.blue.opacity(0.08))
            }
            if let update = updater.verifiedRelease ?? updater.available {
                HStack {
                    VStack(alignment: .leading) {
                        Text(T("发现新版本") + " " + update.version).font(.headline)
                        Text(update.localizedNotes(for: language.code)).font(.caption).lineLimit(2)
                    }
                    Spacer()
                    UpdateActions(showStatus: true)
                }.padding(12).background(.blue.opacity(0.08))
            }
            if let error = store.status.error, store.settings.enabled {
                VStack(alignment: .leading, spacing: 6) {
                    Label(T("连接或分析遇到问题，服务会自动重试。"), systemImage: "exclamationmark.triangle")
                        .font(.callout).foregroundStyle(.orange)
                    DisclosureGroup(T("查看具体错误")) {
                        ScrollView { Text(T(error)).font(.caption).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading) }
                            .frame(maxHeight: 120)
                    }
                }.padding(.horizontal, 22).padding(.bottom, 12)
            }

                Divider()
                ZStack {
                    reportsPage.opacity(store.workspacePage == .reports ? 1 : 0).allowsHitTesting(store.workspacePage == .reports).accessibilityHidden(store.workspacePage != .reports).disabled(store.workspacePage != .reports)
                    StagedSettingsPage(store: store, draft: store.settingsDraft, page: .mailbox).opacity(store.workspacePage == .mailbox ? 1 : 0).allowsHitTesting(store.workspacePage == .mailbox).accessibilityHidden(store.workspacePage != .mailbox).disabled(store.workspacePage != .mailbox)
                    StagedSettingsPage(store: store, draft: store.settingsDraft, page: .ai).opacity(store.workspacePage == .ai ? 1 : 0).allowsHitTesting(store.workspacePage == .ai).accessibilityHidden(store.workspacePage != .ai).disabled(store.workspacePage != .ai)
                    StagedSettingsPage(store: store, draft: store.settingsDraft, page: .general).opacity(store.workspacePage == .general ? 1 : 0).allowsHitTesting(store.workspacePage == .general).accessibilityHidden(store.workspacePage != .general).disabled(store.workspacePage != .general)
                }.frame(maxWidth: .infinity, maxHeight: .infinity)
            }.frame(minWidth: 800, maxWidth: .infinity, maxHeight: .infinity)
        }
        .background(Color(nsColor: .windowBackgroundColor))
        .tint(.blue)
        .onAppear { MailNotifications.shared.showMainWindow = { openWindow(id: "main") } }
        .frame(minWidth: 1000, minHeight: 680)
        .disabled(updater.installing)
        .sheet(isPresented: $store.needsAccountSetup) { SetupView(store: store).interactiveDismissDisabled() }
        .alert(T("邮件小秘书"), isPresented: Binding(get: { store.problem != nil }, set: { if !$0 { store.problem = nil } })) {
            Button(T("知道了")) { store.problem = nil }
        } message: { Text(T(store.problem ?? "")) }
    }
    private var reportsPage: some View {
        VStack(spacing: 0) {
            FilterBar(store: store)
            Divider()
            HSplitView {
                ReportBrowserView(store: store).frame(minWidth: 235, idealWidth: 290, maxWidth: 380)
                VStack(alignment: .leading, spacing: 12) {
                    if let selected = store.selected {
                        HStack {
                            VStack(alignment: .leading, spacing: 5) {
                                Text(selected.title).font(.headline).lineLimit(2)
                                Text(selected.receivedLabel).font(.caption).foregroundStyle(.secondary)
                            }
                            Spacer()
                            Button(T("复制原文"), systemImage: "doc.on.doc") {
                                NSPasteboard.general.clearContents()
                                NSPasteboard.general.setString(store.reportText, forType: .string)
                            }
                            Button(T("打开报告"), systemImage: "arrow.up.right.square") { NSWorkspace.shared.open(selected.url) }
                        }
                        ReportActionsView(store: store, conversation: store.reportConversation, report: selected)
                        Divider()
                        VSplitView {
                            // A split pane must have a stable, concrete root. A transparent
                            // Group exposes the Markdown loading/content branches to NSSplitView.
                            VStack(spacing: 0) {
                                if selected.url.pathExtension.lowercased() == "md" { MarkdownReportView(text: store.reportText) }
                                else { ScrollView {
                                    Text(store.reportText).font(.system(size: 14)).lineSpacing(6)
                                        .textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading)
                                } }
                            }.frame(minHeight: 100, maxHeight: .infinity)
                            ReportConversationView(conversation: store.reportConversation, path: selected.id)
                                .frame(minHeight: 160, idealHeight: 285, maxHeight: .infinity)
                        }
                    } else {
                        ContentUnavailableView(store.reports.isEmpty ? T("等待第一份报告") : T("没有匹配的邮件"), systemImage: "tray", description: Text(store.reports.isEmpty ? T("新来信会自动整理为六项报告。") : T("试试更换关键词，或重置筛选。")))
                    }
                }.padding(20).frame(minWidth: 380, maxWidth: .infinity, maxHeight: .infinity)
            }

        }
    }
}

private struct ReportActionsView: View {
    @ObservedObject private var language = AppLanguage.shared
    @ObservedObject var store: MailStore
    @ObservedObject var conversation: ReportConversationStore
    let report: Report
    @ToolState private var showReply = false
    @ToolState private var showOriginal = false
    @ToolState private var showSources = false
    var body: some View {
        HStack {
            Button(T("重新总结"), systemImage: "sparkles") {
                let path = report.id
                Task { await conversation.regenerate(path) { original, url, text in store.applyRegeneratedReport(original, url: url, text: text) } }
            }.disabled(conversation.state(report.id).busy).accessibilityIdentifier("mail-report-regenerate")
            Button(T("回复"), systemImage: "arrowshape.turn.up.left") { showReply = true }
                .accessibilityIdentifier("mail-report-reply")
                .sheet(isPresented: $showReply) { ReplyDraftView(store: store, report: report).tint(.blue) }
            Button(T("原文"), systemImage: "doc.text") { showOriginal = true }
                .accessibilityIdentifier("mail-report-original")
                .sheet(isPresented: $showOriginal) { OriginalMailView(report: report).tint(.blue) }
            Button(T("报告溯源"), systemImage: "doc.text.magnifyingglass") { showSources = true }
                .accessibilityIdentifier("mail-report-sources")
                .sheet(isPresented: $showSources) { ReportSourcesView(store: store, report: report).tint(.blue) }
            Text(T("使用当前语言和 AI 设置，替换这份报告；原邮件不变。"))
                .font(.caption).foregroundStyle(.secondary).lineLimit(2)
        }
    }
}

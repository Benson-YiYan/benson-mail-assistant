import AppKit
import SwiftUI

private typealias ToolState<Value> = SwiftUI.State<Value>

struct ToolStatus: View {
    @ObservedObject var tools: AssistantTools
    var body: some View {
        if tools.busy { ProgressView().controlSize(.small) }
        if !tools.error.isEmpty { Text(T(tools.error)).foregroundStyle(.orange).textSelection(.enabled) }
        if !tools.notice.isEmpty { Text(T(tools.notice)).foregroundStyle(.secondary).textSelection(.enabled) }
    }
}

struct ReportToolsView: View {
    @Environment(\.dismiss) private var dismiss
    @ObservedObject private var language = AppLanguage.shared
    @ObservedObject var store: MailStore
    let report: Report
    @ToolState private var tone = "formal"
    @ToolState private var draft = ""
    @ToolState private var draftPath = ""
    @ToolState private var recipient = ""
    @ToolState private var subject = ""
    @ToolState private var instructions = ""
    @ToolState private var references: [[String: Any]] = []
    @ObservedObject private var tools: AssistantTools
    init(store: MailStore, report: Report) { self.store = store; self.report = report; self.tools = store.assistantTools }
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack { Text(T("草稿与来源")).font(.title2.bold()); Spacer(); Button(T("关闭")) { dismiss() } }
            Text(report.title).font(.headline).lineLimit(2)
            HStack {
                Picker(T("回复风格"), selection: $tone) {
                    Text(T("正式")).tag("formal")
                    Text(T("简短")).tag("brief")
                    Text(T("友好")).tag("friendly")
                }.frame(width: 250)
                Button(T("生成回复草稿"), systemImage: "square.and.pencil") {
                    Task {
                        if let result = await tools.perform("reply_draft", ["path": report.id, "tone": tone, "language": language.code, "instructions": instructions]) {
                            draft = result["draft"] as? String ?? result["text"] as? String ?? ""
                            draftPath = result["path"] as? String ?? ""
                            recipient = result["recipient"] as? String ?? ""
                            subject = result["subject"] as? String ?? ""
                        }
                    }
                }.disabled(tools.busy)
                Button(T("复制草稿"), systemImage: "doc.on.doc") {
                    NSPasteboard.general.clearContents(); NSPasteboard.general.setString(draft, forType: .string)
                }.disabled(draft.isEmpty)
            }
            TextField(T("回复要求（可选）"), text: $instructions).textFieldStyle(.roundedBorder).disabled(tools.busy)
            Text(T("按当前界面语言生成，可编辑后复制到邮箱发送。")).font(.caption).foregroundStyle(.secondary)
            if !recipient.isEmpty || !subject.isEmpty {
                Text(T("收件人") + ": " + recipient + "\n" + T("主题") + ": " + subject).font(.caption).textSelection(.enabled)
            }
            TextEditor(text: $draft).font(.body).frame(minHeight: 125, idealHeight: 160).border(.quaternary).accessibilityIdentifier("reply-draft-editor")
            Button(T("保存草稿"), systemImage: "square.and.arrow.down") {
                Task {
                    if await tools.perform("draft_save", ["draft_path": draftPath, "draft": draft]) != nil { tools.notice = T("已保存") }
                }
            }.disabled(draftPath.isEmpty || tools.busy)
            ToolStatus(tools: tools).font(.caption)
            Divider()
            HStack {
                Text(T("报告溯源")).font(.headline)
                Spacer()
                Button(T("读取来源"), systemImage: "doc.text.magnifyingglass") { Task { await loadSources() } }.disabled(tools.busy)
            }
            Text(T("来源是原始材料索引，AI 引用仍需核对；未读取的附件不会作为事实依据。")).font(.caption).foregroundStyle(.secondary)
            ScrollView {
                VStack(alignment: .leading, spacing: 10) {
                    ForEach(Array(references.enumerated()), id: \.offset) { _, source in
                        VStack(alignment: .leading, spacing: 4) {
                            Text("[" + (source["id"] as? String ?? "") + "] " + ((source["label"] as? String) ?? (source["name"] as? String) ?? "")).font(.subheadline.bold())
                            if let text = source["text"] as? String ?? source["excerpt"] as? String { Text(text).textSelection(.enabled) }
                            if let status = source["status"] as? String { Text(T(status)).font(.caption).foregroundStyle(.secondary) }
                            if source["truncated"] as? Bool == true { Text(T("仅显示部分来源内容")).font(.caption).foregroundStyle(.orange) }
                        }.frame(maxWidth: .infinity, alignment: .leading).padding(10).background(.quaternary.opacity(0.5), in: RoundedRectangle(cornerRadius: 8))
                    }
                    if references.isEmpty { Text(T("点击读取来源，查看邮件正文和附件中的可用内容。")).foregroundStyle(.secondary) }
                }
            }.frame(minHeight: 100)
        }.padding(22).frame(minWidth: 720, idealWidth: 800, minHeight: 700).task(id: report.id) { await loadSources() }
    }
    private func loadSources() async {
        if let result = await tools.perform("report_sources", ["path": report.id]) {
            references = result["sources"] as? [[String: Any]] ?? []
            tools.notice = result["limitation"] as? String ?? ""
        }
    }
}

struct QuietHoursControl: View {
    @ObservedObject var store: MailStore
    @ObservedObject private var language = AppLanguage.shared
    @ToolState private var enabled = false
    @ToolState private var start = "22:00"
    @ToolState private var end = "08:00"
    @ToolState private var saved = false
    private var valid: Bool {
        [start, end].allSatisfy { $0.range(of: #"^([01]\d|2[0-3]):[0-5]\d$"#, options: .regularExpression) != nil }
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Toggle(T("启用免打扰时间"), isOn: $enabled)
            HStack {
                Text(T("开始时间")); TextField("22:00", text: $start).frame(width: 70)
                Text(T("结束时间")); TextField("08:00", text: $end).frame(width: 70)
                Button(T("保存")) { store.saveQuietHours(QuietHours(enabled: enabled, start: start, end: end)); saved = store.problem == nil }
                    .disabled(!valid)
                if saved { Text(T("已保存")).font(.caption).foregroundStyle(.green) }
            }
            Text(T("使用电脑本地时间，支持跨午夜；期间继续收信和总结，静音通知不补发。")).font(.caption).foregroundStyle(.secondary)
        }.onAppear {
            enabled = store.settings.quiet_hours.enabled; start = store.settings.quiet_hours.start; end = store.settings.quiet_hours.end
        }.onChange(of: enabled) { _, _ in saved = false }.onChange(of: start) { _, _ in saved = false }.onChange(of: end) { _, _ in saved = false }
    }
}

struct AssistantUtilitySettings: View {
    @ObservedObject var store: MailStore
    @ObservedObject private var language = AppLanguage.shared
    @ToolState private var showHistory = false
    @ToolState private var showUsage = false
    @ObservedObject private var tools: AssistantTools
    init(store: MailStore) { self.store = store; self.tools = store.assistantTools }
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Button(T("历史邮件补总结"), systemImage: "clock.arrow.circlepath") { showHistory = true }
            Button(T("费用与用量记录"), systemImage: "chart.bar") { showUsage = true }
            Button(T("导出诊断包"), systemImage: "archivebox") {
                let panel = NSSavePanel()
                panel.nameFieldStringValue = "EmailAssistant-Diagnostics-\(Int(Date().timeIntervalSince1970)).zip"
                panel.begin { response in
                    guard response == .OK, let url = panel.url else { return }
                    Task {
                        if let result = await store.assistantTools.perform("diagnostics_export", ["destination": url.path]) {
                            store.assistantTools.notice = (result["path"] as? String) ?? url.path
                            NSWorkspace.shared.activateFileViewerSelecting([url])
                        }
                    }
                }
            }.disabled(store.assistantTools.busy)
            Text(T("诊断包包含版本与脱敏运行状态，不包含密钥、邮件正文和附件。")).font(.caption).foregroundStyle(.secondary)
            ToolStatus(tools: store.assistantTools).font(.caption)
        }.sheet(isPresented: $showHistory) { HistoryBackfillView(store: store) }
            .sheet(isPresented: $showUsage) { UsageSettingsView(store: store) }
    }
}

struct HistoryBackfillView: View {
    @ObservedObject var store: MailStore
    @ObservedObject private var language = AppLanguage.shared
    @Environment(\.dismiss) private var dismiss
    @ToolState private var from = Calendar.current.date(byAdding: .day, value: -7, to: Date()) ?? Date()
    @ToolState private var to = Date()
    @ToolState private var mailbox = ""
    @ToolState private var snapshot: [String: Any] = [:]
    @ToolState private var confirm = false
    @ObservedObject private var tools: AssistantTools
    init(store: MailStore) { self.store = store; self.tools = store.assistantTools }
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack { Text(T("历史邮件补总结")).font(.title2.bold()); Spacer(); Button(T("关闭")) { dismiss() } }
            Text(T("先查询数量，确认后才调用 AI。已完成的邮件会跳过，屏蔽规则继续生效。")).font(.callout).foregroundStyle(.secondary)
            Picker(T("邮箱"), selection: $mailbox) {
                Text(T("请选择邮箱")).tag("")
                ForEach(store.mailboxProfiles) { profile in Text(profile.connection.account).tag(profile.id) }
            }.disabled(tools.busy)
            HStack {
                DatePicker(T("开始日期"), selection: $from, displayedComponents: .date)
                DatePicker(T("结束日期"), selection: $to, displayedComponents: .date)
            }.disabled(tools.busy)
            HStack {
                Button(T("查询待处理数量")) {
                    Task {
                        snapshot = await tools.perform("history_preview", ["mailbox_id": mailbox, "from": store.dayString(from), "to": store.dayString(to)]) ?? [:]
                    }
                }.disabled(tools.busy || mailbox.isEmpty || from > to)
                if let count = snapshot["count"] as? Int { Text(T("待处理邮件") + ": \(count)") }
            }
            ToolStatus(tools: tools)
            Button(T("确认补总结")) { confirm = true }.disabled(tools.busy || (snapshot["count"] as? Int ?? 0) == 0)
            Spacer()
        }.padding(24).frame(width: 650, height: 380)
            .onChange(of: from) { _, _ in snapshot = [:] }.onChange(of: to) { _, _ in snapshot = [:] }.onChange(of: mailbox) { _, _ in snapshot = [:] }
            .confirmationDialog(T("将调用 AI 处理查询到的历史邮件，可能产生费用。"), isPresented: $confirm, titleVisibility: .visible) {
                Button(T("确认补总结")) {
                    Task {
                        if let result = await tools.perform("history_start", ["preview_id": snapshot["preview_id"] ?? snapshot["token"] ?? ""]) {
                            tools.notice = result["message"] as? String ?? T("已加入历史邮件处理队列。")
                            snapshot = [:]; store.checkNow()
                        }
                    }
                }
                Button(T("取消"), role: .cancel) {}
            }
    }
}

struct UsageSettingsView: View {
    @ObservedObject var store: MailStore
    @ObservedObject private var language = AppLanguage.shared
    @Environment(\.dismiss) private var dismiss
    @ToolState private var rows: [[String: Any]] = []
    @ObservedObject private var tools: AssistantTools
    init(store: MailStore) { self.store = store; self.tools = store.assistantTools }
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack { Text(T("费用与用量记录")).font(.title2.bold()); Spacer(); Button(T("关闭")) { dismiss() } }
            Text(T("仅记录新发生的调用。接口未返回用量时标为未知；订阅和本地工具的账单无法推算。")).font(.caption).foregroundStyle(.secondary)
            Text(T("输入 Token 是发给 AI 的内容，包括原邮件、附件和对话；输出 Token 是 AI 返回的内容。"))
                .font(.caption).foregroundStyle(.secondary)
            Text(T("这些是实际记录的用量，不是使用限额。"))
                .font(.caption).foregroundStyle(.secondary)
            Text(T("未知表示缺少价格或接口用量，不能当作免费。已知用量可能只是部分记录；金额仅为估算，不能推断实际账单。Codex 与 Harness 的订阅费用无法由本工具推算。"))
                .font(.caption).foregroundStyle(.secondary)
            Text(T("在 AI 服务页面设置单价，与其他 AI 设置一起保存。")).font(.caption).foregroundStyle(.secondary)
            Button(T("刷新")) { Task { await refresh() } }.disabled(tools.busy)
            ToolStatus(tools: tools).font(.caption)
            ScrollView {
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(Array(rows.enumerated()), id: \.offset) { _, item in
                        VStack(alignment: .leading, spacing: 4) {
                            Text((item["model"] as? String) ?? (item["provider"] as? String) ?? "").font(.headline)
                            Text(T("调用次数") + ": " + UsagePresentation.number(item, item["calls"] == nil ? "count" : "calls")).monospacedDigit()
                            Text(T("输入 Token：") + UsagePresentation.number(item, "input_tokens")).monospacedDigit()
                            Text(T("输出 Token：") + UsagePresentation.number(item, "output_tokens")).monospacedDigit()
                            Text(T("用量未知的调用") + ": " + UsagePresentation.number(item, "unknown_usage_calls"))
                                .font(.caption).foregroundStyle(.secondary).monospacedDigit()
                            Text(T("估算费用") + ": " + UsagePresentation.cost(item)).monospacedDigit()
                        }.frame(maxWidth: .infinity, alignment: .leading).padding(10).background(.quaternary, in: RoundedRectangle(cornerRadius: 8))
                    }
                    if rows.isEmpty { Text(T("暂无用量记录")).foregroundStyle(.secondary) }
                }
            }
        }.padding(24).frame(width: 730, height: 540).task { await refresh() }
    }
    private func refresh() async {
        if let result = await tools.perform("usage_summary") {
            rows = result["groups"] as? [[String: Any]] ?? result["rows"] as? [[String: Any]] ?? []

        }
    }
}

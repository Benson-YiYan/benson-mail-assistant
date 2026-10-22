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

struct ReplyDraftView: View {
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
    @ToolState private var mailboxID = ""
    @ToolState private var confirmSend = false
    @ToolState private var sent = false
    @ToolState private var sendStatus = ""
    @ObservedObject private var tools: AssistantTools
    init(store: MailStore, report: Report) {
        self.store = store; self.report = report; self.tools = store.assistantTools
        let profiles = store.mailboxProfiles
        let initial = profiles.first(where: { $0.connection.account.caseInsensitiveCompare(report.mailboxAccount) == .orderedSame })?.id
            ?? profiles.first?.id ?? ""
        _mailboxID = ToolState(initialValue: initial)
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack { Text(T("回复")).font(.title2.bold()); Spacer(); Button(T("关闭")) { dismiss() } }
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
            Text(T("按当前界面语言生成，可编辑；发送前会显示完整内容并再次确认。")).font(.caption).foregroundStyle(.secondary)
            TextField(T("收件邮箱"), text: $recipient).textFieldStyle(.roundedBorder).disabled(tools.busy || sent)
            TextField(T("主题"), text: $subject).textFieldStyle(.roundedBorder).disabled(tools.busy || sent)
            TextEditor(text: $draft).font(.body).frame(minHeight: 125, idealHeight: 160).border(.quaternary)
                .accessibilityIdentifier("reply-draft-editor").disabled(tools.busy || sent)
            HStack {
                Button(T("保存草稿"), systemImage: "square.and.arrow.down") {
                    Task {
                        if let saved = await tools.perform("draft_save", ["draft_path": draftPath, "draft": draft, "recipient": recipient, "subject": subject]) {
                            draftPath = saved["path"] as? String ?? draftPath
                            tools.notice = T("已保存")
                        }
                    }
                }.disabled(draftPath.isEmpty || draft.isEmpty || tools.busy || sent)
                Picker(T("发送邮箱"), selection: $mailboxID) {
                    Text(T("请选择邮箱")).tag("")
                    ForEach(store.mailboxProfiles) { profile in
                        Text(profile.connection.account + (profile.enabled ? "" : " · " + T("已暂停监听"))).tag(profile.id)
                    }
                }.frame(minWidth: 230).disabled(tools.busy || store.mailboxProfiles.isEmpty)
                Button(sent ? T("邮件已发送") : T("发送"), systemImage: sent ? "checkmark.circle.fill" : "paperplane.fill") { confirmSend = true }
                    .disabled(sent || draftPath.isEmpty || draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || recipient.isEmpty || mailboxID.isEmpty || tools.busy)
                    .accessibilityIdentifier("reply-send")
            }
            if !sendStatus.isEmpty { Text(T(sendStatus)).font(.caption).foregroundStyle(sendStatus.hasPrefix("邮件已发送") ? Color.secondary : Color.orange).textSelection(.enabled) }
            ToolStatus(tools: tools).font(.caption)
            Spacer(minLength: 0)
        }.padding(22).frame(minWidth: 720, idealWidth: 800, minHeight: 580)
            .sheet(isPresented: $confirmSend) { sendReview }
    }
    private var selectedMailbox: MailboxProfile? { store.mailboxProfiles.first(where: { $0.id == mailboxID }) }
    private var sendReview: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text(T("确认发送邮件")).font(.title2.bold())
            Text(T("你确定发送以下内容给") + recipient + T("吗？")).font(.headline)
            Text(T("发送前请核对以下信息。确认后邮件会立即发送。")).foregroundStyle(.secondary)
            Group {
                Text(T("发件邮箱") + "：" + (selectedMailbox?.connection.account ?? ""))
                Text(T("收件邮箱") + "：" + recipient)
                Text(T("主题") + "：" + subject)
            }.textSelection(.enabled)
            Text(T("邮件正文")).font(.headline)
            ScrollView {
                Text(draft).frame(maxWidth: .infinity, alignment: .leading).textSelection(.enabled)
                    .padding(12).background(Color(nsColor: .textBackgroundColor), in: RoundedRectangle(cornerRadius: 8))
            }.frame(minHeight: 180, maxHeight: .infinity)
            HStack {
                Spacer()
                Button(T("取消")) { confirmSend = false }
                Button(T("确认发送"), systemImage: "paperplane.fill") {
                    confirmSend = false
                    Task { await sendReply() }
                }.disabled(tools.busy || selectedMailbox == nil).accessibilityIdentifier("reply-send-confirm")
            }
            ToolStatus(tools: tools).font(.caption)
        }.padding(24).frame(width: 620, height: 650)
    }
    private func sendReply() async {
        guard let profile = selectedMailbox, !draftPath.isEmpty else { return }
        guard let saved = await tools.perform("draft_save", ["draft_path": draftPath, "draft": draft, "recipient": recipient, "subject": subject]) else { return }
        let savedPath = saved["path"] as? String ?? draftPath
        draftPath = savedPath
        guard let result = await tools.perform("reply_send", [
            "draft_path": savedPath, "draft": draft, "recipient": recipient, "subject": subject,
            "mailbox_id": profile.id, "confirmed": true
        ]) else { return }
        if result["sent"] as? Bool == true {
            sent = true
            if result["draft_status_saved"] as? Bool == false {
                sendStatus = "邮件已发送，但本机草稿状态保存失败；请检查已发送邮件。"
            } else {
                sendStatus = "邮件已发送"
            }
            tools.notice = ""
        }
    }
}

struct OriginalMailView: View {
    @Environment(\.dismiss) private var dismiss
    @ObservedObject private var language = AppLanguage.shared
    let report: Report
    private var originalBody: String { report.body.trimmingCharacters(in: .whitespacesAndNewlines) }
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack { Text(T("原文")).font(.title2.bold()); Spacer(); Button(T("关闭")) { dismiss() } }
            Text(report.title).font(.headline).textSelection(.enabled)
            HStack(spacing: 16) {
                if !report.sender.isEmpty { Text(T("发件人") + "：" + report.sender) }
                if !report.mailboxAccount.isEmpty { Text(T("邮箱") + "：" + report.mailboxAccount) }
                Text(report.receivedLabel)
            }.font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
            if !report.attachmentNames.isEmpty {
                VStack(alignment: .leading, spacing: 5) {
                    Text(T("附件")).font(.headline)
                    ForEach(Array(report.attachmentNames.enumerated()), id: \.offset) { _, name in Label(name, systemImage: "paperclip") }
                }
            }
            Divider()
            if originalBody.isEmpty {
                ContentUnavailableView(T("原邮件正文不可用"), systemImage: "envelope.badge.questionmark", description: Text(T("本地没有保存这封邮件的原文。AI 总结报告不能代替原文。")))
            } else {
                ScrollView {
                    Text(originalBody).font(.body).lineSpacing(5).frame(maxWidth: .infinity, alignment: .leading)
                        .textSelection(.enabled).padding(.vertical, 4)
                }.accessibilityIdentifier("original-mail-body")
            }
        }.padding(22).frame(minWidth: 700, idealWidth: 850, minHeight: 520)
    }
}

struct ReportSourcesView: View {
    @Environment(\.dismiss) private var dismiss
    @ObservedObject private var language = AppLanguage.shared
    let store: MailStore
    let report: Report
    @ToolState private var references: [[String: Any]] = []
    @ObservedObject private var tools: AssistantTools
    init(store: MailStore, report: Report) { self.store = store; self.report = report; self.tools = store.assistantTools }
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack { Text(T("报告溯源")).font(.title2.bold()); Spacer(); Button(T("关闭")) { dismiss() } }
            Text(report.title).font(.headline).lineLimit(2)
            Text(T("来源是原始材料索引，AI 引用仍需核对；未读取的附件不会作为事实依据。" )).font(.caption).foregroundStyle(.secondary)
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
            ToolStatus(tools: tools).font(.caption)
        }.padding(22).frame(minWidth: 720, idealWidth: 800, minHeight: 500).task(id: report.id) { await loadSources() }
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
    @ToolState private var balance: [String: Any]? = nil
    @ToolState private var queryingBalance = false
    @ObservedObject private var tools: AssistantTools
    init(store: MailStore) { self.store = store; self.tools = store.assistantTools }
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Text(T("费用与用量记录")).font(.title2.bold()); Spacer()
                Button(T("刷新")) { Task { await refresh() } }.disabled(tools.busy || queryingBalance)
                Button(T("关闭")) { dismiss() }
            }
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    Text(T("仅记录新发生的调用。接口未返回用量时标为未知；订阅和本地工具的账单无法推算。"))
                    Text(T("输入 Token 是发给 AI 的内容，包括原邮件、附件和对话；输出 Token 是 AI 返回的内容。"))
                    Text(T("这些是实际记录的用量，不是使用限额。"))
                    Text(T("上游返回费用与本地估算费用分别显示，覆盖调用不重叠；不同币种不相加。缺失费用显示未知，不代表免费。"))
                    Text(T("在 AI 服务页面设置单价，与其他 AI 设置一起保存。"))
                    balanceSection
                    ToolStatus(tools: tools)
                    ForEach(Array(rows.enumerated()), id: \.offset) { _, item in
                        VStack(alignment: .leading, spacing: 5) {
                            Text((item["model"] as? String) ?? (item["provider"] as? String) ?? "").font(.headline)
                            Text(T("调用次数") + ": " + UsagePresentation.number(item, item["calls"] == nil ? "count" : "calls"))
                            Text(T("输入 Token：") + UsagePresentation.number(item, "input_tokens"))
                            Text(T("输出 Token：") + UsagePresentation.number(item, "output_tokens"))
                            Text(T("用量未知的调用") + ": " + UsagePresentation.number(item, "unknown_usage_calls"))
                                .foregroundStyle(.secondary)
                            Text(T("上游返回费用") + ": " + UsagePresentation.cost(item, amountKey: "actual_cost", currencyKey: "actual_currency"))
                            Text(T("覆盖调用数") + ": " + UsagePresentation.number(item, "actual_cost_calls"))
                                .foregroundStyle(.secondary)
                            Text(T("本地估算费用") + ": " + UsagePresentation.cost(item))
                            Text(T("覆盖调用数") + ": " + UsagePresentation.number(item, "estimated_cost_calls"))
                                .foregroundStyle(.secondary)
                            Text(T("费用未知的调用") + ": " + UsagePresentation.number(item, "unknown_cost_calls"))
                                .foregroundStyle(.secondary)
                        }.monospacedDigit().textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading).padding(12)
                            .background(.quaternary, in: RoundedRectangle(cornerRadius: 8))
                    }
                    if rows.isEmpty { Text(T("暂无用量记录")).foregroundStyle(.secondary) }
                    Text(T("费用记录只覆盖本工具收到的调用结果；上游金额以服务商返回为准，本地估算不能代替实际账单。Codex 与 Harness 的订阅费用无法由本工具推算。"))
                }.font(.callout).frame(maxWidth: .infinity, alignment: .leading)
            }
        }.padding(24).frame(width: 760, height: 620).task { await refresh() }
    }
    private var balanceSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text(T("账户余额")).font(.headline)
                Spacer()
                Button(T(queryingBalance ? "正在查询余额…" : "查询账户余额")) { Task { await queryBalance() } }
                    .disabled(tools.busy || queryingBalance)
                    .accessibilityIdentifier("usage-query-account-balance")
            }
            Text(T("仅支持官方 DeepSeek 和 OpenRouter 的余额接口，需手动查询；不会在后台自动请求，也不会生成 AI 内容。"))
                .font(.caption).foregroundStyle(.secondary)
            Text(T("OpenRouter 余额接口需要管理权限，普通推理 Key 可能无法查询；不建议为此把推理 Key 换成管理 Key。"))
                .font(.caption).foregroundStyle(.secondary)
            Text(T("余额属于服务商账户，可能包含其他软件的使用，不能归属于本工具。"))
                .font(.caption).foregroundStyle(.secondary)
            if let balance {
                Text(UsagePresentation.provider(balance) + " · " + UsagePresentation.balanceStatus(balance))
                    .textSelection(.enabled)
                if balance["status"] as? String == "ok" {
                    let amounts = balance["balances"] as? [[String: Any]] ?? []
                    if amounts.isEmpty { Text(T("服务商未返回可用余额。")) }
                    ForEach(Array(amounts.enumerated()), id: \.offset) { _, amount in
                        VStack(alignment: .leading, spacing: 4) {
                            Text(T("可用余额") + ": " + UsagePresentation.cost(amount, amountKey: "total_balance", allowNegative: true))
                            if amount["granted_balance"] != nil {
                                Text(T("赠送余额") + ": " + UsagePresentation.cost(amount, amountKey: "granted_balance", allowNegative: true))
                            }
                            if amount["topped_up_balance"] != nil {
                                Text(T("充值余额") + ": " + UsagePresentation.cost(amount, amountKey: "topped_up_balance", allowNegative: true))
                            }
                        }.monospacedDigit().textSelection(.enabled)
                    }
                }
                if balance["checked_at"] != nil {
                    Text(T("查询时间") + ": " + UsagePresentation.checkedAt(balance, locale: language.localeIdentifier))
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
        }.padding(14).frame(maxWidth: .infinity, alignment: .leading)
            .background(.quaternary, in: RoundedRectangle(cornerRadius: 8))
    }
    private func queryBalance() async {
        guard !queryingBalance, !tools.busy else { return }
        queryingBalance = true; defer { queryingBalance = false }
        // Provider message is diagnostic data, not a localized user-facing status.
        balance = await tools.perform("usage_balance") ?? ["status": "error"]
        tools.error = ""
    }
    private func refresh() async {
        if let result = await tools.perform("usage_summary") {
            rows = result["groups"] as? [[String: Any]] ?? result["rows"] as? [[String: Any]] ?? []
        }
    }
}

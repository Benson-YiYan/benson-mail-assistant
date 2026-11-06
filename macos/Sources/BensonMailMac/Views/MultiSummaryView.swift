import SwiftUI

enum MultiSummarySelection {
    static func toggled(_ path: String, in selection: [String]) -> [String] {
        if selection.contains(path) { return selection.filter { $0 != path } }
        return selection + [path]
    }

    static func applying(_ selection: [String], to visibleReports: [Report], selected: Bool) -> [String] {
        let visible = Set(visibleReports.map(\.id))
        if selected {
            return selection + visibleReports.map(\.id).filter { !selection.contains($0) }
        }
        return selection.filter { !visible.contains($0) }
    }

    /// Preserve the order in which the user checked the reports.
    static func request(paths: [String]) -> [String: Any] { ["paths": paths] }
}

struct MultiSummaryView: View {
    @ObservedObject var store: MailStore
    @ObservedObject private var language = AppLanguage.shared
    @Environment(\.dismiss) private var dismiss
    @ObservedObject private var tools: AssistantTools
    @State private var search = ""
    @State private var selectedPaths: [String] = []
    @State private var confirm = false

    init(store: MailStore) {
        self.store = store
        self.tools = store.assistantTools
    }

    private var candidates: [Report] {
        store.reports.filter { !ReportTree.isMultiSummary($0) }
    }
    private var eligibleCount: Int { candidates.filter { $0.originalMessageAvailable }.count }

    private var visibleReports: [Report] {
        guard !search.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return candidates }
        return candidates.filter { $0.searchableText.localizedCaseInsensitiveContains(search) }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text(T("多选总结")).font(.title2.bold())
                Spacer()
                Button(T("关闭")) { dismiss() }
            }
            Text(T("选择已读取的邮件，可跨邮箱选择。确认后会一起发送给 AI 生成一份总结，可能产生费用。"))
                .font(.callout).foregroundStyle(.secondary)
            TextField(T("按标题、发件人或邮箱搜索"), text: $search)
                .textFieldStyle(.roundedBorder)
                .disabled(tools.busy)
            HStack {
                Text(T("已选择：") + "\(selectedPaths.count) / \(eligibleCount)")
                    .font(.caption).foregroundStyle(.secondary)
                Spacer()
                Button(T("清除选择")) { selectedPaths = [] }
                    .disabled(tools.busy || selectedPaths.isEmpty)
            }
            if selectedPaths.count < 2 {
                Text(T("至少选择两封邮件。")).font(.caption).foregroundStyle(.secondary)
            } else if selectedPaths.count > 100 {
                Text(T("最多选择100封邮件。")).font(.caption).foregroundStyle(.orange)
            }
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 2) {
                    ForEach(visibleReports) { report in
                        Toggle(isOn: Binding(
                            get: { selectedPaths.contains(report.id) },
                            set: { _ in selectedPaths = MultiSummarySelection.toggled(report.id, in: selectedPaths) }
                        )) {
                            VStack(alignment: .leading, spacing: 3) {
                                Text(report.title.isEmpty ? T("无标题") : report.title)
                                    .lineLimit(2)
                                HStack(spacing: 8) {
                                    Text(report.mailboxAccount.isEmpty ? T("未识别的邮箱") : report.mailboxAccount)
                                    if !report.sender.isEmpty { Text(report.sender) }
                                    Text(report.receivedLabel)
                                }
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .lineLimit(1)
                                if !report.originalMessageAvailable {
                                    Text(T("缺少原邮件数据，不能选择此项。"))
                                        .font(.caption2).foregroundStyle(.orange)
                                }
                            }
                        }
                        .toggleStyle(.checkbox)
                        .disabled(tools.busy || !report.originalMessageAvailable ||
                                  (!selectedPaths.contains(report.id) && selectedPaths.count >= 100))
                        .padding(.vertical, 4)
                        .accessibilityIdentifier("multi-summary-item")
                    }
                    if visibleReports.isEmpty {
                        Text(candidates.isEmpty ? T("暂无可选择的已读取邮件") : T("没有符合搜索条件的邮件"))
                            .font(.callout).foregroundStyle(.secondary).padding(.vertical, 16)
                    }
                }
            }
            .frame(maxHeight: .infinity)
            ToolStatus(tools: tools)
            Button(T("确认总结")) { confirm = true }
                .buttonStyle(.borderedProminent)
                .disabled(tools.busy || !(2...100).contains(selectedPaths.count))
                .accessibilityIdentifier("multi-summary-confirm")
        }
        .padding(24)
        .frame(width: 760, height: 640)
        .confirmationDialog(T("确认将选中的邮件发送给 AI 总结？"), isPresented: $confirm, titleVisibility: .visible) {
            Button(T("确认总结")) {
                let paths = selectedPaths
                Task {
                    if let result = await tools.perform("multi_summary", MultiSummarySelection.request(paths: paths)) {
                        let title = result["title"] as? String ?? ""
                        tools.notice = title.isEmpty ? T("多选总结已完成。") : T("已生成报告：") + title
                        store.scanReports()
                        dismiss()
                    }
                }
            }
            Button(T("取消"), role: .cancel) {}
        } message: {
            Text(T("这会调用 AI，根据所选邮件生成一份总结报告。"))
        }
    }
}

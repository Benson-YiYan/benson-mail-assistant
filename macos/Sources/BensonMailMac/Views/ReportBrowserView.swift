import SwiftUI

private typealias BrowserState<Value> = SwiftUI.State<Value>

struct ReportBrowserView: View {
    @ObservedObject private var language = AppLanguage.shared
    @ObservedObject var store: MailStore
    @AppStorage("report-tree-enabled") private var treeEnabled = false
    @BrowserState private var path: [String] = []

    private var visible: [Report] { treeEnabled ? ReportTree.reports(store.filteredReports, in: path) : store.filteredReports }
    private func folderLabel(_ key: String, level: Int) -> String {
        if key.isEmpty { return T(level == 0 ? "未识别的邮箱" : "未识别的发件人") }
        return level == 2 ? "From " + key : key
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text(T("邮件报告")).font(.headline)
                Spacer()
                Toggle(T("报告树"), isOn: $treeEnabled).toggleStyle(.switch).controlSize(.small)
                    .accessibilityIdentifier("report-tree-toggle")
                    .help(T("按邮箱、日期、发件人逐层浏览；搜索和筛选仍然生效。"))
            }.padding(14)
            if treeEnabled {
                ScrollView(.horizontal, showsIndicators: true) {
                    HStack(spacing: 5) {
                        Button(T("全部邮箱")) { path = [] }.buttonStyle(.link)
                        ForEach(Array(path.enumerated()), id: \.offset) { item in
                            Image(systemName: "chevron.right").font(.caption2).foregroundStyle(.secondary)
                            Button(folderLabel(item.element, level: item.offset)) { path = Array(path.prefix(item.offset + 1)) }
                                .buttonStyle(.link)
                        }
                    }.lineLimit(1).fixedSize(horizontal: true, vertical: false).padding(.vertical, 4)
                }.padding(.horizontal, 14).padding(.bottom, 8)
                HStack(spacing: 8) {
                    Button { if !path.isEmpty { path.removeLast() } } label: {
                        Image(systemName: "arrow.up").frame(width: 24, height: 24)
                    }.disabled(path.isEmpty).help(T("上一级")).accessibilityLabel(T("上一级"))
                        .accessibilityIdentifier("report-tree-up")
                    Text(path.last.map { folderLabel($0, level: path.count - 1) } ?? T("全部邮箱"))
                        .font(.caption).foregroundStyle(.secondary).lineLimit(1)
                        .help(path.last.map { folderLabel($0, level: path.count - 1) } ?? T("全部邮箱"))
                    Spacer(minLength: 0)
                }.padding(.horizontal, 14).padding(.bottom, 5)
            }
            if treeEnabled && path.count < 3 {
                List {
                    ForEach(ReportTree.folders(store.filteredReports, in: path)) { folder in
                        Button { path.append(folder.key) } label: {
                            HStack(spacing: 9) {
                                Image(systemName: "folder.fill").foregroundStyle(.blue)
                                Text(folderLabel(folder.key, level: path.count)).lineLimit(2)
                                Spacer(minLength: 4)
                                Text("\(folder.count)").font(.caption).foregroundStyle(.secondary)
                                Image(systemName: "chevron.right").font(.caption).foregroundStyle(.secondary)
                            }.padding(.vertical, 8).frame(maxWidth: .infinity, alignment: .leading).contentShape(Rectangle())
                        }.buttonStyle(.plain).accessibilityIdentifier("report-tree-folder-\(folder.key)")
                    }
                }.listStyle(.sidebar)
            } else {
                List(selection: Binding(get: { store.selected?.id }, set: { id in
                    if let report = visible.first(where: { $0.id == id }) { store.select(report) }
                })) {
                    ForEach(visible) { report in
                        VStack(alignment: .leading, spacing: 4) {
                            Text(report.title).lineLimit(1)
                            if !report.sender.isEmpty { Text(report.sender).font(.caption).foregroundStyle(.secondary).lineLimit(1) }
                            Text(report.receivedLabel).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                        }.padding(.vertical, 3).tag(report.id)
                    }
                }.listStyle(.sidebar)
            }
            if store.filteredReports.isEmpty {
                Text(store.reports.isEmpty ? T("新邮件的六项报告会出现在这里") : T("没有符合筛选条件的邮件"))
                    .font(.caption).foregroundStyle(.secondary).padding(14)
            }
        }
        .onChange(of: treeEnabled) { _, _ in path = [] }
        .onChange(of: store.filteredReports.map(\.id)) { _, _ in path = ReportTree.validPath(path, in: store.filteredReports) }
    }
}

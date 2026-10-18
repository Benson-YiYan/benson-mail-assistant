import SwiftUI

private typealias FilterState<Value> = SwiftUI.State<Value>

struct FilterBar: View {
    @ObservedObject private var language = AppLanguage.shared
    @ObservedObject var store: MailStore
    @FilterState private var expanded = false
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Image(systemName: "magnifyingglass").foregroundStyle(.secondary)
                TextField(T("搜索正文、发件人、附件名或主题"), text: $store.filter.query)
                    .textFieldStyle(.roundedBorder).accessibilityLabel(T("搜索邮件"))
                if !store.filter.query.isEmpty {
                    Button(T("清除搜索"), systemImage: "xmark.circle") { store.filter.query = "" }.labelStyle(.iconOnly)
                }
                Button(T("筛选"), systemImage: "line.3.horizontal.decrease.circle") { expanded.toggle() }
                Text(T("\(store.filteredReports.count) / \(store.reports.count) 封")).font(.caption).foregroundStyle(.secondary)
            }
            if expanded {
            HStack(spacing: 12) {
                Text(T("发件人")).foregroundStyle(.secondary)
                TextField(T("姓名或邮箱"), text: $store.filter.sender).frame(minWidth: 110, maxWidth: 180).textFieldStyle(.roundedBorder)
                    .accessibilityLabel(T("筛选发件人"))
                Menu(T("选择")) {
                    Button(T("全部发件人")) { store.filter.sender = "" }
                    ForEach(store.senders, id: \.self) { sender in Button(sender) { store.filter.sender = sender } }
                }.fixedSize()
                Picker(T("附件"), selection: $store.filter.attachments) {
                    ForEach(AttachmentFilter.allCases) { value in Text(T(value.rawValue)).tag(value) }
                }.frame(width: 170)
                Spacer()
                Button(T("重置筛选")) { store.resetFilters() }
            }
            HStack(spacing: 10) {
                Toggle(T("收到日期"), isOn: $store.dateFilterEnabled).toggleStyle(.checkbox)
                DatePicker(T("从"), selection: $store.fromDate, displayedComponents: .date).labelsHidden().disabled(!store.dateFilterEnabled)
                    .accessibilityLabel(T("开始日期"))
                Text(T("至")).foregroundStyle(.secondary)
                DatePicker(T("至"), selection: $store.toDate, displayedComponents: .date).labelsHidden().disabled(!store.dateFilterEnabled)
                    .accessibilityLabel(T("结束日期"))
                Text(T("北京时间")).font(.caption).foregroundStyle(.secondary)
                Spacer()
            }
            if store.dateFilterEnabled && store.dayString(store.fromDate) > store.dayString(store.toDate) {
                Text(T("开始日期不能晚于结束日期。")).font(.caption).foregroundStyle(.orange)
            }
            }
        }.padding(.horizontal, 22).padding(.vertical, 12)
        .environment(\.timeZone, TimeZone(identifier: "Asia/Shanghai")!)
        .onChange(of: store.filter.query) { _, _ in store.reconcileSelection() }
        .onChange(of: store.filter.sender) { _, _ in store.reconcileSelection() }
        .onChange(of: store.filter.attachments) { _, _ in store.reconcileSelection() }
        .onChange(of: store.dateFilterEnabled) { _, _ in store.reconcileSelection() }
        .onChange(of: store.fromDate) { _, _ in store.reconcileSelection() }
        .onChange(of: store.toDate) { _, _ in store.reconcileSelection() }
    }
}

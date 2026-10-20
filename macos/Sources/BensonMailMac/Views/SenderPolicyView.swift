import AppKit
import SwiftUI

private typealias PolicyState<Value> = SwiftUI.State<Value>

struct SenderPolicyView: View {
    @ObservedObject private var language = AppLanguage.shared
    @ObservedObject var store: MailStore
    var staged: SettingsDraft?
    @StateObject private var policy: SenderPolicyStore
    @PolicyState private var adding = false
    @PolicyState private var expanded = false
    @PolicyState private var selected: Set<String> = []
    init(store: MailStore, policy: SenderPolicyStore? = nil, expanded: Bool = false, staged: SettingsDraft? = nil) {
        self.staged = staged
        self.store = store
        _policy = StateObject(wrappedValue: policy ?? SenderPolicyStore(base: store.base, offline: store.isTest))
        _expanded = PolicyState(initialValue: expanded)
    }
    private var senders: [String] {
        Array(Set((store.reports.map(\.sender) + policy.knownSenders).compactMap(SenderPolicyStore.address)))
            .filter { !policy.draft.addresses.contains($0) }.sorted()
    }
    private var groups: [(String, [SkippedMailRecord])] {
        Dictionary(grouping: policy.records, by: \.sender).sorted { $0.key < $1.key }
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Picker(T("发件人规则"), selection: $policy.draft.mode) {
                Text(T("黑名单")).tag("blacklist")
                Text(T("白名单")).tag("whitelist")
            }.accessibilityIdentifier("mail-policy-mode")
            Text(T(policy.draft.mode == "whitelist"
                   ? "只总结白名单中的发件人；名单为空时会跳过所有邮件。"
                   : "跳过黑名单中的发件人，其余邮件正常总结。"))
                .font(.caption).foregroundStyle(.secondary)
            Text(T("规则对所有已添加的邮箱生效；跳过的邮件不会调用 AI，也不会从邮箱删除。"))
                .font(.caption).foregroundStyle(.secondary)
            if policy.draft.addresses.isEmpty {
                Text(T("尚未添加邮箱地址")).font(.callout).foregroundStyle(.secondary)
            } else {
                ScrollView {
                    VStack(alignment: .leading, spacing: 7) {
                        ForEach(policy.draft.addresses, id: \.self) { address in
                            HStack {
                                Text(address).textSelection(.enabled)
                                Spacer()
                                Button(T("移除"), systemImage: "minus.circle") { policy.removeAddress(address) }
                                    .accessibilityLabel(T("移除") + " " + address)
                            }
                        }
                    }
                }.frame(maxHeight: 150)
            }
            HStack {
                Button(T("添加邮箱地址"), systemImage: "plus") { policy.error = ""; adding = true }.accessibilityIdentifier("mail-policy-add")
                Spacer()
                if staged == nil { Button(T("保存屏蔽规则")) { Task { await policy.save() } }
                    .buttonStyle(.borderedProminent).disabled(!policy.dirty).accessibilityIdentifier("mail-policy-save") }
            }
            Toggle(T("不总结垃圾邮件（部分邮箱可能不支持）"), isOn: $policy.draft.skip_spam).accessibilityIdentifier("mail-policy-skip-spam")
            Text(T("仅依据邮箱服务商的垃圾邮件标记；不会凭主题或正文猜测。"))
                .font(.caption).foregroundStyle(.secondary)
            if staged == nil && policy.dirty { Text(T("有未保存的屏蔽规则")).font(.caption).foregroundStyle(.orange) }
            Divider()
            DisclosureGroup(isExpanded: $expanded) {
                VStack(alignment: .leading, spacing: 12) {
                    Text(T("仅删除本地跳过记录，不会删除邮箱中的邮件。总结一次不会把发件人移出名单。"))
                        .font(.caption).foregroundStyle(.secondary)
                    HStack {
                        Button(T("全选")) { selected = Set(policy.records.filter { !$0.busy }.map(\.id)) }
                        Button(T("取消选择")) { selected = [] }
                        Spacer()
                        Menu(T("批量操作")) {
                            Button(T("总结所选邮件一次")) { summarize(Array(selected)) }
                            Button(T("删除所选记录"), role: .destructive) { remove(Array(selected)) }
                        }.disabled(selected.isEmpty)
                        Button(T("刷新"), systemImage: "arrow.clockwise") { Task { await policy.refresh() } }
                    }
                    if policy.records.isEmpty { Text(T("没有被跳过的邮件")).foregroundStyle(.secondary) }
                    ForEach(groups, id: \.0) { sender, records in
                        VStack(alignment: .leading, spacing: 10) {
                            Label(sender.isEmpty ? T("未知发件人") : sender, systemImage: "person.crop.circle").font(.headline)
                            ForEach(records) { record in
                                HStack(alignment: .top, spacing: 9) {
                                    Toggle(T("选择邮件"), isOn: Binding(get: { selected.contains(record.id) }, set: {
                                        if $0 { selected.insert(record.id) } else { selected.remove(record.id) }
                                    })).labelsHidden().disabled(record.busy)
                                    VStack(alignment: .leading, spacing: 4) {
                                        Text(record.subject.isEmpty ? T("无主题") : record.subject).lineLimit(2)
                                        Text(record.received).font(.caption).foregroundStyle(.secondary)
                                        Text(reason(record)).font(.caption).foregroundStyle(.secondary)
                                        if let error = record.last_error, !error.isEmpty { Text(T(error)).font(.caption).foregroundStyle(.orange).textSelection(.enabled) }
                                    }
                                    Spacer()
                                    Button(T("总结一次")) { summarize([record.id]) }.disabled(record.busy)
                                    Button(T("删除记录"), role: .destructive) { remove([record.id]) }.disabled(record.busy)
                                }
                            }
                        }.padding(10).background(.quaternary, in: RoundedRectangle(cornerRadius: 8))
                    }
                }.padding(.top, 10)
            } label: {
                HStack { Text(T("被跳过的邮件")); Text("(\(policy.records.count))").foregroundStyle(.secondary) }
            }.accessibilityIdentifier("mail-policy-skipped")
            if policy.busy { HStack { ProgressView().controlSize(.small); Text(T("正在处理屏蔽规则…")).font(.caption) } }
            if !policy.notice.isEmpty { Text(T(policy.notice)).font(.caption).foregroundStyle(.secondary) }
            if !policy.error.isEmpty { Text(T(policy.error)).font(.callout).foregroundStyle(.red).textSelection(.enabled) }
        }.disabled(policy.busy)
        .sheet(isPresented: $adding) { SenderAddressPicker(policy: policy, candidates: senders) }
        .task {
            if staged == nil { policy.policyDidSave = { [weak mailStore = store] value, persist in
                guard let mailStore else { return }
                mailStore.settings.mail_policy = value
                if persist { try mailStore.save() }
            }
            }
            await policy.refresh()
            if let staged { policy.draft = staged.value.mail_policy }
        }
        .onChange(of: policy.draft) { _, value in if let staged { staged.value.mail_policy = value } }
        .onChange(of: store.status.last_check) { _, _ in Task { await policy.refresh() } }
        .onChange(of: policy.records.map(\.id)) { _, ids in selected.formIntersection(ids) }
    }
    private func reason(_ record: SkippedMailRecord) -> String {
        if record.state == "queued" { return T("已加入一次性总结队列") }
        if record.state == "processing" { return T("正在总结…") }
        switch record.reason {
        case "blacklist": return T("发件人在黑名单中")
        case "whitelist", "not_whitelisted": return T("发件人不在白名单中")
        case "spam": return T("邮箱标记为垃圾邮件")
        default: return T(record.reason)
        }
    }
    private func summarize(_ ids: [String]) { Task { await policy.summarizeRecords(ids); selected.subtract(ids) } }
    private func remove(_ ids: [String]) { Task { await policy.removeRecords(ids); selected.subtract(ids) } }
}

struct SenderAddressPicker: View {
    @ObservedObject private var language = AppLanguage.shared
    @ObservedObject var policy: SenderPolicyStore
    let candidates: [String]
    @Environment(\.dismiss) private var dismiss
    @PolicyState private var address = ""
    @PolicyState private var selected: Set<String> = []
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text(T("添加邮箱地址")).font(.title2.bold())
            TextField(T("邮箱地址，例如 name@example.com"), text: $address).accessibilityIdentifier("mail-policy-address")
            Divider()
            HStack {
                Text(T("从已有发件人批量选择")).font(.headline)
                Spacer()
                Button(T("全选")) { selected = Set(candidates) }
                Button(T("取消选择")) { selected = [] }
            }
            ScrollView {
                VStack(alignment: .leading, spacing: 10) {
                    if candidates.isEmpty { Text(T("没有可添加的已有发件人")).foregroundStyle(.secondary) }
                    ForEach(candidates, id: \.self) { sender in
                        Toggle(sender, isOn: Binding(get: { selected.contains(sender) }, set: {
                            if $0 { selected.insert(sender) } else { selected.remove(sender) }
                        }))
                    }
                }.frame(maxWidth: .infinity, alignment: .leading)
            }.frame(minHeight: 130, maxHeight: 260)
            if !policy.error.isEmpty { Text(T(policy.error)).foregroundStyle(.red).font(.caption) }
            Text(T("添加后点击本页底部的“保存”，规则才会生效。")).font(.caption).foregroundStyle(.secondary)
            HStack {
                Button(T("取消")) { dismiss() }.keyboardShortcut(.cancelAction)
                Spacer()
                Button(T("添加")) {
                    var values = Array(selected).sorted()
                    if !address.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { values.append(address) }
                    if policy.addAddresses(values) { dismiss() }
                }.buttonStyle(.borderedProminent).disabled(selected.isEmpty && address.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    .keyboardShortcut(.defaultAction)
            }
        }.padding(22).frame(width: 520).textFieldStyle(.roundedBorder)
    }
}

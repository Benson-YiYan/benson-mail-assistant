import Foundation

struct Report: Identifiable {
    let url: URL
    let modified: Date
    var metadataModified: Date? = nil
    var sender: String = ""
    var body: String = ""
    var attachmentNames: [String] = []
    var hasAttachments: Bool? = nil
    var text: String = ""
    var subject: String = ""
    var receivedAt: Date? = nil
    var mailboxAccount: String = ""
    var senderAddress: String {
        let raw = sender.trimmingCharacters(in: .whitespacesAndNewlines)
        if let range = raw.range(of: #"[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Z0-9.-]+"#, options: [.regularExpression, .caseInsensitive]) {
            return String(raw[range]).lowercased()
        }
        let folder = url.deletingLastPathComponent().lastPathComponent
        return folder.hasPrefix("From ") ? String(folder.dropFirst(5)) : raw
    }
    var id: String { url.path }
    var title: String {
        if !subject.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { return subject }
        return url.deletingPathExtension().lastPathComponent.replacingOccurrences(
            of: #"-\d{2}-\d{2}(?:-\d+)?$"#, with: "", options: .regularExpression)
    }
    var receivedLabel: String {
        if let receivedAt {
            let formatter = DateFormatter()
            formatter.locale = Locale(identifier: "zh_CN")
            formatter.timeZone = TimeZone(identifier: "Asia/Shanghai")
            formatter.dateFormat = "yyyy-MM-dd HH:mm"
            return formatter.string(from: receivedAt) + T(" · 北京时间")
        }
        let stem = url.deletingPathExtension().lastPathComponent
        if let range = stem.range(of: #"-\d{2}-\d{2}(?:-\d+)?$"#, options: .regularExpression) {
            let parts = stem[range].split(separator: "-")
            return dateLabel + " " + parts[0] + ":" + parts[1] + T(" · 北京时间")
        }
        return dateLabel
    }
    var dateLabel: String {
        var parent = url.deletingLastPathComponent()
        while parent.path != "/" {
            if parent.lastPathComponent.range(of: #"^\d{4}-\d{2}-\d{2}$"#, options: .regularExpression) != nil { return parent.lastPathComponent }
            parent.deleteLastPathComponent()
        }
        return ""
    }
    var searchableText: String { [title, mailboxAccount, sender, body, attachmentNames.joined(separator: " "), text].joined(separator: "\n") }
}

enum AttachmentFilter: String, CaseIterable, Identifiable {
    case all = "全部", withAttachments = "有附件", withoutAttachments = "无附件"
    var id: String { rawValue }
}

struct ReportFilter {
    var query = ""
    var sender = ""
    var fromDay: String? = nil
    var toDay: String? = nil
    var attachments: AttachmentFilter = .all
    func matches(_ report: Report) -> Bool {
        if let fromDay, report.dateLabel < fromDay { return false }
        if let toDay, report.dateLabel > toDay { return false }
        if !sender.isEmpty && !report.sender.localizedStandardContains(sender) { return false }
        if attachments == .withAttachments && report.hasAttachments != true { return false }
        if attachments == .withoutAttachments && report.hasAttachments != false { return false }
        let terms = query.split(whereSeparator: { $0.isWhitespace })
        if !terms.isEmpty {
            let text = report.searchableText
            if !terms.allSatisfy({ text.localizedStandardContains(String($0)) }) { return false }
        }
        return true
    }
}

struct ServiceStatus: Decodable {
    var phase: String?
    var last_check: String?
    var heartbeat: String?
    var error: String?
    var current_subject: String?
    var pending: [Int]?
}

struct MailSettings: Codable {
    var enabled: Bool = true
    var output_dir: String = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Documents/邮件").path
    var interval_seconds: Int = 60
    var ai_provider = "api"
    var api_base = ""
    var api_model = ""
    var ui_language: String? = nil
    var codex_path = ""
    var harness_path = ""
    var mailbox: MailConnection?
    var mailboxes: [MailboxProfile]?
    var mail_policy = SenderPolicyRule()
    var notifications_enabled = true
    var quiet_hours = QuietHours()
    enum CodingKeys: String, CodingKey { case enabled, output_dir, interval_seconds, ai_provider, api_base, api_model, ui_language, codex_path, harness_path, mailbox, mailboxes, mail_policy, notifications_enabled, quiet_hours }
    init() {}
    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        enabled = try values.decodeIfPresent(Bool.self, forKey: .enabled) ?? true
        output_dir = try values.decodeIfPresent(String.self, forKey: .output_dir) ?? output_dir
        interval_seconds = min(86400, max(10, try values.decodeIfPresent(Int.self, forKey: .interval_seconds) ?? 60))
        ai_provider = try values.decodeIfPresent(String.self, forKey: .ai_provider) ?? "codex"
        mailboxes = try values.decodeIfPresent([MailboxProfile].self, forKey: .mailboxes)
        api_base = try values.decodeIfPresent(String.self, forKey: .api_base) ?? ""
        ui_language = try values.decodeIfPresent(String.self, forKey: .ui_language)
        api_model = try values.decodeIfPresent(String.self, forKey: .api_model) ?? ""
        codex_path = try values.decodeIfPresent(String.self, forKey: .codex_path) ?? ""
        harness_path = try values.decodeIfPresent(String.self, forKey: .harness_path) ?? ""
        mailbox = try values.decodeIfPresent(MailConnection.self, forKey: .mailbox)
        mail_policy = try values.decodeIfPresent(SenderPolicyRule.self, forKey: .mail_policy) ?? SenderPolicyRule()
        notifications_enabled = try values.decodeIfPresent(Bool.self, forKey: .notifications_enabled) ?? true
        quiet_hours = try values.decodeIfPresent(QuietHours.self, forKey: .quiet_hours) ?? QuietHours()
    }
}

struct QuietHours: Codable {
    var enabled = false
    var start = "22:00"
    var end = "08:00"
    func contains(_ date: Date = Date()) -> Bool {
        guard enabled else { return false }
        func minutes(_ raw: String) -> Int? {
            let pieces = raw.split(separator: ":").compactMap { Int($0) }
            guard pieces.count == 2, (0...23).contains(pieces[0]), (0...59).contains(pieces[1]) else { return nil }
            return pieces[0] * 60 + pieces[1]
        }
        guard let from = minutes(start), let until = minutes(end) else { return false }
        if from == until { return true }
        let local = Calendar.current.dateComponents([.hour, .minute], from: date)
        let now = (local.hour ?? 0) * 60 + (local.minute ?? 0)
        return from < until ? now >= from && now < until : now >= from || now < until
    }
}

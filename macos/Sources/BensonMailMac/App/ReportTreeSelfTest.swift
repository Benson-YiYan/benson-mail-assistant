import Foundation

enum ReportTreeSelfTest {
    private struct Failure: LocalizedError {
        let errorDescription: String?
        init(_ message: String) { errorDescription = message }
    }
    static func run(base: URL) throws -> [String] {
        let root = base.resolvingSymlinksInPath().appendingPathComponent("report-tree-fixture-" + UUID().uuidString)
        let output = root.appendingPathComponent("reports")
        let data = root.appendingPathComponent("mail_watch")
        let fm = FileManager.default
        try fm.createDirectory(at: data, withIntermediateDirectories: true)
        defer { try? fm.removeItem(at: root) }
        func write(_ path: String, metadata: [String: Any]?) throws -> URL {
            let file = output.appendingPathComponent(path)
            try fm.createDirectory(at: file.deletingLastPathComponent(), withIntermediateDirectories: true)
            try "# Original report\n\nReport body".write(to: file, atomically: true, encoding: .utf8)
            if let metadata {
                let target = ReportMetadata.location(for: file, base: root)
                try fm.createDirectory(at: target.deletingLastPathComponent(), withIntermediateDirectories: true)
                try JSONSerialization.data(withJSONObject: metadata).write(to: target)
            }
            return file
        }
        let first = try write("a@example.com/2026-10-21/From sender@example.com/first-11-53.md",
                              metadata: ["uid": 101, "mailbox_account": "a@example.com", "from": "Sender <sender@example.com>",
                                         "subject": "First", "bodies": [["text": "original searchable body"]], "attachments": [["filename": "invoice.pdf"]]])
        _ = try write("b@example.com/2026-10-21/From sender@example.com/second-11-54.md",
                      metadata: ["uid": 101, "mailbox_account": "b@example.com", "from": "Sender <sender@example.com>", "subject": "Second"])
        _ = try write("a@example.com/2026-10-20/From older@example.com/older-10-00.md", metadata: nil)
        _ = try write("2026-10-19/legacy-09-00.txt", metadata: nil)
        let multiSummary = try write("全部邮箱/多选总结/2026-10-22/First, Second.md",
                                     metadata: ["uid": 101, "mailbox_account": "a@example.com",
                                                "from": "Sender <sender@example.com>", "subject": "First, Second",
                                                "bodies": [["text": "original searchable body"]]])
        _ = try write("全部邮箱/多选总结/2026-10-21/Older, Summary.md",
                      metadata: ["uid": 102, "mailbox_account": "b@example.com",
                                 "from": "Sender <sender@example.com>", "subject": "Older, Summary",
                                 "bodies": [["text": "another original searchable body"]]])
        _ = try write("unrelated.txt", metadata: nil)
        guard ((fm.enumerator(at: output, includingPropertiesForKeys: nil)?.allObjects as? [URL]) ?? [])
            .allSatisfy({ $0.pathExtension.lowercased() != "json" }) else {
            throw Failure("internal metadata leaked into the readable report folder")
        }
        let external = root.appendingPathComponent("outside")
        try fm.createDirectory(at: external, withIntermediateDirectories: true)
        try "# Excluded".write(to: external.appendingPathComponent("outside.md"), atomically: true, encoding: .utf8)
        try fm.createSymbolicLink(at: output.appendingPathComponent("a@example.com/2026-10-21/From outside"), withDestinationURL: external)
        let reports = ReportIndex.reports(in: output, data: data, cached: [:])
        guard reports.count == 6, let indexed = reports.first(where: { $0.url.lastPathComponent == first.lastPathComponent }),
              indexed.title == "First", indexed.dateLabel == "2026-10-21", indexed.mailboxAccount == "a@example.com",
              indexed.senderAddress == "sender@example.com", indexed.hasAttachments == true,
              indexed.originalMessageAvailable,
              indexed.receivedLabel.contains("11:53") else {
            throw Failure("recursive report discovery or nested date/metadata failed: " + reports.map {
                "\($0.id):\($0.title):\($0.dateLabel):\($0.mailboxAccount):\($0.senderAddress):\(String(describing: $0.hasAttachments)):\($0.receivedLabel)"
            }.joined(separator: "\n"))
        }
        let rootFolders = ReportTree.folders(reports, in: []).map(\.key)
        let accountDates = ReportTree.folders(reports, in: ["a@example.com"]).map(\.key)
        let accountSenders = ReportTree.folders(reports, in: ["a@example.com", "2026-10-21"]).map(\.key)
        let otherAccountReport = ReportTree.reports(reports, in: ["b@example.com", "2026-10-21", "sender@example.com"]).first?.title
        let repairedPath = ReportTree.validPath(["a@example.com", "removed"], in: reports)
        let virtual = reports.first(where: { $0.url.path == multiSummary.path })
        let summaryRoot = ReportTree.folders(reports, in: ["全部邮箱"]).map(\.key)
        let summaryDates = ReportTree.folders(reports, in: ["全部邮箱", "多选总结"]).map(\.key)
        let summaryTitles = ReportTree.reports(reports, in: ["全部邮箱", "多选总结", "2026-10-22"]).map(\.title)
        guard rootFolders.count == 4,
              accountDates == ["2026-10-21", "2026-10-20"],
              accountSenders == ["sender@example.com"],
              otherAccountReport == "Second",
              repairedPath == ["a@example.com"],
              let virtual,
              virtual.treeComponents == ["全部邮箱", "多选总结", "2026-10-22"],
              virtual.mailboxAccount == "a@example.com",
              virtual.originalMessageAvailable,
              reports.first(where: { $0.title == "older" })?.originalMessageAvailable == false,
              ReportTree.isMultiSummary(virtual),
              summaryRoot == ["多选总结"],
              summaryDates == ["2026-10-22", "2026-10-21"],
              summaryTitles == ["First, Second"] else {
            throw Failure("report tree grouping, ordering, mailbox isolation or breadcrumb repair failed: " +
                "root=\(rootFolders), accountDates=\(accountDates), senders=\(accountSenders), other=\(String(describing: otherAccountReport)), " +
                "repaired=\(repairedPath), virtual=\(String(describing: virtual?.treeComponents)), account=\(String(describing: virtual?.mailboxAccount)), " +
                "original=\(String(describing: virtual?.originalMessageAvailable)), summaryRoot=\(summaryRoot), dates=\(summaryDates), titles=\(summaryTitles)")
        }
        var filter = ReportFilter()
        filter.query = "invoice.pdf"
        filter.fromDay = "2026-10-21"
        filter.toDay = "2026-10-21"
        filter.sender = "sender@example.com"
        filter.attachments = .withAttachments
        let filtered = reports.filter { filter.matches($0) }
        guard filtered.count == 1, ReportTree.folders(filtered, in: []).first?.count == 1 else { throw Failure("tree does not respect search/date filters") }
        let cached = ReportIndex.reports(in: output, data: data, cached: Dictionary(uniqueKeysWithValues: reports.map { ($0.id, $0) }))
        guard cached.map(\.id) == reports.map(\.id), cached.first(where: { $0.url.lastPathComponent == first.lastPathComponent })?.mailboxAccount == "a@example.com" else {
            throw Failure("report metadata cache lost account identity")
        }
        return ["recursive report index supports account/date/sender, legacy TXT and virtual multi-summary paths, reads internal original-message data without JSON beside reports, excludes symlinks and unrelated files",
                "report tree isolates same-UID mailboxes, sorts dates, exposes All mailboxes/multi-summary/date virtual groups, repairs breadcrumbs, preserves search/date/attachment metadata and cached account identity"]
    }
}

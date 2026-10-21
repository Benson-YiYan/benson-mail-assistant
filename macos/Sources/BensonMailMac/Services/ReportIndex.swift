import Foundation

enum ReportIndex {
    static func reports(in directory: URL, data: URL, cached: [String: Report]) -> [Report] {
        let fm = FileManager.default
        let archives = data.deletingLastPathComponent().appendingPathComponent("mailbox-archives")
        let metadataDirectories = [data] + (((try? fm.contentsOfDirectory(at: archives, includingPropertiesForKeys: nil)) ?? [])
            .map { $0.appendingPathComponent("mail_watch") })
        // Discover both the current account/day/From sender layout and legacy day/report
        // files. Never follow directory symlinks outside the user-selected report root.
        let keys: Set<URLResourceKey> = [.isRegularFileKey, .isSymbolicLinkKey, .contentModificationDateKey]
        let root = directory.resolvingSymlinksInPath()
        let files = fm.enumerator(at: root, includingPropertiesForKeys: Array(keys),
                                  options: [.skipsHiddenFiles, .skipsPackageDescendants])
        var found: [Report] = []
        while let file = files?.nextObject() as? URL {
                let attributes = try? file.resourceValues(forKeys: keys)
                guard attributes?.isSymbolicLink != true else { continue }
                guard attributes?.isRegularFile == true, ["txt", "md"].contains(file.pathExtension.lowercased()) else { continue }
                // URL enumeration canonicalizes /tmp to /private/tmp on macOS;
                // enumerator depth gives the true relative path without alias assumptions.
                let relative = Array(file.pathComponents.suffix(files?.level ?? 0))
                let dayIndex = relative.firstIndex { $0.range(of: #"^\d{4}-\d{2}-\d{2}$"#, options: .regularExpression) != nil }
                guard let dayIndex, dayIndex == 0 || dayIndex == 1 else { continue }
                guard (dayIndex == 0 && relative.count == 2) ||
                      (dayIndex == 1 && relative.count == 4 && relative[2].hasPrefix("From ")) else { continue }
                let modified = (try? file.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate) ?? .distantPast
                let previous = cached[file.path]
                let text = previous?.modified == modified ? previous!.text : ((try? String(contentsOf: file, encoding: .utf8)) ?? "")
                let firstLine = text.split(separator: "\n", maxSplits: 1).first.map(String.init) ?? ""
                let uid = firstLine.hasPrefix("邮件编号：") ? String(firstLine.dropFirst("邮件编号：".count)).trimmingCharacters(in: .whitespaces) : ""
                let safeUID = !uid.isEmpty && uid.allSatisfy(\.isNumber)
                let sidecar = file.deletingPathExtension().appendingPathExtension("mail.json")
                let internalMetadata = ReportMetadata.location(for: file, base: data.deletingLastPathComponent())
                var metadataURL = data.appendingPathComponent(safeUID ? uid : "missing").appendingPathComponent("mail.json")
                if ReportMetadata.exists(at: internalMetadata) { metadataURL = internalMetadata }
                else if ReportMetadata.exists(at: sidecar) { metadataURL = sidecar }
                else if safeUID {
                    for directory in metadataDirectories {
                        let candidate = directory.appendingPathComponent(uid)
                        let saved = (try? Data(contentsOf: candidate.appendingPathComponent("saved.json")))
                            .flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String: Any] }
                        if saved?["saved"] as? String == file.path {
                            metadataURL = candidate.appendingPathComponent("mail.json"); break
                        }
                    }
                }
                let savedURL = metadataURL.deletingLastPathComponent().appendingPathComponent("saved.json")
                let saved = (try? Data(contentsOf: savedURL)).flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String: Any] }
                let belongsToReport = metadataURL == internalMetadata || metadataURL == sidecar || ((saved?["saved"] as? String).map { $0 == file.path } ?? true)
                let metadataModified = belongsToReport ? (try? metadataURL.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate) : nil
                if let previous, previous.modified == modified, previous.metadataModified == metadataModified { found.append(previous); continue }
                var report = Report(url: file, modified: modified)
                report.text = text; report.metadataModified = metadataModified
                if dayIndex == 1 { report.mailboxAccount = relative[0] }
                if relative.count > dayIndex + 2, relative[dayIndex + 1].hasPrefix("From ") {
                    report.sender = String(relative[dayIndex + 1].dropFirst(5))
                }
                if belongsToReport, let bytes = try? Data(contentsOf: metadataURL), let metadata = (try? JSONSerialization.jsonObject(with: bytes)) as? [String: Any] {
                    report.sender = metadata["from"] as? String ?? ""
                    report.mailboxAccount = metadata["mailbox_account"] as? String ?? report.mailboxAccount
                    report.subject = metadata["subject"] as? String ?? ""
                    if let stamp = (metadata["received_at"] ?? metadata["received"]) as? String {
                        let formatter = ISO8601DateFormatter()
                        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
                        report.receivedAt = formatter.date(from: stamp) ?? ISO8601DateFormatter().date(from: stamp)
                    }
                    let bodies = metadata["bodies"] as? [[String: Any]] ?? []
                    report.body = bodies.compactMap { $0["text"] as? String }.joined(separator: "\n")
                    if let attachments = metadata["attachments"] as? [[String: Any]] {
                        report.attachmentNames = attachments.compactMap { $0["filename"] as? String }
                        report.hasAttachments = !attachments.isEmpty
                    }
                }
                found.append(report)
        }
        return found.sorted { $0.dateLabel == $1.dateLabel ? $0.modified > $1.modified : $0.dateLabel > $1.dateLabel }
    }
}

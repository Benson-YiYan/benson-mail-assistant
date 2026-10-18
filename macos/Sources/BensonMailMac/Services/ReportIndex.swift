import Foundation

enum ReportIndex {
    static func reports(in directory: URL, data: URL, cached: [String: Report]) -> [Report] {
        let fm = FileManager.default
        let archives = data.deletingLastPathComponent().appendingPathComponent("mailbox-archives")
        let metadataDirectories = [data] + (((try? fm.contentsOfDirectory(at: archives, includingPropertiesForKeys: nil)) ?? [])
            .map { $0.appendingPathComponent("mail_watch") })
        let dates = ((try? fm.contentsOfDirectory(at: directory, includingPropertiesForKeys: [.isDirectoryKey])) ?? [])
            .filter { $0.lastPathComponent.range(of: #"^\d{4}-\d{2}-\d{2}$"#, options: .regularExpression) != nil }
        var found: [Report] = []
        for folder in dates {
            for file in (try? fm.contentsOfDirectory(at: folder, includingPropertiesForKeys: [.contentModificationDateKey])) ?? [] where ["txt", "md"].contains(file.pathExtension.lowercased()) {
                let modified = (try? file.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate) ?? .distantPast
                let previous = cached[file.path]
                let text = previous?.modified == modified ? previous!.text : ((try? String(contentsOf: file, encoding: .utf8)) ?? "")
                let firstLine = text.split(separator: "\n", maxSplits: 1).first.map(String.init) ?? ""
                let uid = firstLine.hasPrefix("邮件编号：") ? String(firstLine.dropFirst("邮件编号：".count)).trimmingCharacters(in: .whitespaces) : ""
                let safeUID = !uid.isEmpty && uid.allSatisfy(\.isNumber)
                let sidecar = file.deletingPathExtension().appendingPathExtension("mail.json")
                var metadataURL = data.appendingPathComponent(safeUID ? uid : "missing").appendingPathComponent("mail.json")
                if fm.fileExists(atPath: sidecar.path) { metadataURL = sidecar }
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
                let belongsToReport = metadataURL == sidecar || ((saved?["saved"] as? String).map { $0 == file.path } ?? true)
                let metadataModified = belongsToReport ? (try? metadataURL.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate) : nil
                if let previous, previous.modified == modified, previous.metadataModified == metadataModified { found.append(previous); continue }
                var report = Report(url: file, modified: modified)
                report.text = text; report.metadataModified = metadataModified
                if safeUID, belongsToReport, let bytes = try? Data(contentsOf: metadataURL), let metadata = (try? JSONSerialization.jsonObject(with: bytes)) as? [String: Any] {
                    report.sender = metadata["from"] as? String ?? ""
                    report.subject = metadata["subject"] as? String ?? ""
                    if let stamp = metadata["received_at"] as? String {
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
        }
        return found.sorted { $0.dateLabel == $1.dateLabel ? $0.modified > $1.modified : $0.dateLabel > $1.dateLabel }
    }
}

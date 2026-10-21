import Foundation

enum ReportUninstallSelfTest {
    private struct Failure: LocalizedError {
        let errorDescription: String?
        init(_ message: String) { errorDescription = message }
    }
    static func run(base: URL) throws -> [String] {
        let fm = FileManager.default
        let temporary = base.appendingPathComponent("nested-uninstall-" + UUID().uuidString)
        defer { try? fm.removeItem(at: temporary) }
        for preserve in [false, true] {
            let root = temporary.appendingPathComponent(preserve ? "keep" : "delete")
            let destination = temporary.appendingPathComponent("preserved")
            let dataHome = temporary.appendingPathComponent(preserve ? "keep-app-data" : "delete-app-data")
            let outside = temporary.appendingPathComponent(preserve ? "outside-keep" : "outside-delete")
            let legacy = "2026-10-20/legacy.md"
            let nested = "receiver@example.com/2026-10-21/From sender@example.com/report.md"
            let clean = "second@example.com/2026-10-21/From sender@example.com/clean.txt"
            func write(_ relative: String, _ text: String) throws {
                let file = root.appendingPathComponent(relative)
                try fm.createDirectory(at: file.deletingLastPathComponent(), withIntermediateDirectories: true)
                try text.write(to: file, atomically: true, encoding: .utf8)
            }
            for file in [legacy, nested, clean] { try write(file, "邮件编号：123\n# Synthetic report") }
            let nestedSidecar = String(nested.dropLast(3)) + ".mail.json"
            try write(nestedSidecar, "{\"uid\":123,\"from\":\"sender@example.com\",\"bodies\":[{\"text\":\"SYNTHETIC ORIGINAL MESSAGE\"}]}")
            let unrelated = "receiver@example.com/2026-10-21/From sender@example.com/personal.md"
            try write(unrelated, "# Personal notes")
            try write("settings.json", "{\"secret\":\"SYNTHETIC\"}")
            try write("mail_watch/123/mail.json", "{\"credential\":\"SYNTHETIC\"}")
            try fm.createDirectory(at: outside, withIntermediateDirectories: true)
            let sentinel = outside.appendingPathComponent("sentinel.md")
            try "邮件编号：456\nOutside".write(to: sentinel, atomically: true, encoding: .utf8)
            try fm.createSymbolicLink(at: root.appendingPathComponent("2026-10-22"), withDestinationURL: outside)
            if preserve {
                let metadata = try ServiceInstaller.metadataForPreservedReports(in: root, base: dataHome, relocatedTo: destination)
                try ServiceInstaller.preserveReportFiles(in: root, to: destination)
                try ServiceInstaller.removeUserData(base: dataHome, preserving: nil, preservingReportMetadata: metadata)
            } else {
                let owned = ReportMetadata.location(for: root.appendingPathComponent(nested), base: dataHome)
                try fm.createDirectory(at: owned.deletingLastPathComponent(), withIntermediateDirectories: true)
                try Data("{\"uid\":123}".utf8).write(to: owned)
                try ServiceInstaller.removeReports(in: root)
                try ServiceInstaller.removeUserData(base: dataHome, preserving: nil)
                guard !fm.fileExists(atPath: dataHome.path) else { throw Failure("delete-reports retained private original-message data") }
            }
            guard [legacy, nested, clean, nestedSidecar].allSatisfy({ !fm.fileExists(atPath: root.appendingPathComponent($0).path) }),
                  fm.fileExists(atPath: root.path), fm.fileExists(atPath: root.appendingPathComponent(unrelated).path),
                  fm.fileExists(atPath: root.appendingPathComponent("settings.json").path),
                  fm.fileExists(atPath: root.appendingPathComponent("mail_watch/123/mail.json").path),
                  fm.fileExists(atPath: sentinel.path),
                  !fm.fileExists(atPath: root.appendingPathComponent("second@example.com").path) else {
                throw Failure("nested report uninstall affected unrelated files, missed families or left empty account directories: preserve=\(preserve), left=\([legacy, nested, clean, nestedSidecar].filter { fm.fileExists(atPath: root.appendingPathComponent($0).path) }), root=\(fm.fileExists(atPath: root.path)), unrelated=\(fm.fileExists(atPath: root.appendingPathComponent(unrelated).path)), settings=\(fm.fileExists(atPath: root.appendingPathComponent("settings.json").path)), mail=\(fm.fileExists(atPath: root.appendingPathComponent("mail_watch/123/mail.json").path)), sentinel=\(fm.fileExists(atPath: sentinel.path)), account=\(fm.fileExists(atPath: root.appendingPathComponent("second@example.com").path))")
            }
            if preserve {
                let newReport = destination.appendingPathComponent(nested)
                let privateFile = ReportMetadata.location(for: newReport, base: dataHome)
                guard [legacy, nested, clean].allSatisfy({ fm.fileExists(atPath: destination.appendingPathComponent($0).path) }),
                      !fm.fileExists(atPath: destination.appendingPathComponent(nestedSidecar).path),
                      ReportMetadata.exists(at: privateFile),
                      ((try JSONSerialization.jsonObject(with: Data(contentsOf: privateFile))) as? [String: Any])?["uid"] as? Int == 123,
                      !fm.fileExists(atPath: destination.appendingPathComponent("settings.json").path),
                      !fm.fileExists(atPath: destination.appendingPathComponent("mail_watch").path),
                      !fm.fileExists(atPath: destination.appendingPathComponent(unrelated).path),
                      !fm.fileExists(atPath: destination.appendingPathComponent("2026-10-22").path) else {
                    throw Failure("report preservation moved credentials, unrelated files or links, or lost report paths")
                }
                let reinstalled = ReportIndex.reports(in: destination, data: dataHome.appendingPathComponent("mail_watch"), cached: [:])
                guard reinstalled.count == 3,
                      reinstalled.first(where: { $0.url.lastPathComponent == "report.md" })?.body.contains("SYNTHETIC ORIGINAL MESSAGE") == true else {
                    throw Failure("reinstalled report index cannot read retained report files and original-message data")
                }
            }
        }
        let externalRoot = temporary.appendingPathComponent("external-reports")
        let appData = temporary.appendingPathComponent("external-app-data")
        let externalReport = externalRoot.appendingPathComponent("owner@example.com/2026-10-21/From sender@example.com/external.md")
        try fm.createDirectory(at: externalReport.deletingLastPathComponent(), withIntermediateDirectories: true)
        try "邮件编号：900\nExternal report".write(to: externalReport, atomically: true, encoding: .utf8)
        let original = ReportMetadata.location(for: externalReport, base: appData)
        try fm.createDirectory(at: original.deletingLastPathComponent(), withIntermediateDirectories: true)
        try Data("{\"uid\":900,\"bodies\":[{\"text\":\"EXTERNAL ORIGINAL\"}]}".utf8).write(to: original)
        let retained = try ServiceInstaller.metadataForPreservedReports(in: externalRoot, base: appData)
        try ServiceInstaller.removeUserData(base: appData, preserving: nil, preservingReportMetadata: retained)
        let reinstalled = ReportIndex.reports(in: externalRoot, data: appData.appendingPathComponent("mail_watch"), cached: [:])
        guard reinstalled.count == 1, reinstalled[0].body == "EXTERNAL ORIGINAL",
              !fm.fileExists(atPath: appData.appendingPathComponent("settings.json").path),
              ((try fm.attributesOfItem(atPath: original.path)[.posixPermissions]) as? NSNumber)?.intValue == 0o600 else {
            throw Failure("preserving external reports without configuration lost private original data or private permissions")
        }
        try ServiceInstaller.removeReports(in: externalRoot)
        try ServiceInstaller.removeUserData(base: appData, preserving: nil)
        guard !fm.fileExists(atPath: appData.path) else { throw Failure("delete-reports retained external-report metadata") }
        return ["uninstall deletes legacy and nested report/sidecar families and empty account parents, retaining root, unrelated files, credentials and symlink targets",
                "report preservation moves only readable reports, keeps original-message metadata privately under re-keyed paths, survives reinstall indexing, and delete-reports removes private metadata"]
    }
}

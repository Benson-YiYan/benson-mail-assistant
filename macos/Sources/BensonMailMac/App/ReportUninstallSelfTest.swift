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
            try write(nestedSidecar, "{\"uid\":123}")
            let unrelated = "receiver@example.com/2026-10-21/From sender@example.com/personal.md"
            try write(unrelated, "# Personal notes")
            try write("settings.json", "{\"secret\":\"SYNTHETIC\"}")
            try write("mail_watch/123/mail.json", "{\"credential\":\"SYNTHETIC\"}")
            try fm.createDirectory(at: outside, withIntermediateDirectories: true)
            let sentinel = outside.appendingPathComponent("sentinel.md")
            try "邮件编号：456\nOutside".write(to: sentinel, atomically: true, encoding: .utf8)
            try fm.createSymbolicLink(at: root.appendingPathComponent("2026-10-22"), withDestinationURL: outside)
            if preserve { try ServiceInstaller.preserveReportFiles(in: root, to: destination) }
            else { try ServiceInstaller.removeReports(in: root) }
            guard [legacy, nested, clean, nestedSidecar].allSatisfy({ !fm.fileExists(atPath: root.appendingPathComponent($0).path) }),
                  fm.fileExists(atPath: root.path), fm.fileExists(atPath: root.appendingPathComponent(unrelated).path),
                  fm.fileExists(atPath: root.appendingPathComponent("settings.json").path),
                  fm.fileExists(atPath: root.appendingPathComponent("mail_watch/123/mail.json").path),
                  fm.fileExists(atPath: sentinel.path),
                  !fm.fileExists(atPath: root.appendingPathComponent("second@example.com").path) else {
                throw Failure("nested report uninstall affected unrelated files, missed families or left empty account directories: preserve=\(preserve), left=\([legacy, nested, clean, nestedSidecar].filter { fm.fileExists(atPath: root.appendingPathComponent($0).path) }), root=\(fm.fileExists(atPath: root.path)), unrelated=\(fm.fileExists(atPath: root.appendingPathComponent(unrelated).path)), settings=\(fm.fileExists(atPath: root.appendingPathComponent("settings.json").path)), mail=\(fm.fileExists(atPath: root.appendingPathComponent("mail_watch/123/mail.json").path)), sentinel=\(fm.fileExists(atPath: sentinel.path)), account=\(fm.fileExists(atPath: root.appendingPathComponent("second@example.com").path))")
            }
            if preserve {
                guard [legacy, nested, clean, nestedSidecar].allSatisfy({ fm.fileExists(atPath: destination.appendingPathComponent($0).path) }),
                      !fm.fileExists(atPath: destination.appendingPathComponent("settings.json").path),
                      !fm.fileExists(atPath: destination.appendingPathComponent("mail_watch").path),
                      !fm.fileExists(atPath: destination.appendingPathComponent(unrelated).path),
                      !fm.fileExists(atPath: destination.appendingPathComponent("2026-10-22").path) else {
                    throw Failure("report preservation moved credentials, unrelated files or links, or lost report paths")
                }
            }
        }
        return ["uninstall deletes legacy and nested report/sidecar families and empty account parents, retaining root, unrelated files, credentials and symlink targets",
                "report preservation moves recognized families with account/date/sender paths only; credentials, unrelated files and links remain in application data"]
    }
}

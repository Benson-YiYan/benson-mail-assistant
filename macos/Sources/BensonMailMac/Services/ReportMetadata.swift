import CryptoKit
import Foundation

/// Original-message data belongs to the app, never beside the readable report.
enum ReportMetadata {
    static func location(for report: URL, base: URL) -> URL {
        let path = report.resolvingSymlinksInPath().standardizedFileURL.path
        let key = SHA256.hash(data: Data(path.utf8)).map { String(format: "%02x", $0) }.joined()
        return base.appendingPathComponent("report_metadata").appendingPathComponent(key + ".json")
    }
    static func exists(at file: URL) -> Bool {
        let values = try? file.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey])
        return values?.isRegularFile == true && values?.isSymbolicLink != true
    }
}

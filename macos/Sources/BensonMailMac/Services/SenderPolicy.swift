import Foundation
import SwiftUI

struct SenderPolicyRule: Codable, Equatable {
    var mode = "blacklist"
    var addresses: [String] = []
    var skip_spam = false
}

struct SkippedMailRecord: Decodable, Identifiable {
    let id: String
    let sender: String
    let subject: String
    let received: String
    let reason: String
    let state: String
    let last_error: String?
    var busy: Bool { ["queued", "processing"].contains(state) }
}

struct SenderPolicySnapshot: Decodable {
    let policy: SenderPolicyRule
    let records: [SkippedMailRecord]
    let count: Int
    let senders: [String]
}

struct SenderPolicyRequest: Encodable {
    let action: String
    var policy: SenderPolicyRule? = nil
    var ids: [String]? = nil
}

/// Only edits local filtering rules and skipped-mail records. Mailbox messages stay intact.
@MainActor
final class SenderPolicyStore: ObservableObject {
    typealias Executor = (SenderPolicyRequest) async throws -> Data
    @Published var draft = SenderPolicyRule()
    @Published private(set) var saved = SenderPolicyRule()
    @Published private(set) var records: [SkippedMailRecord] = []
    @Published private(set) var knownSenders: [String] = []
    @Published private(set) var loaded = false
    @Published private(set) var busy = false
    @Published var error = ""
    @Published private(set) var notice = ""
    private let executor: Executor
    var dirty: Bool { draft != saved }
    var policyDidSave: ((SenderPolicyRule, Bool) throws -> Void)?

    init(base: URL, offline: Bool = false, executor: Executor? = nil) {
        self.executor = executor ?? { request in
            if offline {
                return try JSONEncoder().encode(OfflineSnapshot(policy: request.policy ?? SenderPolicyRule()))
            }
            return try await Self.runWorker(base: base, request: request)
        }
    }
    private struct OfflineSnapshot: Encodable {
        let policy: SenderPolicyRule
        let records: [String] = []
        let count = 0
        let senders: [String] = []
    }
    static func address(_ raw: String) -> String? {
        var value = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        if let start = value.lastIndex(of: "<"), let end = value[start...].firstIndex(of: ">") {
            value = String(value[value.index(after: start)..<end])
        }
        value = value.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard value.count <= 254, value.range(of: #"^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$"#, options: .regularExpression) != nil else { return nil }
        return value
    }
    @discardableResult func addAddresses(_ values: [String]) -> Bool {
        guard !busy else { return false }
        var normalized: [String] = []
        for value in values {
            guard let address = Self.address(value) else { error = "请输入完整的邮箱地址，例如 name@example.com。"; return false }
            if !normalized.contains(address) { normalized.append(address) }
        }
        for address in normalized where !draft.addresses.contains(address) { draft.addresses.append(address) }
        error = ""; notice = ""
        return true
    }
    func removeAddress(_ address: String) {
        guard !busy else { return }
        draft.addresses.removeAll { $0 == address }; notice = ""
    }
    func refresh() async { await perform(SenderPolicyRequest(action: "status"), savesDraft: false) }
    func save() async { await perform(SenderPolicyRequest(action: "save", policy: draft), savesDraft: true) }
    func removeRecords(_ ids: [String]) async {
        guard !ids.isEmpty else { return }
        await perform(SenderPolicyRequest(action: "remove_records", ids: ids), savesDraft: false)
    }
    func summarizeRecords(_ ids: [String]) async {
        guard !ids.isEmpty else { return }
        await perform(SenderPolicyRequest(action: "summarize_records", ids: ids), savesDraft: false)
    }
    private func perform(_ request: SenderPolicyRequest, savesDraft: Bool) async {
        guard !busy else { return }
        busy = true; error = ""; notice = ""
        defer { busy = false }
        do {
            let bytes = try await executor(request)
            guard bytes.count <= 32 * 1024 * 1024 else { throw Failure(message: "被跳过邮件记录过大，请稍后重试。") }
            if let value = try? JSONSerialization.jsonObject(with: bytes) as? [String: Any], value["ok"] as? Bool == false {
                throw Failure(message: (value["detail"] as? String) ?? (value["error"] as? String) ?? "邮件规则操作失败，请重试。")
            }
            let snapshot = try JSONDecoder().decode(SenderPolicySnapshot.self, from: bytes)
            let preserveDraft = loaded && dirty && !savesDraft
            saved = snapshot.policy
            if !preserveDraft { draft = snapshot.policy }
            records = snapshot.records; knownSenders = snapshot.senders; loaded = true
            try policyDidSave?(snapshot.policy, savesDraft)
            if savesDraft { notice = "屏蔽规则已保存。" }
            if request.action == "remove_records" { notice = "本地记录已删除，邮箱中的原邮件未删除。" }
            if request.action == "summarize_records" { notice = "所选邮件已加入一次性总结队列，不会改变屏蔽规则。" }
        } catch { self.error = error.localizedDescription }
    }
    struct Failure: LocalizedError {
        let message: String
        var errorDescription: String? { message }
    }
    private static func runWorker(base: URL, request: SenderPolicyRequest) async throws -> Data {
        let executable = ServiceInstaller.worker
        return try await Task.detached(priority: .userInitiated) {
            let requests = base.appendingPathComponent("policy-requests")
            try FileManager.default.createDirectory(at: requests, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
            let file = requests.appendingPathComponent(UUID().uuidString + ".json")
            defer { try? FileManager.default.removeItem(at: file) }
            try JSONEncoder().encode(request).write(to: file, options: .atomic)
            try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: file.path)
            let process = Process(), output = Pipe()
            process.executableURL = executable
            process.arguments = ["--home", base.path, "--mail-policy", file.path]
            process.standardOutput = output; process.standardError = FileHandle.nullDevice
            try process.run()
            let bytes = output.fileHandleForReading.readDataToEndOfFile()
            process.waitUntilExit()
            guard process.terminationStatus == 0 else {
                if let value = try? JSONSerialization.jsonObject(with: bytes) as? [String: Any] {
                    throw Failure(message: (value["detail"] as? String) ?? (value["error"] as? String) ?? "邮件规则操作失败，请重试。")
                }
                throw Failure(message: "邮件规则操作失败，请重试。")
            }
            return bytes
        }.value
    }
}

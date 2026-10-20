import AppKit
import Foundation
import SwiftUI

struct ReportChatMessage: Decodable, Identifiable {
    let id = UUID()
    let role: String
    let content: String
    let files: [String]
    private struct Attachment: Decodable { let name: String?; let filename: String?; let path: String? }
    enum CodingKeys: String, CodingKey { case role, content, files }
    init(role: String, content: String, files: [String] = []) {
        self.role = role; self.content = content; self.files = files
    }
    init(from decoder: Decoder) throws {
        let value = try decoder.container(keyedBy: CodingKeys.self)
        role = try value.decode(String.self, forKey: .role)
        content = try value.decode(String.self, forKey: .content)
        if let paths = try? value.decode([String].self, forKey: .files) { files = paths }
        else if let attachments = try? value.decode([Attachment].self, forKey: .files) {
            files = attachments.compactMap { $0.name ?? $0.filename ?? $0.path }
        } else { files = [] }
    }
}

struct ReportChatSnapshot: Decodable {
    let messages: [ReportChatMessage]
    let compressed: Bool
    enum CodingKeys: String, CodingKey { case messages, compressed }
    init(from decoder: Decoder) throws {
        let value = try decoder.container(keyedBy: CodingKeys.self)
        messages = try value.decode([ReportChatMessage].self, forKey: .messages)
        compressed = try value.decodeIfPresent(Bool.self, forKey: .compressed) ?? false
    }
}

struct ReportConversationState {
    var messages: [ReportChatMessage] = []
    var compressed = false
    var loaded = false
    var busy = false
    var operation = ""
    var error = ""
    var draft = ""
    var files: [String] = []
}

/// Owns presentation state by report path. The worker owns persistent history and report files.
@MainActor
final class ReportConversationStore: ObservableObject {
    typealias Executor = ([String]) async throws -> Data
    @Published private(set) var sessions: [String: ReportConversationState] = [:]
    private let base: URL
    private let executor: Executor
    private struct ChatRequest: Encodable { let path: String; let text: String; let files: [String] }
    private struct RetryResult: Decodable { let text: String; let path: String }
    struct Failure: LocalizedError {
        let message: String
        var errorDescription: String? { message }
    }
    init(base: URL, offline: Bool = false, executor: Executor? = nil) {
        self.base = base
        self.executor = executor ?? { arguments in
            if offline {
                if arguments.first == "--chat-history" { return Data("{\"messages\":[],\"compressed\":false}".utf8) }
                throw Failure(message: "模拟测试不会请求真实 AI 服务。")
            }
            return try await Self.runWorker(base: base, arguments: arguments)
        }
    }
    func state(_ path: String) -> ReportConversationState { sessions[path] ?? ReportConversationState() }
    private func update(_ path: String, _ action: (inout ReportConversationState) -> Void) {
        var value = state(path); action(&value); sessions[path] = value
    }
    func draft(_ text: String, for path: String) { update(path) { $0.draft = text } }
    func addFiles(_ urls: [URL], for path: String) {
        update(path) { value in
            guard !value.busy else { return }
            for url in urls where url.isFileURL {
                let file = url.standardizedFileURL.path
                if !value.files.contains(file) { value.files.append(file) }
            }
        }
    }
    func removeFile(_ file: String, for path: String) { update(path) { if !$0.busy { $0.files.removeAll { $0 == file } } } }
    func chooseFiles(for path: String) {
        guard !state(path).busy else { return }
        let panel = NSOpenPanel()
        panel.title = T("选择向 AI 提问时附加的文件")
        panel.prompt = T("添加附件")
        panel.canChooseFiles = true; panel.canChooseDirectories = false; panel.allowsMultipleSelection = true
        panel.begin { [weak self] result in
            guard result == .OK else { return }
            Task { @MainActor in self?.addFiles(panel.urls, for: path) }
        }
    }
    func load(_ path: String, force: Bool = false) async {
        guard !state(path).busy, force || !state(path).loaded else { return }
        update(path) { $0.busy = true; $0.operation = "正在恢复对话…"; $0.error = "" }
        defer { update(path) { $0.busy = false; $0.operation = "" } }
        do {
            let bytes = try await executor(["--chat-history", path])
            let snapshot = try Self.decode(ReportChatSnapshot.self, from: bytes)
            update(path) { $0.messages = snapshot.messages; $0.compressed = snapshot.compressed; $0.loaded = true }
        } catch { update(path) { $0.error = error.localizedDescription } }
    }
    func send(_ path: String) async {
        let original = state(path)
        let question = original.draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !original.busy, !question.isEmpty || !original.files.isEmpty else { return }
        update(path) { $0.busy = true; $0.operation = "正在回答邮件问题…"; $0.error = "" }
        defer { update(path) { $0.busy = false; $0.operation = "" } }
        do {
            // Send private request text through a temporary file, never through command-line arguments.
            let requests = base.appendingPathComponent("chat-requests")
            try FileManager.default.createDirectory(at: requests, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
            let request = requests.appendingPathComponent(UUID().uuidString + ".json")
            defer { try? FileManager.default.removeItem(at: request) }
            let bytes = try JSONEncoder().encode(ChatRequest(path: path, text: question, files: original.files))
            try bytes.write(to: request, options: .atomic)
            try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: request.path)
            let result = try await executor(["--chat-send", request.path])
            let snapshot = try Self.decode(ReportChatSnapshot.self, from: result)
            update(path) {
                $0.messages = snapshot.messages; $0.compressed = snapshot.compressed; $0.loaded = true
                // Preserve edits if a caller changed a draft while the worker was running.
                if $0.draft == original.draft { $0.draft = "" }
                if $0.files == original.files { $0.files = [] }
            }
        } catch { update(path) { $0.error = error.localizedDescription } }
    }
    func regenerate(_ path: String, updated: (String, URL, String) -> Void) async {
        guard !state(path).busy else { return }
        update(path) { $0.busy = true; $0.operation = "正在重新总结…"; $0.error = "" }
        defer { update(path) { $0.busy = false; $0.operation = "" } }
        do {
            let bytes = try await executor(["--report-retry", path])
            let result = try Self.decode(RetryResult.self, from: bytes)
            guard !result.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                  result.path.hasPrefix("/"), ["md", "txt"].contains(URL(fileURLWithPath: result.path).pathExtension.lowercased()) else {
                throw Failure(message: "后台返回的报告内容无效，请重试。")
            }
            updated(path, URL(fileURLWithPath: result.path), result.text)
        } catch { update(path) { $0.error = error.localizedDescription } }
    }
    private static func decode<Value: Decodable>(_ type: Value.Type, from data: Data) throws -> Value {
        guard data.count <= 40 * 1024 * 1024 else { throw Failure(message: "后台返回的数据过大，请重试。") }
        if let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any], object["ok"] as? Bool == false {
            let message = (object["detail"] as? String) ?? (object["error"] as? String) ?? "邮件操作失败，请检查 AI 设置后重试。"
            throw Failure(message: message)
        }
        do { return try JSONDecoder().decode(type, from: data) }
        catch { throw Failure(message: "无法读取后台返回的结果，请更新软件后重试。") }
    }
    private static func runWorker(base: URL, arguments: [String]) async throws -> Data {
        let executable = ServiceInstaller.worker
        return try await Task.detached(priority: .userInitiated) {
            let process = Process(), output = Pipe()
            process.executableURL = executable
            process.arguments = ["--home", base.path] + arguments
            process.standardOutput = output; process.standardError = FileHandle.nullDevice
            do { try process.run() }
            catch { throw Failure(message: "无法启动邮件操作，请检查后台组件。") }
            let bytes = output.fileHandleForReading.readDataToEndOfFile()
            process.waitUntilExit()
            if process.terminationStatus != 0 {
                if let object = try? JSONSerialization.jsonObject(with: bytes) as? [String: Any],
                   let message = (object["detail"] as? String) ?? (object["error"] as? String) { throw Failure(message: message) }
                throw Failure(message: "邮件操作失败，请检查 AI 设置后重试。")
            }
            return bytes
        }.value
    }
}

import AppKit
import SwiftUI

/// Invokes local worker tools. Private text goes through a restricted request file.
@MainActor final class AssistantTools: ObservableObject {
    @Published var busy = false
    @Published var error = ""
    @Published var notice = ""
    @Published var reply = ""
    @Published var sources: [[String: Any]] = []
    @Published var usage: [String: Any] = [:]
    @Published var preview: [String: Any] = [:]
    private let base: URL
    private let offline: Bool
    typealias Executor = ([String: Any]) async throws -> [String: Any]
    private let executor: Executor?
    init(base: URL, offline: Bool = false, executor: Executor? = nil) { self.base = base; self.offline = offline; self.executor = executor }

    func perform(_ action: String, _ values: [String: Any] = [:]) async -> [String: Any]? {
        guard !busy else { return nil }
        busy = true; error = ""; notice = ""
        defer { busy = false }
        do {
            var request = values; request["action"] = action
            if let executor {
                let result = try await executor(request)
                guard result["ok"] as? Bool != false else { throw ReportConversationStore.Failure(message: result["error"] as? String ?? T("操作失败，请重试。")) }
                return result
            }
            guard !offline else { throw ReportConversationStore.Failure(message: T("模拟测试不会请求真实 AI 服务。")) }
            let data = try JSONSerialization.data(withJSONObject: request)
            let home = base
            let executable = ServiceInstaller.worker
            let bytes = try await Task.detached(priority: .userInitiated) { () throws -> Data in
                let directory = home.appendingPathComponent("tool-requests")
                try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
                let file = directory.appendingPathComponent(UUID().uuidString + ".json")
                defer { try? FileManager.default.removeItem(at: file) }
                try data.write(to: file, options: .atomic)
                try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: file.path)
                let process = Process(), output = Pipe()
                process.executableURL = executable
                process.arguments = ["--home", home.path, "--assistant-tools", file.path]
                process.standardOutput = output; process.standardError = FileHandle.nullDevice
                try process.run()
                let result = output.fileHandleForReading.readDataToEndOfFile()
                process.waitUntilExit()
                guard result.count <= 32 * 1024 * 1024 else { throw ReportConversationStore.Failure(message: T("后台返回的数据过大，请重试。")) }
                return result
            }.value
            guard let result = try JSONSerialization.jsonObject(with: bytes) as? [String: Any] else {
                throw ReportConversationStore.Failure(message: T("无法读取后台返回的结果，请更新软件后重试。"))
            }
            guard result["ok"] as? Bool != false else {
                throw ReportConversationStore.Failure(message: (result["detail"] as? String) ?? (result["error"] as? String) ?? T("操作失败，请重试。"))
            }
            return result
        } catch { self.error = error.localizedDescription; return nil }
    }
}

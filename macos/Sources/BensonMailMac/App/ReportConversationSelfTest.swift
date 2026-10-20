import Foundation

@MainActor
enum ReportConversationSelfTest {
    private struct Failure: LocalizedError {
        let message: String
        var errorDescription: String? { message }
    }
    private static func require(_ value: @autoclosure () -> Bool, _ reason: String) throws {
        if !value() { throw Failure(message: reason) }
    }
    /// A disk-backed synthetic worker boundary. It never opens mail, credentials or a network connection.
    @MainActor private final class WorkerFixture {
        let base: URL
        let history: URL
        var pauseNextSend = false
        var pending: CheckedContinuation<Void, Never>?
        var nextFailure = false
        var sendCount = 0
        var retryCount = 0
        var requestFiles: [URL] = []
        init(base: URL) { self.base = base; history = base.appendingPathComponent("fixture-history.json") }
        func release() { pending?.resume(); pending = nil }
        func run(_ arguments: [String]) async throws -> Data {
            guard arguments.count == 2 else { throw Failure(message: "private worker arguments malformed") }
            if nextFailure { nextFailure = false; return Data("{\"ok\":false,\"error\":\"synthetic offline failure\"}".utf8) }
            var saved = ((try? Data(contentsOf: history)).flatMap { try? JSONSerialization.jsonObject(with: $0) }) as? [String: [[String: Any]]] ?? [:]
            func snapshot(_ path: String) throws -> Data {
                let rows = saved[path] ?? []
                return try JSONSerialization.data(withJSONObject: ["messages": rows, "compressed": rows.count >= 4])
            }
            switch arguments[0] {
            case "--chat-history": return try snapshot(arguments[1])
            case "--chat-send":
                let file = URL(fileURLWithPath: arguments[1])
                requestFiles.append(file)
                let mode = (try FileManager.default.attributesOfItem(atPath: file.path)[.posixPermissions] as? NSNumber)?.intValue
                try ReportConversationSelfTest.require(mode == 0o600, "private chat request permissions incorrect")
                let request = try JSONSerialization.jsonObject(with: Data(contentsOf: file)) as! [String: Any]
                let path = request["path"] as! String, text = request["text"] as! String, files = request["files"] as! [String]
                sendCount += 1
                if pauseNextSend {
                    pauseNextSend = false
                    await withCheckedContinuation { pending = $0 }
                }
                // Read at operation time, just as the real worker does. The UI must not bake a language into the request.
                let settings = try JSONSerialization.jsonObject(with: Data(contentsOf: base.appendingPathComponent("settings.json"))) as! [String: String]
                let answer = settings["ui_language"] == "es" ? "Respuesta en español" : "Answer in English"
                var rows = saved[path] ?? []
                rows.append(["role": "user", "content": text, "files": files.map { ["name": URL(fileURLWithPath: $0).lastPathComponent, "size": 12] as [String: Any] }])
                rows.append(["role": "assistant", "content": answer])
                saved[path] = rows
                try JSONSerialization.data(withJSONObject: saved).write(to: history, options: .atomic)
                return try snapshot(path)
            case "--report-retry":
                retryCount += 1
                let path = arguments[1]
                let settings = try JSONSerialization.jsonObject(with: Data(contentsOf: base.appendingPathComponent("settings.json"))) as! [String: String]
                let text = settings["ui_language"] == "es" ? "## 1. Correo nuevo\n\nResumen nuevo" : "## 1. New email\n\nNew summary"
                try Data(text.utf8).write(to: URL(fileURLWithPath: path), options: .atomic)
                return try JSONSerialization.data(withJSONObject: ["text": text, "path": path])
            default: throw Failure(message: "unexpected synthetic worker operation")
            }
        }
    }
    static func run(base: URL) async throws -> [String] {
        let root = base.appendingPathComponent("report-conversation-fixture")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        let settings = root.appendingPathComponent("settings.json")
        try Data("{\"ui_language\":\"es\"}".utf8).write(to: settings)
        let a = root.appendingPathComponent("report-a.md"), b = root.appendingPathComponent("report-b.md")
        let attachment = root.appendingPathComponent("additional-contract.txt")
        try Data("Original A".utf8).write(to: a); try Data("Original B".utf8).write(to: b)
        try Data("Synthetic additional contract".utf8).write(to: attachment)
        let worker = WorkerFixture(base: root)
        let chat = ReportConversationStore(base: root, executor: { try await worker.run($0) })
        await chat.load(a.path)
        try require(chat.state(a.path).loaded && chat.state(a.path).messages.isEmpty, "empty persistent chat did not restore")
        chat.draft("Question A", for: a.path); chat.addFiles([attachment, attachment], for: a.path)
        chat.draft("Unsent B", for: b.path)
        try require(chat.state(a.path).files == [attachment.path], "chosen files were duplicated")
        worker.pauseNextSend = true
        let sending = Task { await chat.send(a.path) }
        for _ in 0..<100 where worker.pending == nil { await Task.yield() }
        try require(worker.pending != nil && chat.state(a.path).busy, "in-flight send did not enter busy state")
        await chat.send(a.path)
        var wronglyRetried = false
        await chat.regenerate(a.path) { _, _, _ in wronglyRetried = true }
        await chat.load(b.path)
        try require(worker.sendCount == 1 && !wronglyRetried && worker.retryCount == 0, "duplicate send/regeneration bypassed busy guard")
        try require(chat.state(b.path).messages.isEmpty && chat.state(b.path).draft == "Unsent B", "opening another report leaked the first conversation")
        worker.release(); await sending.value
        try require(chat.state(a.path).messages.count == 2 && chat.state(a.path).messages.last?.content == "Respuesta en español", "Spanish answer not stored on the originating report")
        try require(chat.state(b.path).messages.isEmpty && chat.state(b.path).draft == "Unsent B", "completed first-report answer overwrote the second report")
        try require(chat.state(a.path).draft.isEmpty && chat.state(a.path).files.isEmpty && !chat.state(a.path).busy, "successful send did not clear its own composer")
        try require(worker.requestFiles.allSatisfy { !FileManager.default.fileExists(atPath: $0.path) }, "private request was left on disk")
        let restored = ReportConversationStore(base: root, executor: { try await worker.run($0) })
        await restored.load(a.path)
        try require(restored.state(a.path).messages.count == 2 && restored.state(a.path).messages.first?.files == [attachment.lastPathComponent], "persisted history/attachments were not restored in a fresh UI store")
        try Data("{\"ui_language\":\"en\"}".utf8).write(to: settings)
        restored.draft("Follow-up", for: a.path)
        await restored.send(a.path)
        try require(restored.state(a.path).messages.count == 4 && restored.state(a.path).compressed && restored.state(a.path).messages.last?.content == "Answer in English", "multi-turn/current-language/compression state incorrect")
        restored.draft("Keep this failed question", for: a.path); restored.addFiles([attachment], for: a.path)
        worker.nextFailure = true
        await restored.send(a.path)
        try require(restored.state(a.path).error.contains("synthetic offline failure") && !restored.state(a.path).busy && restored.state(a.path).draft == "Keep this failed question" && restored.state(a.path).files == [attachment.path] && restored.state(a.path).messages.count == 4, "failed send lost draft, files or prior history")
        var regenerated: (String, URL, String)?
        await restored.regenerate(a.path) { regenerated = ($0, $1, $2) }
        try require(regenerated?.0 == a.path && regenerated?.1 == a && regenerated?.2.contains("New summary") == true, "regenerated report applied to the wrong mail or language")
        let untouchedReport = try String(contentsOf: b, encoding: .utf8)
        try require(untouchedReport == "Original B", "regeneration modified another report")
        try require(restored.state(a.path).messages.count == 4, "report regeneration unexpectedly cleared conversation history")
        restored.draft("", for: b.path); restored.addFiles([attachment], for: b.path)
        await restored.send(b.path)
        try require(restored.state(b.path).messages.count == 2 && restored.state(b.path).messages.first?.content == "", "attachment-only question was rejected")
        return ["offline native report/chat state: new/current-language summaries, persistent multi-turn history, extra file attachments, compression notice, busy guard, failed-draft preservation and no cross-mail result mixing"]
    }
}

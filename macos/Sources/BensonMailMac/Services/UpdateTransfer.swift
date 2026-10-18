import Foundation
import CryptoKit

/// URLSession writes to disk; hashing and file moves stay on its serial delegate queue.
final class UpdateTransfer: NSObject, URLSessionDownloadDelegate, @unchecked Sendable {
    private let lock = NSLock()
    private var cancelled = false
    private var children: [UpdateTransfer] = []
    private var probes: [UpdateProbe] = []
    private let configuration: URLSessionConfiguration
    init(configuration: URLSessionConfiguration = .ephemeral) { self.configuration = configuration; super.init() }
    private var session: URLSession?
    private var task: URLSessionDownloadTask?
    private var continuation: CheckedContinuation<URL, Error>?
    private var result: Result<URL, Error>?
    private var destination: URL!
    private var expectedHash = ""
    private var expectedSize: Int64?
    private var progress: @Sendable (Int64, Int64) -> Void = { _, _ in }
    func run(url: URL, mirrors: [URL] = [], destination: URL, sha256: String, size: Int64?, progress: @escaping @Sendable (Int64, Int64) -> Void) async throws -> URL {
        guard ([url] + mirrors).allSatisfy(AppUpdater.secure), mirrors.count <= 3 else { throw TransferError.invalid("Download URL must use HTTPS") }
        if isCancelled { throw URLError(.cancelled) }
        if !mirrors.isEmpty {
            let sources = Array(NSOrderedSet(array: [url] + mirrors)) as! [URL]
            let measured = await withTaskGroup(of: (URL, Double)?.self) { group in
                for source in sources {
                    let probe = UpdateProbe(configuration: configuration)
                    register(probe)
                    group.addTask { await probe.measure(source) }
                }
                var results: [(URL, Double)] = []
                for await value in group { if let value { results.append(value) } }
                return results.sorted { $0.1 > $1.1 }.map { $0.0 }
            }
            if isCancelled { throw URLError(.cancelled) }
            let ordered = measured + sources.filter { !measured.contains($0) }
            var lastError: Error = URLError(.cannotConnectToHost)
            for source in ordered {
                if isCancelled { throw URLError(.cancelled) }
                let child = UpdateTransfer(configuration: configuration)
                register(child)
                try? FileManager.default.removeItem(at: destination.appendingPathExtension("part"))
                do { return try await child.run(url: source, destination: destination, sha256: sha256, size: size, progress: progress) }
                catch {
                    if isCancelled || (error as? URLError)?.code == .cancelled { throw URLError(.cancelled) }
                    if case TransferError.invalid = error { throw error }
                    lastError = error
                }
            }
            throw lastError
        }
        self.destination = destination; self.expectedHash = sha256; self.expectedSize = size; self.progress = progress
        configuration.timeoutIntervalForRequest = 60
        configuration.timeoutIntervalForResource = 3600
        let queue = OperationQueue(); queue.maxConcurrentOperationCount = 1
        let session = URLSession(configuration: configuration, delegate: self, delegateQueue: queue)
        self.session = session
        return try await withCheckedThrowingContinuation { continuation in
            self.continuation = continuation
            let task = session.downloadTask(with: url)
            lock.lock()
            self.task = task
            let stop = cancelled
            lock.unlock()
            if stop { task.cancel() }
            task.resume()
        }
    }
    private func register(_ child: UpdateTransfer) { lock.lock(); children.append(child); let stop = cancelled; lock.unlock(); if stop { child.cancel() } }
    private func register(_ probe: UpdateProbe) { lock.lock(); probes.append(probe); let stop = cancelled; lock.unlock(); if stop { probe.cancel() } }
    func cancel() {
        lock.lock(); cancelled = true; let current = task; let children = children; let probes = probes; lock.unlock()
        current?.cancel(); children.forEach { $0.cancel() }; probes.forEach { $0.cancel() }
    }
    private var isCancelled: Bool { lock.lock(); defer { lock.unlock() }; return cancelled }
    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest, completionHandler: @escaping (URLRequest?) -> Void) {
        completionHandler(request.url.map(AppUpdater.secure) == true ? request : nil)
    }
    func urlSession(_ session: URLSession, downloadTask: URLSessionDownloadTask, didWriteData bytesWritten: Int64,
                    totalBytesWritten: Int64, totalBytesExpectedToWrite: Int64) {
        progress(totalBytesWritten, expectedSize ?? totalBytesExpectedToWrite)
        let limit = expectedSize ?? 2_147_483_648
        if totalBytesWritten > limit || totalBytesExpectedToWrite > limit {
            result = .failure(TransferError.invalid("Download exceeds expected size or 2 GB safety limit"))
            downloadTask.cancel()
        }
    }
    func urlSession(_ session: URLSession, downloadTask: URLSessionDownloadTask, didFinishDownloadingTo location: URL) {
        do {
            guard let response = downloadTask.response as? HTTPURLResponse else { throw TransferError.invalid("Non-HTTP download response") }
            guard response.statusCode == 200 else { throw TransferError.transport("HTTP " + String(response.statusCode)) }
            guard response.url.map(AppUpdater.secure) == true else { throw TransferError.invalid("Download response URL must use HTTPS") }
            let partial = destination.appendingPathExtension("part")
            try? FileManager.default.removeItem(at: partial)
            try FileManager.default.moveItem(at: location, to: partial)
            do {
                if let expectedSize {
                    let actualSize = Int64(try partial.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? -1)
                    if actualSize < expectedSize { throw TransferError.transport("Incomplete download; trying another source") }
                    if actualSize > expectedSize { throw TransferError.invalid("Download exceeds expected size") }
                }
                try Self.verify(partial, sha256: expectedHash, size: expectedSize)
                if isCancelled { throw URLError(.cancelled) }
                try? FileManager.default.removeItem(at: destination)
                try FileManager.default.moveItem(at: partial, to: destination)
                result = .success(destination)
            } catch { try? FileManager.default.removeItem(at: partial); throw error }
        } catch { result = .failure(error) }
    }
    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        let value: Result<URL, Error>
        if isCancelled { value = .failure(URLError(.cancelled)) }
        else if let result, case .failure = result { value = result }
        else { value = error.map { .failure($0) } ?? result ?? .failure(TransferError.invalid("Download did not finish")) }
        continuation?.resume(with: value); continuation = nil
        session.finishTasksAndInvalidate()
        self.session = nil
        lock.lock(); self.task = nil; lock.unlock()
    }
    static func verify(_ file: URL, sha256: String, size: Int64?) throws {
        let values = try file.resourceValues(forKeys: [.fileSizeKey])
        if let size, Int64(values.fileSize ?? -1) != size { throw TransferError.invalid("Download size mismatch") }
        let handle = try FileHandle(forReadingFrom: file)
        defer { try? handle.close() }
        var hash = SHA256()
        while let data = try handle.read(upToCount: 1_048_576), !data.isEmpty { hash.update(data: data) }
        let digest = hash.finalize().map { String(format: "%02x", $0) }.joined()
        guard digest == sha256.lowercased() else { throw TransferError.invalid("SHA256 mismatch; installation blocked") }
    }
    enum TransferError: LocalizedError {
        case invalid(String), transport(String)
        var errorDescription: String? { switch self { case .invalid(let value), .transport(let value): return value } }
    }
}

/// Range is advisory: the data delegate also caps retained bytes when a server ignores it.
private final class UpdateProbe: NSObject, URLSessionDataDelegate, @unchecked Sendable {
    private let lock = NSLock()
    private let configuration: URLSessionConfiguration
    private var task: URLSessionDataTask?
    private var session: URLSession?
    private var cancelled = false
    private var continuation: CheckedContinuation<(URL, Double)?, Never>?
    private var bytes = 0
    private var usable = false
    private var start = Date()
    private var source: URL!
    private var deadline: DispatchWorkItem?
    init(configuration: URLSessionConfiguration) { self.configuration = configuration.copy() as! URLSessionConfiguration }
    func measure(_ url: URL) async -> (URL, Double)? {
        configuration.timeoutIntervalForRequest = 8; configuration.timeoutIntervalForResource = 8
        return await withCheckedContinuation { completion in
            lock.lock()
            if cancelled { lock.unlock(); completion.resume(returning: nil); return }
            continuation = completion; source = url; start = Date()
            let queue = OperationQueue(); queue.maxConcurrentOperationCount = 1
            let session = URLSession(configuration: configuration, delegate: self, delegateQueue: queue)
            self.session = session
            var request = URLRequest(url: url); request.setValue("bytes=0-262143", forHTTPHeaderField: "Range")
            request.setValue("identity", forHTTPHeaderField: "Accept-Encoding")
            let task = session.dataTask(with: request); self.task = task
            let deadline = DispatchWorkItem { [weak self] in self?.cancel() }; self.deadline = deadline
            DispatchQueue.global().asyncAfter(deadline: .now() + 8, execute: deadline)
            lock.unlock(); task.resume()
        }
    }
    func cancel() { lock.lock(); cancelled = true; let task = task; lock.unlock(); task?.cancel() }
    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse, newRequest request: URLRequest, completionHandler: @escaping (URLRequest?) -> Void) {
        completionHandler(request.url.map(AppUpdater.secure) == true ? request : nil)
    }
    func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive response: URLResponse, completionHandler: @escaping (URLSession.ResponseDisposition) -> Void) {
        usable = (response as? HTTPURLResponse).map { [200, 206].contains($0.statusCode) && $0.url.map(AppUpdater.secure) == true } ?? false
        completionHandler(usable ? .allow : .cancel)
    }
    func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive data: Data) {
        bytes += min(data.count, 262144 - bytes)
        if bytes >= 262144 { dataTask.cancel() }
    }
    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        deadline?.cancel()
        lock.lock(); let stopped = cancelled; let completion = continuation; continuation = nil; self.task = nil; lock.unlock()
        let success = !stopped && usable && bytes > 0 && (error == nil || bytes >= 262144)
        completion?.resume(returning: success ? (source, Double(bytes) / max(Date().timeIntervalSince(start), 0.000001)) : nil)
        session.finishTasksAndInvalidate(); self.session = nil
    }
}

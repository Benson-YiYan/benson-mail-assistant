import Foundation
import CryptoKit

/// URLSession writes to disk; hashing and file moves stay on its serial delegate queue.
final class UpdateTransfer: NSObject, URLSessionDownloadDelegate, @unchecked Sendable {
    private let lock = NSLock()
    private var cancelled = false
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
    func run(url: URL, destination: URL, sha256: String, size: Int64?, progress: @escaping @Sendable (Int64, Int64) -> Void) async throws -> URL {
        guard AppUpdater.secure(url) else { throw TransferError.invalid("Download URL must use HTTPS") }
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
    func cancel() { lock.lock(); cancelled = true; let current = task; lock.unlock(); current?.cancel() }
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
            guard response.statusCode == 200 else { throw TransferError.invalid("HTTP " + String(response.statusCode)) }
            guard response.url.map(AppUpdater.secure) == true else { throw TransferError.invalid("Download response URL must use HTTPS") }
            let partial = destination.appendingPathExtension("part")
            try? FileManager.default.removeItem(at: partial)
            try FileManager.default.moveItem(at: location, to: partial)
            do {
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
        case invalid(String)
        var errorDescription: String? { if case .invalid(let value) = self { return value }; return nil }
    }
}

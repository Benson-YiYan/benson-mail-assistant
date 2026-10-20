import AppKit
import Foundation
import PDFKit
import Vision

// A small signed helper using system frameworks. No network or external models.
func run() throws {
    guard CommandLine.arguments.count >= 2 else { throw NSError(domain: "MailOCR", code: 1) }
    let url = URL(fileURLWithPath: CommandLine.arguments[1])
    var image: CGImage?
    if CommandLine.arguments.count == 3, let number = Int(CommandLine.arguments[2]) {
        guard let document = PDFDocument(url: url), !document.isLocked,
              number >= 1, number <= document.pageCount, let page = document.page(at: number - 1) else {
            throw NSError(domain: "MailOCR", code: 2)
        }
        let bounds = page.bounds(for: .mediaBox)
        guard bounds.width > 0, bounds.height > 0 else { throw NSError(domain: "MailOCR", code: 3) }
        let scale = min(2400 / max(bounds.width, bounds.height), 3)
        let thumbnail = page.thumbnail(of: NSSize(width: bounds.width * scale, height: bounds.height * scale), for: .mediaBox)
        image = thumbnail.cgImage(forProposedRect: nil, context: nil, hints: nil)
    } else {
        guard let source = CGImageSourceCreateWithURL(url as CFURL, nil) else { throw NSError(domain: "MailOCR", code: 4) }
        image = CGImageSourceCreateThumbnailAtIndex(source, 0, [kCGImageSourceCreateThumbnailFromImageAlways: true, kCGImageSourceThumbnailMaxPixelSize: 3000] as CFDictionary)
    }
    guard let image else { throw NSError(domain: "MailOCR", code: 5) }
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = true
    request.recognitionLanguages = ["en-US", "es-ES", "zh-Hans"]
    try VNImageRequestHandler(cgImage: image).perform([request])
    let text = (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }.joined(separator: "\n")
    FileHandle.standardOutput.write(Data(text.prefix(100000).utf8))
}
do { try run() } catch { exit(1) }

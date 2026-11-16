import SwiftUI
import WebKit
import CryptoKit
private typealias MarkdownState<Value> = SwiftUI.State<Value>

/// A local-only Markdown document. Raw HTML is escaped and remote resources are blocked.
enum MarkdownDocument {
    private static let renderedCache: NSCache<NSString, NSString> = {
        let cache = NSCache<NSString, NSString>()
        cache.countLimit = 32
        cache.totalCostLimit = 4 * 1024 * 1024
        return cache
    }()

    static func render(_ markdown: String) throws -> String {
        let key = SHA256.hash(data: Data(markdown.utf8)).map { String(format: "%02x", $0) }.joined() as NSString
        if let cached = renderedCache.object(forKey: key) { return cached as String }
        let process = Process(), input = Pipe(), output = Pipe()
        process.executableURL = ServiceInstaller.worker
        process.arguments = ["--render-markdown"]
        process.standardInput = input; process.standardOutput = output; process.standardError = FileHandle.nullDevice
        try process.run()
        try input.fileHandleForWriting.write(contentsOf: Data(markdown.utf8))
        try input.fileHandleForWriting.close()
        let bytes = output.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        guard process.terminationStatus == 0, let fragment = String(data: bytes, encoding: .utf8) else {
            throw NSError(domain: "BensonMail.Markdown", code: 1, userInfo: [NSLocalizedDescriptionKey: "Markdown 排版失败，原文仍可复制或打开。"])
        }
        let rendered = html(fragment)
        renderedCache.setObject(rendered as NSString, forKey: key, cost: rendered.utf8.count)
        return rendered
    }
    static func html(_ fragment: String) -> String {
        """
        <!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
        <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
        <style>:root{color-scheme:light dark}body{font:14px -apple-system,BlinkMacSystemFont,sans-serif;line-height:1.65;margin:0 8px 24px 0;overflow-wrap:anywhere;color:CanvasText;background:Canvas}h1,h2,h3,h4{line-height:1.35;margin:1.3em 0 .6em}h1{font-size:24px}h2{font-size:20px}h3{font-size:17px}p{margin:.7em 0}li{margin:.25em 0}blockquote{margin:.7em 0;padding:6px 12px;border-left:3px solid #888;background:color-mix(in srgb,CanvasText 5%,Canvas)}pre{padding:12px;white-space:pre-wrap;background:color-mix(in srgb,CanvasText 7%,Canvas);border-radius:7px}code{font-family:ui-monospace,monospace;font-size:.92em}table{border-collapse:collapse;width:100%}td,th{border:1px solid #8886;padding:7px;text-align:left}th{background:color-mix(in srgb,CanvasText 7%,Canvas)}a{color:LinkText}hr{border:0;border-top:1px solid #8886}</style></head><body>\(fragment)</body></html>
        """
    }
}

struct MarkdownReportView: View {
    @ObservedObject private var language = AppLanguage.shared
    let text: String
    @MarkdownState private var html = ""
    @MarkdownState private var error = ""
    var body: some View {
        // Keep the native renderer mounted through loading and errors. Changing a
        // transparent Group's child inside VSplitView can recreate the split item,
        // restart this task and endlessly alternate between loading and content.
        ZStack(alignment: .topLeading) {
            NativeMarkdownView(html: html)
                .opacity(html.isEmpty ? 0 : 1)
                .allowsHitTesting(!html.isEmpty)
                .accessibilityHidden(html.isEmpty)
            if !error.isEmpty {
                ScrollView { VStack(alignment: .leading) { Text(T(error)).foregroundStyle(.secondary); Text(text).textSelection(.enabled) } }
            } else if html.isEmpty { ProgressView() }
        }.frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading).task(id: text) {
            html = ""; error = ""
            do {
                let rendered = try await Task.detached { try MarkdownDocument.render(text) }.value
                guard !Task.isCancelled else { return }
                html = rendered
            } catch { if !Task.isCancelled { self.error = error.localizedDescription } }
        }
    }
}

struct ChatMarkdownView: View {
    let text: String
    @MarkdownState private var html = ""
    @MarkdownState private var error = ""
    @MarkdownState private var contentHeight: CGFloat = 48

    var body: some View {
        Group {
            if error.isEmpty {
                NativeMarkdownView(html: html) { measuredHeight in
                    guard abs(contentHeight - measuredHeight) > 1 else { return }
                    contentHeight = measuredHeight
                }
                .frame(maxWidth: .infinity)
                .frame(height: contentHeight)
            } else {
                Text(text).textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .task(id: text) {
            html = ""; error = ""
            contentHeight = 48
            do {
                let rendered = try await Task.detached { try MarkdownDocument.render(text) }.value
                guard !Task.isCancelled else { return }
                html = rendered
            } catch {
                guard !Task.isCancelled else { return }
                self.error = error.localizedDescription
            }
        }
    }
}

private final class ContentSizedMarkdownWebView: WKWebView {
    var widthDidChange: (() -> Void)?

    override func setFrameSize(_ newSize: NSSize) {
        let widthChanged = abs(frame.width - newSize.width) > 1
        super.setFrameSize(newSize)
        if widthChanged { widthDidChange?() }
    }
}

struct NativeMarkdownView: NSViewRepresentable {
    let html: String
    var onContentHeightChange: ((CGFloat) -> Void)? = nil
    func makeCoordinator() -> Coordinator { Coordinator() }
    func makeNSView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.websiteDataStore = .nonPersistent()
        config.defaultWebpagePreferences.allowsContentJavaScript = false
        let view = ContentSizedMarkdownWebView(frame: .zero, configuration: config)
        view.navigationDelegate = context.coordinator
        view.setValue(false, forKey: "drawsBackground")
        view.widthDidChange = { [weak coordinator = context.coordinator, weak view] in
            guard let coordinator, let view else { return }
            DispatchQueue.main.async { coordinator.measureContentHeight(in: view, forWidth: view.bounds.width) }
        }
        return view
    }
    func updateNSView(_ view: WKWebView, context: Context) {
        context.coordinator.onContentHeightChange = onContentHeightChange
        guard !html.isEmpty else { return }
        guard context.coordinator.previous != html else {
            context.coordinator.measureContentHeight(in: view, forWidth: view.bounds.width)
            return
        }
        context.coordinator.previous = html
        context.coordinator.finished = false
        context.coordinator.loadCount += 1
        view.loadHTMLString(html, baseURL: nil)
    }
    final class Coordinator: NSObject, WKNavigationDelegate {
        var previous: String?
        var finished = false
        var loadCount = 0
        var failure = ""
        var onContentHeightChange: ((CGFloat) -> Void)?
        var measuredContentHeight: CGFloat = 0
        var measuredWidth: CGFloat = 0
        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            finished = true
            measureContentHeight(in: webView, forWidth: webView.bounds.width, force: true)
        }
        func measureContentHeight(in webView: WKWebView, forWidth width: CGFloat, force: Bool = false) {
            guard onContentHeightChange != nil else { return }
            guard width > 1, force || abs(measuredWidth - width) > 1 else { return }
            measuredWidth = width
            webView.evaluateJavaScript("Math.ceil(document.documentElement.scrollHeight)") { [weak self] value, _ in
                guard let self, let number = value as? NSNumber else { return }
                let height = max(48, CGFloat(number.doubleValue) + 4)
                DispatchQueue.main.async {
                    self.measuredContentHeight = height
                    self.onContentHeightChange?(height)
                }
            }
        }
        func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) { failure = error.localizedDescription }
        func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) { failure = error.localizedDescription }
        func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            if navigationAction.navigationType == .linkActivated {
                if let url = navigationAction.request.url, ["https", "http", "mailto"].contains(url.scheme?.lowercased() ?? "") { NSWorkspace.shared.open(url) }
                decisionHandler(.cancel)
            } else { decisionHandler(navigationAction.request.url?.scheme == "about" ? .allow : .cancel) }
        }
    }
}

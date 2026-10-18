import SwiftUI
import WebKit
private typealias MarkdownState<Value> = SwiftUI.State<Value>

/// A local-only Markdown document. Raw HTML is escaped and remote resources are blocked.
enum MarkdownDocument {
    static func render(_ markdown: String) throws -> String {
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
            throw NSError(domain: "BensonMail.Markdown", code: 1, userInfo: [NSLocalizedDescriptionKey: T("Markdown 排版失败，原文仍可复制或打开。")])
        }
        return html(fragment)
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
    let text: String
    @MarkdownState private var html = ""
    @MarkdownState private var error = ""
    var body: some View {
        Group {
            if !html.isEmpty { NativeMarkdownView(html: html) }
            else if !error.isEmpty { ScrollView { VStack(alignment: .leading) { Text(error).foregroundStyle(.secondary); Text(text).textSelection(.enabled) } } }
            else { ProgressView() }
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

struct NativeMarkdownView: NSViewRepresentable {
    let html: String
    func makeCoordinator() -> Coordinator { Coordinator() }
    func makeNSView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.websiteDataStore = .nonPersistent()
        config.defaultWebpagePreferences.allowsContentJavaScript = false
        let view = WKWebView(frame: .zero, configuration: config)
        view.navigationDelegate = context.coordinator
        view.setValue(false, forKey: "drawsBackground")
        return view
    }
    func updateNSView(_ view: WKWebView, context: Context) {
        guard context.coordinator.previous != html else { return }
        context.coordinator.previous = html
        context.coordinator.finished = false
        view.loadHTMLString(html, baseURL: nil)
    }
    final class Coordinator: NSObject, WKNavigationDelegate {
        var previous: String?
        var finished = false
        var failure = ""
        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) { finished = true }
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

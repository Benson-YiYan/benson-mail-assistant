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

/// One native scroll surface for the entire conversation, including streamed replies.
struct ConversationTranscriptView: View {
    @ObservedObject private var language = AppLanguage.shared
    let messages: [ReportChatMessage]
    let question: String
    let partial: String
    var pending = false
    var files: [String] = []
    @MarkdownState private var html = ""
    private var revision: String {
        messages.map { $0.role + "\n" + $0.content + "\n" + $0.files.joined(separator: "\n") }.joined(separator: "\n\n") + question + partial + String(pending) + files.joined() + language.code
    }
    var body: some View {
        NativeMarkdownView(html: html, preservesScrollPosition: true)
            .task(id: revision) {
                do {
                    // Coalesce incoming chunks; completed messages reuse the bounded render cache.
                    try Task.checkCancellation()
                    let rows = messages.map { ($0.role, $0.content, $0.files) } +
                        (!pending && question.isEmpty && partial.isEmpty ? [] : [("user", question, files), ("assistant", partial, [])])
                    let userLabel = Self.escape(T("你")), assistantLabel = Self.escape(T("AI 助手"))
                    let welcome = Self.escape(T("可以针对这封邮件和附件继续提问，也可以添加文件。对话会自动保存。"))
                    let rendered = try await Task.detached {
                        var fragments: [String] = []
                        for (role, content, files) in rows {
                            let label = role == "user" ? userLabel : assistantLabel
                            let body: String
                            if role == "user" {
                                body = "<p style=\"white-space:pre-wrap\">" + Self.escape(content) + "</p>"
                            } else {
                                let document = try MarkdownDocument.render(content)
                                body = document.components(separatedBy: "<body>").last?.components(separatedBy: "</body>").first ?? Self.escape(content)
                            }
                            fragments.append("<section" + (role == "user" ? " class=\"user-message\"" : "") + "><strong>" + label + "</strong>" + body +
                                files.map { "<p>" + Self.escape(URL(fileURLWithPath: $0).lastPathComponent) + "</p>" }.joined() + "</section><hr>")
                        }
                        let style = "<style>.user-message{background:rgba(0,122,255,.10);border-radius:8px;padding:10px;margin:8px 0}@media(prefers-color-scheme:dark){.user-message{background:rgba(0,122,255,.16)}}</style>"
                        return MarkdownDocument.html(style + (fragments.isEmpty ? "<p>" + welcome + "</p>" : fragments.joined()))
                    }.value
                    guard !Task.isCancelled else { return }
                    html = rendered
                } catch is CancellationError {} catch {
                    if !Task.isCancelled { html = MarkdownDocument.html("<pre>" + Self.escape(revision) + "</pre>") }
                }
            }
    }
    private static func escape(_ text: String) -> String {
        text.replacingOccurrences(of: "&", with: "&amp;").replacingOccurrences(of: "<", with: "&lt;").replacingOccurrences(of: ">", with: "&gt;")
    }
}

struct NativeMarkdownView: NSViewRepresentable {
    let html: String
    var preservesScrollPosition = false
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
        guard !html.isEmpty else { return }
        guard context.coordinator.previous != html else { return }
        context.coordinator.previous = html
        context.coordinator.finished = false
        context.coordinator.loadCount += 1
        if preservesScrollPosition, context.coordinator.loadCount > 1 {
            let coordinator = context.coordinator
            let expected = html
            view.evaluateJavaScript("({y:window.scrollY,bottom:window.scrollY+window.innerHeight>=document.documentElement.scrollHeight-30})") { value, _ in
                guard coordinator.previous == expected else { return }
                let position = value as? [String: Any]
                coordinator.savedScrollY = (position?["y"] as? NSNumber)?.doubleValue ?? 0
                coordinator.followBottom = position?["bottom"] as? Bool ?? true
                view.loadHTMLString(expected, baseURL: nil)
            }
        } else {
            context.coordinator.followBottom = preservesScrollPosition
            view.loadHTMLString(html, baseURL: nil)
        }
    }
    final class Coordinator: NSObject, WKNavigationDelegate {
        var previous: String?
        var finished = false
        var loadCount = 0
        var failure = ""
        var savedScrollY: Double = 0
        var followBottom = false
        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            finished = true
            if followBottom || savedScrollY > 0 {
                let target = followBottom ? "document.documentElement.scrollHeight" : String(savedScrollY)
                webView.evaluateJavaScript("window.scrollTo(0," + target + ")", completionHandler: nil)
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

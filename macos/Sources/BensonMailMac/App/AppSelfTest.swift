import AppKit
import SwiftUI
import WebKit

@MainActor
enum AppSelfTest {
    static func run(attempt: Int = 0) async {
        let args = CommandLine.arguments
        guard let index = args.firstIndex(of: "--self-test"), args.indices.contains(index + 1) else { return }
        let output = URL(fileURLWithPath: args[index + 1])
        var checks: [String] = []
        do {
            let store = MailStore.shared
            guard store.isTest, store.base.path.contains("BensonMail-UI-test") else { throw Failure("isolated fixture required") }
            if store.reports.count < 2 && attempt < 30 {
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { Task { await run(attempt: attempt + 1) } }
                return
            }
            guard store.reports.count == 2, store.alive else {
                throw Failure("fixture report/status failed: count=\(store.reports.count), preview=\(store.reportText.contains("建议回复")), alive=\(store.alive)")
            }
            if args.contains("--policy-self-test-only") {
                checks += try await SenderPolicySelfTest.run(store: store, output: output)
                let result: [String: Any] = ["ok": true, "checks": checks]
                try JSONSerialization.data(withJSONObject: result, options: [.prettyPrinted, .sortedKeys])
                    .write(to: output.appendingPathComponent("result.json"))
                NSApp.terminate(nil)
                return
            }
            store.select(store.reports[0])
            guard store.reportText.contains("建议回复") else {
                throw Failure("fixture preview failed: title=\(store.reports[0].title), length=\(store.reports[0].text.count)")
            }
            checks.append("synthetic report listing, six-section preview, live heartbeat")
            let notice = MailNotice(id: "fixture-notice", title: "模拟新邮件", body: "模拟发件人及摘要",
                                    created: Date().timeIntervalSince1970, report: store.reports[0].url.path)
            let notification = MailNotifications.content(notice)
            guard notification.title == notice.title, notification.body == notice.body,
                  notification.userInfo["reportPath"] as? String == notice.report else {
                throw Failure("native notification content or report routing failed")
            }
            if let window = NSApp.windows.first(where: { $0.title == "邮件小秘书" && $0.canBecomeMain }) {
                window.orderOut(nil)
                MailNotifications.shared.openWindow()
                RunLoop.current.run(until: Date().addingTimeInterval(0.2))
                guard NSApp.windows.contains(where: { $0.title == "邮件小秘书" && $0.isVisible }) else {
                    throw Failure("notification click did not restore main window")
                }
            } else { throw Failure("main window missing for notification routing test") }
            checks.append("native app notification content and click-to-restore main window; no AppleScript, no real notification in fixture test")
            guard let first = store.reports.first else { throw Failure("fixture mail missing") }
            guard first.title == "原始主题-12-34", first.receivedLabel.contains("2026-10-15 09:02"), first.url.lastPathComponent == "模拟来信：合同审阅-09-02.md" else { throw Failure("subject/time separation or original filename failed") }
            let fallback = store.reports[1]
            guard fallback.title == "另一封模拟邮件", fallback.receivedLabel.contains("2026-10-14 10:00") else { throw Failure("legacy filename display fallback failed") }
            checks.append("original subject and separate Beijing receipt time; legacy fallback; Markdown and legacy TXT listed together; report filename preserved")
            let markdown = """
            ## 1. Report heading
            **Strong text**

            3. First action
               - Nested action
            4. Second action

            [Website](https://example.invalid)

            | Name | Value |
            | --- | --- |
            | Fee | 100 |

            ```text
            literal **code**
            ```
            <script>window.untrusted=true</script>
            ![remote](https://example.invalid/tracker.png)
            """
            let markdownHost = NSHostingView(rootView: MarkdownReportView(text: markdown))
            markdownHost.frame = NSRect(x: 0, y: 0, width: 600, height: 700)
            markdownHost.autoresizingMask = [.width, .height]
            let renderWindow = NSWindow(contentRect: NSRect(x: 120,y: 120,width: 600,height: 700),styleMask: [.titled,.closable],backing: .buffered,defer: false)
            renderWindow.title = "Markdown fixture"
            renderWindow.contentView = markdownHost
            renderWindow.setContentSize(NSSize(width: 600, height: 700))
            renderWindow.makeKeyAndOrderFront(nil)
            defer { renderWindow.orderOut(nil) }
            let renderedHTML = try MarkdownDocument.render(markdown)
            let loadingDeadline = Date().addingTimeInterval(8)
            func webView(in view: NSView) -> WKWebView? {
                if let web = view as? WKWebView { return web }
                for child in view.subviews { if let web = webView(in: child) { return web } }
                return nil
            }
            while webView(in: markdownHost) == nil && Date() < loadingDeadline { try await Task.sleep(nanoseconds: 50_000_000) }
            guard let rendered = webView(in: markdownHost), !rendered.configuration.defaultWebpagePreferences.allowsContentJavaScript else {
                throw Failure("production Markdown view did not create its protected native renderer")
            }
            guard let renderCoordinator = rendered.navigationDelegate as? NativeMarkdownView.Coordinator else { throw Failure("production Markdown navigation policy missing") }
            while !renderCoordinator.finished && Date() < loadingDeadline { try await Task.sleep(nanoseconds: 50_000_000) }
            guard renderCoordinator.finished else { throw Failure("production Markdown navigation did not finish: \(renderCoordinator.failure), \(rendered.url?.absoluteString ?? "no URL")") }
            try await Task.sleep(nanoseconds: 300_000_000)
            let snapshot = try await rendered.takeSnapshot(configuration: nil)
            guard let tiff = snapshot.tiffRepresentation, let bitmap = NSBitmapImageRep(data: tiff),
                  let png = bitmap.representation(using: .png, properties: [:]) else {
                throw Failure("actual WebKit Markdown snapshot missing or empty")
            }
            try png.write(to: output.appendingPathComponent("markdown-preview.png"))
            guard png.count > 20000, snapshot.size.width >= 500, snapshot.size.height >= 600 else {
                throw Failure("production Markdown preview blank: size=\(snapshot.size), bytes=\(png.count), frame=\(rendered.frame)")
            }
            guard renderedHTML.contains("<h2>1. Report heading</h2>"), renderedHTML.contains("<strong>Strong text</strong>"),
                  renderedHTML.contains("<ol start=\"3\">"), renderedHTML.contains("<ul>\n<li>Nested action</li>"),
                  renderedHTML.contains("<td>100</td>"), renderedHTML.contains("literal **code**"),
                  !renderedHTML.contains("<script>"), !renderedHTML.contains("<img") else {
                throw Failure("CommonMark document structure failed before native snapshot")
            }
            checks.append("actual WebKit renders Markdown headings, bold, lists, links, tables and fenced code; HTML escaped and remote images absent")
            // Exercise the renderer inside the real report/chat split, not only its standalone host.
            guard let reportWindow = NSApp.windows.first(where: { $0.title == "邮件小秘书" && $0.canBecomeMain }),
                  let integratedRoot = reportWindow.contentView else { throw Failure("integrated report window missing") }
            store.workspacePage = .reports
            store.select(first)
            reportWindow.makeKeyAndOrderFront(nil)
            let reportDeadline = Date().addingTimeInterval(8)
            while (webView(in: integratedRoot)?.navigationDelegate as? NativeMarkdownView.Coordinator)?.finished != true && Date() < reportDeadline {
                try await Task.sleep(nanoseconds: 50_000_000)
            }
            guard let integratedWeb = webView(in: integratedRoot),
                  let integratedCoordinator = integratedWeb.navigationDelegate as? NativeMarkdownView.Coordinator,
                  integratedCoordinator.finished else { throw Failure("report/chat split never finished Markdown navigation") }
            let integratedHTML = integratedCoordinator.previous
            let initialLoads = integratedCoordinator.loadCount
            guard integratedHTML?.contains("合同审阅") == true else { throw Failure("integrated Markdown did not show selected report") }
            for page in [WorkspacePage.ai, .reports, .general, .reports] {
                store.workspacePage = page
                reportWindow.setContentSize(NSSize(width: page == .reports ? 1160 : 1120, height: 790))
                store.reconcileSelection()
                store.reportConversation.draft("integrated layout fixture", for: first.id)
                try await Task.sleep(nanoseconds: 150_000_000)
                guard webView(in: integratedRoot) === integratedWeb,
                      integratedCoordinator.finished, integratedCoordinator.previous == integratedHTML,
                      integratedCoordinator.loadCount == initialLoads else {
                    throw Failure("report/chat split recreated or reloaded unchanged Markdown during layout/navigation")
                }
            }
            func reportDescendants(_ view: NSView) -> [NSView] { [view] + view.subviews.flatMap { reportDescendants($0) } }
            guard let divider = reportDescendants(integratedRoot).compactMap({ $0 as? NSSplitView })
                .first(where: { !$0.isVertical && $0.arrangedSubviews.count == 2 && webView(in: $0.arrangedSubviews[0]) != nil }) else {
                throw Failure("report/chat native draggable divider missing")
            }
            let topPane = divider.arrangedSubviews[0], bottomPane = divider.arrangedSubviews[1]
            let beforeDrag = topPane.frame.height
            let dividerY = topPane.frame.minY < bottomPane.frame.minY
                ? (topPane.frame.maxY + bottomPane.frame.minY) / 2
                : (bottomPane.frame.maxY + topPane.frame.minY) / 2
            let dragStart = divider.convert(NSPoint(x: divider.bounds.midX, y: dividerY), to: nil)
            let dragEnd = NSPoint(x: dragStart.x, y: dragStart.y + 55)
            NSApp.activate(ignoringOtherApps: true)
            for (kind, point) in [(NSEvent.EventType.leftMouseDown, dragStart), (.leftMouseDragged, dragEnd), (.leftMouseUp, dragEnd)] {
                guard let event = NSEvent.mouseEvent(with: kind, location: point, modifierFlags: [],
                    timestamp: ProcessInfo.processInfo.systemUptime, windowNumber: reportWindow.windowNumber,
                    context: nil, eventNumber: 0, clickCount: 1, pressure: kind == .leftMouseUp ? 0 : 1) else { throw Failure("divider drag event missing") }
                NSApp.postEvent(event, atStart: false)
            }
            try await Task.sleep(nanoseconds: 350_000_000)
            guard abs(topPane.frame.height - beforeDrag) >= 20,
                  webView(in: integratedRoot) === integratedWeb, integratedCoordinator.loadCount == initialLoads else {
                throw Failure("dragging report/chat divider did not resize both panes or reloaded Markdown")
            }
            checks.append("actual native mouse drag resizes the report/chat divider while preserving the mounted Markdown renderer")
            store.reportConversation.draft("", for: first.id)
            let originalReportSource = store.reportText
            store.reportText = "# Outdated fixture report"
            try await Task.sleep(nanoseconds: 10_000_000)
            store.reportText = "# Current fixture report\n\n**Newest report body**"
            let changedDeadline = Date().addingTimeInterval(8)
            while (integratedCoordinator.previous?.contains("Newest report body") != true || !integratedCoordinator.finished) && Date() < changedDeadline {
                try await Task.sleep(nanoseconds: 50_000_000)
            }
            guard webView(in: integratedRoot) === integratedWeb, integratedCoordinator.finished,
                  integratedCoordinator.previous?.contains("<strong>Newest report body</strong>") == true,
                  integratedCoordinator.previous?.contains("Outdated fixture report") == false else {
                throw Failure("changed report content was stale or replaced its native renderer")
            }
            store.reportText = originalReportSource
            let restoredDeadline = Date().addingTimeInterval(8)
            while (integratedCoordinator.previous != integratedHTML || !integratedCoordinator.finished) && Date() < restoredDeadline {
                try await Task.sleep(nanoseconds: 50_000_000)
            }
            guard integratedCoordinator.previous == integratedHTML, integratedCoordinator.finished else { throw Failure("restoring selected report failed") }
            try capture(reportWindow, to: output.appendingPathComponent("integrated-report-chat-markdown.png"))
            checks.append("actual main report/chat split finishes Markdown and retains one WKWebView without reloads through page changes, resizing, rescans and chat drafts; rapid text changes show only the newest report and restore correctly")
            let networkDiagnostic = "AI 接口DNS 解析失败，请检查域名和 DNS 设置。\n具体原因：gaierror: synthetic failure"
            for (code, expected) in [("en", "DNS lookup failed"), ("es", "Falló la consulta DNS")] {
                AppLanguage.shared.select(code)
                let translated = T(networkDiagnostic)
                guard translated.contains(expected), translated.contains("gaierror: synthetic failure"),
                      !translated.contains("DNS 解析失败") else { throw Failure("AI network diagnostic hint was not localized: " + code) }
            }
            AppLanguage.shared.select("zh")
            checks.append("English and Spanish AI network diagnostics translate the hint and preserve the safe technical detail")
            if args.contains("--markdown-self-test-only") {
                let result: [String: Any] = ["ok": true, "checks": checks]
                try JSONSerialization.data(withJSONObject: result, options: [.prettyPrinted, .sortedKeys])
                    .write(to: output.appendingPathComponent("result.json"))
                NSApp.terminate(nil)
                return
            }
            var filter = ReportFilter()
            for query in ["zebra", "demo@example.invalid", "付款明细专用.xlsx"] {
                filter.query = query
                guard store.reports.filter({ filter.matches($0) }).map(\.id) == [first.id] else { throw Failure("search failed: " + query) }
            }
            filter.query = ""; filter.fromDay = "2026-10-15"; filter.toDay = "2026-10-15"
            filter.sender = "demo"; filter.attachments = .withAttachments
            guard store.reports.filter({ filter.matches($0) }).map(\.id) == [first.id] else { throw Failure("combined filters failed") }
            filter.attachments = .withoutAttachments
            guard store.reports.filter({ filter.matches($0) }).isEmpty else { throw Failure("attachment filter failed") }
            filter = ReportFilter(); filter.attachments = .withoutAttachments
            guard store.reports.filter({ filter.matches($0) }).count == 1 else { throw Failure("no-attachment filter failed") }
            filter.attachments = .all; filter.query = "not-found-unique"
            guard store.reports.filter({ filter.matches($0) }).isEmpty else { throw Failure("empty result failed") }
            store.filter = filter; store.reconcileSelection()
            guard store.selected == nil else { throw Failure("stale report remained visible") }
            store.resetFilters()
            guard store.filteredReports.count == 2, store.selected?.id == first.id else { throw Failure("reset filters failed") }
            checks.append("body-only, sender and attachment-name search; inclusive dates and sender/attachment combinations; no-attachment, empty result and reset")
            store.toggle()
            guard !store.settings.enabled, store.statusTitle.contains("暂停") else { throw Failure("pause failed") }
            store.refresh()
            guard !store.settings.enabled else { throw Failure("pause did not persist") }
            store.toggle(); store.checkNow()
            guard store.settings.enabled, FileManager.default.fileExists(atPath: store.data.appendingPathComponent("check.request").path) else { throw Failure("resume or check request failed") }
            guard store.checkRequested, !store.checkFeedback.isEmpty else { throw Failure("manual check feedback missing") }
            let requestURL = store.data.appendingPathComponent("check.request")
            let requestedAt = try requestURL.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate
            store.checkNow()
            guard try requestURL.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate == requestedAt else { throw Failure("duplicate request not suppressed") }
            let statusURL = store.data.appendingPathComponent("service.json")
            var fixtureStatus = try JSONSerialization.jsonObject(with: Data(contentsOf: statusURL)) as! [String: Any]
            fixtureStatus["last_check"] = ISO8601DateFormatter().string(from: Date().addingTimeInterval(1))
            fixtureStatus["phase"] = "idle"
            try JSONSerialization.data(withJSONObject: fixtureStatus).write(to: statusURL, options: .atomic)
            store.refresh()
            guard !store.checkRequested, store.checkFeedback.contains("检查完成") else { throw Failure("manual check completion missing") }
            checks.append("single click feedback, duplicate request suppression and completion acknowledgement")
            checks.append("persisted pause/resume and manual check request without AI or launchctl")
            store.setInterval("25"); store.refresh()
            guard store.settings.interval_seconds == 25 else { throw Failure("custom interval persistence failed") }
            store.setInterval("0")
            guard store.settings.interval_seconds == 25, store.problem != nil else { throw Failure("invalid interval accepted") }
            store.problem = nil; store.setInterval("60")
            checks.append("custom interval persists; invalid interval rejected; migration from existing settings")
            guard store.settings.ai_provider == "codex", MailSettings().ai_provider == "api" else { throw Failure("AI provider migration/default failed") }
            guard try MailCredentials.apiEndpoint("https://example.invalid/v1/") == "https://example.invalid/v1/chat/completions" else { throw Failure("API endpoint normalization failed") }
            do {
                _ = try MailCredentials.apiEndpoint("http://remote.invalid/v1")
                throw Failure("insecure remote API address accepted")
            } catch is MailCredentials.Failure {}
            try store.saveAI(provider: "codex", base: "https://example.invalid/v1", model: "fixture-model", key: "")
            store.refresh()
            guard store.settings.api_model == "fixture-model" else { throw Failure("AI configuration did not persist") }
            let encoded = String(data: try Data(contentsOf: store.settingsURL), encoding: .utf8) ?? ""
            guard !encoded.contains("api_key") else { throw Failure("API key stored in ordinary settings") }
            checks.append("API configuration persistence, HTTPS validation, fresh API default and legacy Codex migration; no plaintext key")
            guard MailPreset.all.count >= 10, MailPreset.all.contains(where: { $0.id == "custom" }),
                  MailPreset.all.first(where: { $0.id == "qq" })?.host == "imap.qq.com" else {
                throw Failure("mailbox presets missing from standalone bundle")
            }
            var connection = MailConnection()
            connection.account = "demo@example.invalid"; connection.host = "imap.example.invalid"
            connection.port = 1993; connection.security = "starttls"; connection.username = "login-user"
            connection.mail_folder = "Archive"; connection.mail_auth = "oauth2"; connection.mail_provider = "custom"
            connection = try connection.validated()
            guard connection.identity == "7c0447c91e4fa209f9a4a9cd5f4227df6a6a6b486906f780e32039e5f44f67f1" else {
                throw Failure("Swift and Python mailbox identities differ")
            }
            let legacyMailbox = try JSONSerialization.jsonObject(with: JSONEncoder().encode(connection)) as! [String: Any]
            let withoutProxy = legacyMailbox.filter { !$0.key.hasPrefix("proxy_") }
            let migrated = try JSONDecoder().decode(MailConnection.self, from: JSONSerialization.data(withJSONObject: withoutProxy))
            guard migrated.proxy_mode == "direct", migrated.identity == connection.identity else {
                throw Failure("legacy mailbox proxy migration changed identity or default routing")
            }
            for mode in ["direct", "system", "http", "socks5"] {
                var proxied = connection
                proxied.proxy_mode = mode; proxied.proxy_host = "127.0.0.1"; proxied.proxy_port = 10808
                let validated = try proxied.validated()
                let roundtrip = try JSONDecoder().decode(MailConnection.self, from: JSONEncoder().encode(validated))
                guard roundtrip == validated, validated.identity == connection.identity else {
                    throw Failure("mailbox proxy failed persistence or changed mail progress identity")
                }
            }
            var invalidProxy = connection
            invalidProxy.proxy_mode = "socks5"; invalidProxy.proxy_port = 0
            do { _ = try invalidProxy.validated(); throw Failure("invalid proxy port accepted") }
            catch is MailCredentials.Failure {}
            invalidProxy.proxy_port = 10808; invalidProxy.proxy_host = "http://127.0.0.1"
            do { _ = try invalidProxy.validated(); throw Failure("proxy URL accepted as host") }
            catch is MailCredentials.Failure {}
            invalidProxy.proxy_mode = "direct"
            _ = try invalidProxy.validated() // Disabled manual fields must not invalidate direct connections.
            checks.append("legacy proxy defaults, all routing modes persist without changing mail progress identity, and manual proxy validation")
            let previousIdentity = connection.identity
            connection.mail_folder = "INBOX"
            guard previousIdentity != connection.identity else { throw Failure("folders share progress identity") }
            store.settings.mailbox = connection; try store.save(); store.refresh()
            guard store.settings.mailbox?.port == 1993, store.settings.mailbox?.username == "login-user",
                  store.settings.mailbox?.security == "starttls", store.settings.mailbox?.mail_auth == "oauth2" else {
                throw Failure("custom mailbox configuration did not persist")
            }
            checks.append("bundled common/custom mailbox presets; custom TLS port username folder and OAuth2 persistence; shared identity format")
            var secondConnection = connection
            secondConnection.account = "second@example.invalid"
            secondConnection.host = "imap.second.invalid"
            secondConnection.proxy_mode = "socks5"; secondConnection.proxy_host = "127.0.0.1"; secondConnection.proxy_port = 10999
            store.settings.mailboxes = [MailboxProfile(connection: connection), MailboxProfile(connection: secondConnection)]
            try store.save(); store.refresh()
            guard store.mailboxProfiles.count == 2 else { throw Failure("multiple accounts not persisted") }
            store.selectMailbox(secondConnection.identity)
            store.setMailboxEnabled(connection.identity, enabled: false)
            store.refresh()
            guard store.mailAccount == secondConnection.account,
                  store.mailboxProfiles.first?.enabled == false,
                  store.mailboxProfiles.last?.enabled == true,
                  store.settings.mailbox?.proxy_mode == "socks5", store.settings.mailbox?.proxy_port == 10999,
                  store.mailboxProfiles.first?.connection.proxy_mode == "direct" else { throw Failure("per-account selection, proxy or pause mixed accounts") }
            checks.append("multiple mailbox accounts persist; selection and individual pause preserve the other account")
            let uninstallFixture = store.base.appendingPathComponent("uninstall-fixture")
            try FileManager.default.createDirectory(at: uninstallFixture, withIntermediateDirectories: true)
            try Data("synthetic cached body".utf8).write(to: uninstallFixture.appendingPathComponent("cache.txt"))
            try ServiceInstaller.removeUserData(base: uninstallFixture, preserving: store.settings)
            let retained = try JSONDecoder().decode(MailSettings.self, from: Data(contentsOf: uninstallFixture.appendingPathComponent("settings.json")))
            guard retained.mailboxes?.count == 2, retained.api_model == "fixture-model",
                  !FileManager.default.fileExists(atPath: uninstallFixture.appendingPathComponent("cache.txt").path) else {
                throw Failure("uninstall configuration preservation failed")
            }
            try ServiceInstaller.removeUserData(base: uninstallFixture, preserving: nil)
            guard !FileManager.default.fileExists(atPath: uninstallFixture.path) else { throw Failure("full data removal failed") }
            checks.append("isolated uninstall retains mailbox and AI settings without cached mail; full removal deletes fixture data")
            let (_, configChoice, reportChoice) = ServiceInstaller.uninstallChoices()
            guard configChoice.title == "保留配置", reportChoice.title == "保留邮件报告",
                  configChoice.state == .off, reportChoice.state == .on,
                  !ServiceInstaller.UninstallOptions().deleteReports else { throw Failure("uninstall choice labels or defaults incorrect") }
            reportChoice.state = .off; configChoice.state = .on
            let deleteOptions = ServiceInstaller.UninstallOptions(preserveConfiguration: configChoice.state == .on,
                preserveReports: reportChoice.state == .on)
            guard deleteOptions.deleteReports, deleteOptions.preserveConfiguration,
                  configChoice.title == "保留配置", reportChoice.title == "保留邮件报告" else {
                throw Failure("uninstall preserve switch mapping or fixed labels failed")
            }
            let reportRoot = store.base.appendingPathComponent("uninstall-report-fixture")
            let reportDay = reportRoot.appendingPathComponent("2026-10-18")
            let outside = store.base.appendingPathComponent("uninstall-outside")
            try FileManager.default.createDirectory(at: reportDay, withIntermediateDirectories: true)
            try FileManager.default.createDirectory(at: outside, withIntermediateDirectories: true)
            let generated = reportDay.appendingPathComponent("fixture.txt")
            let generatedMarkdown = reportDay.appendingPathComponent("markdown.md")
            let metadata = reportDay.appendingPathComponent("fixture.mail.json")
            let unrelated = reportDay.appendingPathComponent("personal.txt")
            let sentinel = outside.appendingPathComponent("must-remain.txt")
            try "邮件编号：123\nSynthetic report".write(to: generated, atomically: true, encoding: .utf8)
            try "邮件编号：124\n## 1. Synthetic Markdown".write(to: generatedMarkdown, atomically: true, encoding: .utf8)
            try "{}".write(to: metadata, atomically: true, encoding: .utf8)
            try "unrelated".write(to: unrelated, atomically: true, encoding: .utf8)
            try "邮件编号：456\nOutside report".write(to: sentinel, atomically: true, encoding: .utf8)
            try FileManager.default.createSymbolicLink(at: reportRoot.appendingPathComponent("2026-10-19"), withDestinationURL: outside)
            var didOperate = false
            let cancelled = try ServiceInstaller.performWhenAuthorized(options: deleteOptions, reports: reportRoot,
                confirmation: { warning in
                    guard warning.informativeText.contains(reportRoot.path), warning.messageText == "确认删除邮件报告？",
                          warning.buttons[0].keyEquivalent.isEmpty, warning.buttons[1].keyEquivalent == "\r",
                          warning.window.defaultButtonCell === warning.buttons[1].cell else {
                        return .alertFirstButtonReturn
                    }
                    return .alertSecondButtonReturn
                }, operation: { didOperate = true; try ServiceInstaller.removeReports(in: reportRoot) })
            guard !cancelled, !didOperate, FileManager.default.fileExists(atPath: generated.path),
                  FileManager.default.fileExists(atPath: sentinel.path) else { throw Failure("cancelled report deletion executed uninstall action") }
            for (keyCode, characters) in [(UInt16(53), "\u{1b}"), (UInt16(36), "\r")] {
                var operated = false
                var keyResponse = NSApplication.ModalResponse.abort
                let result = ServiceInstaller.performWhenAuthorized(options: deleteOptions, reports: reportRoot,
                    confirmation: { warning in
                        let keyTimer = Timer(timeInterval: 0.05, repeats: false) { _ in
                            if let event = NSEvent.keyEvent(with: .keyDown, location: .zero, modifierFlags: [], timestamp: 0,
                                windowNumber: warning.window.windowNumber, context: nil, characters: characters,
                                charactersIgnoringModifiers: characters, isARepeat: false, keyCode: keyCode) { NSApp.sendEvent(event) }
                        }
                        let timeout = Timer(timeInterval: 2, repeats: false) { _ in NSApp.abortModal() }
                        RunLoop.main.add(keyTimer, forMode: .modalPanel)
                        RunLoop.main.add(timeout, forMode: .modalPanel)
                        defer { timeout.invalidate(); keyTimer.invalidate() }
                        keyResponse = ServiceInstaller.runReportConfirmation(warning)
                        return keyResponse
                    }, operation: { operated = true })
                guard !result, !operated, keyResponse == .alertSecondButtonReturn else { throw Failure("Return or Escape failed to cancel report deletion: key=\(keyCode), response=\(keyResponse.rawValue), performed=\(operated)") }
            }
            var confirmationCount = 0
            let kept = ServiceInstaller.performWhenAuthorized(options: .init(preserveConfiguration: false, preserveReports: true),
                reports: reportRoot, confirmation: { _ in confirmationCount += 1; return .alertSecondButtonReturn }, operation: { didOperate = true })
            guard kept, didOperate, confirmationCount == 0 else { throw Failure("configuration deletion incorrectly adds confirmation") }
            let deleted = try ServiceInstaller.performWhenAuthorized(options: deleteOptions, reports: reportRoot,
                confirmation: { _ in .alertFirstButtonReturn }, operation: { try ServiceInstaller.removeReports(in: reportRoot) })
            guard deleted, !FileManager.default.fileExists(atPath: generated.path), !FileManager.default.fileExists(atPath: generatedMarkdown.path), !FileManager.default.fileExists(atPath: metadata.path),
                  FileManager.default.fileExists(atPath: unrelated.path), FileManager.default.fileExists(atPath: sentinel.path),
                  FileManager.default.fileExists(atPath: reportRoot.path) else { throw Failure("report deletion exceeded confirmed scope") }
            checks.append("fixed uninstall labels and defaults; keep reports maps inversely to deleteReports; report deletion needs confirmation with Cancel as default and Escape target; cancellation prevents all actions; config deletion adds no confirmation; unrelated files and symlink destinations preserved")
            let isolatedReports = store.base.appendingPathComponent("index-isolation/2026-10-17")
            try FileManager.default.createDirectory(at: isolatedReports, withIntermediateDirectories: true)
            for (name, sender) in [("first", "one@example.invalid"), ("second", "two@example.invalid")] {
                let file = isolatedReports.appendingPathComponent(name + "-08-00.txt")
                try "邮件编号：101\n模拟报告".write(to: file, atomically: true, encoding: .utf8)
                try JSONSerialization.data(withJSONObject: ["uid": 101, "subject": name, "from": sender])
                    .write(to: file.deletingPathExtension().appendingPathExtension("mail.json"))
            }
            let isolated = ReportIndex.reports(in: isolatedReports.deletingLastPathComponent(), data: store.data, cached: [:])
            guard Set(isolated.map(\.sender)) == Set(["one@example.invalid", "two@example.invalid"]) else {
                throw Failure("same UID in different mailbox reports mixed sender metadata")
            }
            checks.append("report-sidecar indexing isolates different mailboxes with identical IMAP UID")
            try MailCredentials.validate(address: "demo@163.com", code: "SYNTHETIC", existing: nil)
            try MailCredentials.validate(address: "demo@163.com", code: "", existing: "demo@163.com")
            do {
                try MailCredentials.validate(address: "demo@163.com", code: "", existing: nil)
                throw Failure("missing first-run authorization code accepted")
            } catch is MailCredentials.Failure {}
            do {
                try MailCredentials.validate(address: "invalid", code: "SYNTHETIC", existing: nil)
                throw Failure("invalid address accepted")
            } catch is MailCredentials.Failure {}
            let onboarding = NSHostingView(rootView: MailAccountView(store: store, onboarding: true))
            onboarding.frame = NSRect(x: 0, y: 0, width: 520, height: 420)
            onboarding.layoutSubtreeIfNeeded()
            checks.append("first-run account form renders; address/code validation; existing code may be retained; no real keychain writes")
            guard let window = NSApp.windows.first(where: { $0.title == "邮件小秘书" }), let view = window.contentView else { throw Failure("main window missing") }
            store.needsAccountSetup = true
            RunLoop.main.run(until: Date().addingTimeInterval(0.6))
            guard window.attachedSheet != nil else { throw Failure("first-run setup sheet not presented") }
            try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
            _ = try? capture(window, to: output.appendingPathComponent("mac-setup.png"))
            store.needsAccountSetup = false
            RunLoop.main.run(until: Date().addingTimeInterval(0.3))
            checks.append("first-run setup appears as an actual attached sheet")
            let agent = try ServiceInstaller.prepare(base: store.base, home: store.base.appendingPathComponent("test-home"))
            let agentData = try Data(contentsOf: agent)
            let job = try PropertyListSerialization.propertyList(from: agentData, format: nil) as? [String: Any]
            guard let command = job?["ProgramArguments"] as? [String],
                  command.first == ServiceInstaller.worker.path, command.contains("--daemon"),
                  command.contains(store.base.path), !command.contains("/usr/bin/python3"),
                  job?["KeepAlive"] as? Bool == true else { throw Failure("standalone worker installation failed") }
            checks.append("fresh user launch-agent generated with bundled worker; no system Python; existing user service untouched")
            let beforeExit = store.settings
            try store.prepareForExit(); store.refresh()
            guard !store.settings.enabled,
                  !AppDelegate().applicationShouldTerminateAfterLastWindowClosed(NSApp) else {
                throw Failure("quit must persist pause while window closing keeps the app running")
            }
            let quitLabel = "com.benson.mail-quit-test." + UUID().uuidString.lowercased()
            let quitJob = store.base.appendingPathComponent("quit-test.plist")
            let quitBytes = try PropertyListSerialization.data(fromPropertyList: [
                "Label": quitLabel, "ProgramArguments": ["/bin/sleep", "60"], "RunAtLoad": true, "KeepAlive": true
            ], format: .xml, options: 0)
            try quitBytes.write(to: quitJob)
            let quitTarget = "gui/\(getuid())/" + quitLabel
            guard MailStore.run("/bin/launchctl", ["bootstrap", "gui/\(getuid())", quitJob.path]) == 0 else {
                throw Failure("isolated quit service fixture could not start")
            }
            defer { _ = MailStore.run("/bin/launchctl", ["bootout", quitTarget]) }
            try ServiceInstaller.stop(name: quitLabel)
            guard MailStore.run("/bin/launchctl", ["print", quitTarget]) != 0 else { throw Failure("quit left service registered") }
            store.settings = beforeExit; try store.save()
            checks.append("quit persists paused state and removes isolated KeepAlive service; closing last window keeps UI running")
            window.orderOut(nil); window.makeKeyAndOrderFront(nil)
            guard window.isVisible else { throw Failure("window restore failed") }
            view.layoutSubtreeIfNeeded()
            try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
            let captured = (try? capture(window, to: output.appendingPathComponent("mac-window.png"))) != nil
            let settingsWindow = NSWindow(contentRect: NSRect(x: 120, y: 120, width: 560, height: 530), styleMask: [.titled, .closable], backing: .buffered, defer: false)
            settingsWindow.title = "邮件小秘书设置"
            settingsWindow.contentView = NSHostingView(rootView: SettingsView(store: store))
            settingsWindow.makeKeyAndOrderFront(nil)
            RunLoop.main.run(until: Date().addingTimeInterval(0.5))
            _ = try? capture(settingsWindow, to: output.appendingPathComponent("mac-settings.png"))
            settingsWindow.orderOut(nil)
            checks.append("native SwiftUI main/settings windows created; main window restore verified")
            checks.append(captured ? "actual window screenshots saved" : "window screenshot unavailable: macOS screen recording permission not granted")
            guard AppLanguage.detect(["zh-Hant-TW"]) == "zh", AppLanguage.detect(["zh-CN"]) == "zh", AppLanguage.detect(["es-MX"]) == "es", AppLanguage.detect(["es-ES"]) == "es", AppLanguage.detect(["fr-FR"]) == "en", AppLanguage.detect([]) == "en" else { throw Failure("system language detection failed") }
            for code in ["zh", "en", "es"] {
                guard let guide = MailAccountGuide.url(language: code),
                      guide.lastPathComponent == "Mail-account-setup-\(code).txt",
                      (try String(contentsOf: guide, encoding: .utf8)).count > 1000 else {
                    throw Failure("Bundled account guide missing or wrong language")
                }
            }
            checks.append("three downloaded account setup guides exist; help resolves selected pack language without opening editor")
            for code in ["zh", "en", "es"] {
                guard let guide = MailHelp.quickStartURL(language: code),
                      (try String(contentsOf: guide, encoding: .utf8)).count > 600 else { throw Failure("quick start guide missing") }
            }
            func verifyHelp(_ titles: [String], heading: String) throws {
                RunLoop.main.run(until: Date().addingTimeInterval(0.3))
                MailHelp.refreshTitle()
                guard let help = NSApp.helpMenu,
                      let main = NSApp.mainMenu,
                      main.items.filter({ $0.submenu === help }).count == 1,
                      main.items.first(where: { $0.submenu === help })?.title == heading else {
                    throw Failure("native Help menu missing, duplicated or wrong language")
                }
                let visible = help.items.filter { !$0.isSeparatorItem }.map(\.title)
                guard visible == titles else { throw Failure("Help actions incorrect: \(visible)") }
                guard help.items.filter({ !$0.isSeparatorItem }).allSatisfy({ $0.action != nil }) else {
                    throw Failure("Help menu contains unconnected actions")
                }
            }
            try verifyHelp(["使用指南", "如何获取授权码？", "检查更新", "关于邮件小秘书"], heading: "帮助")
            checks.append("single native Help menu contains four connected actions; three language-pack quick-start guides")
            guard MailAccountGuide.offersToken("oauth2"), !MailAccountGuide.offersToken("password"),
                  let tokenTool = MailAccountGuide.tokenURL(), FileManager.default.isExecutableFile(atPath: tokenTool.path) else {
                throw Failure("OAuth2 conditional token button or bundled helper missing")
            }
            checks.append("OAuth2 token entry only offered for OAuth2 authentication; bundled executable command exists")
            let originalUpdateState = store.settings.enabled
            for enabled in [true, false] {
                store.settings.enabled = enabled; try store.save()
                let prior = try store.pauseForUpdate()
                guard prior == enabled, !store.settings.enabled else { throw Failure("update pause lost listening state") }
                try store.restoreAfterUpdate(prior)
                let persisted = try JSONDecoder().decode(MailSettings.self, from: Data(contentsOf: store.settingsURL))
                guard persisted.enabled == enabled else { throw Failure("update restart failed to retain original listening state") }
            }
            store.settings.enabled = originalUpdateState; try store.save()
            checks.append("update pause and restart preserve both listening and paused settings; manual Dock quit path remains separate")
            let existingText = store.reportText
            let existingTitles = store.reports.map(\.title)
            let enabledBeforeLanguage = store.settings.enabled
            AppLanguage.shared.select("en")
            let diagnostic = "demo@example.invalid：邮箱连接失败：服务器明确提示 IMAP 未开启；请在邮箱网页设置中启用 IMAP。\n服务器：imap.example.invalid:993 (ssl)\n阶段：LOGIN 认证\n具体原因：IMAP4.error: IMAP disabled [已隐藏凭据]"
            let translatedDiagnostic = T(diagnostic)
            guard translatedDiagnostic.contains("Server: imap.example.invalid:993"), translatedDiagnostic.contains("Stage: LOGIN authentication"),
                  translatedDiagnostic.contains("IMAP is disabled"), translatedDiagnostic.contains("[credentials hidden]"),
                  T("查看具体错误") == "Show error details" else { throw Failure("safe mailbox diagnostic English translation failed") }
            checks.append("safe structured mailbox diagnostics retain endpoint, stage and server code in English; credentials stay hidden")
            try verifyHelp(["User guide", "How do I get an authorization code?", "Check for updates", "About Email Assistant"], heading: "Help")
            guard T("保留配置") == "Keep configuration", T("保留邮件报告") == "Keep mail reports",
                  T("邮件小秘书") == "Email Assistant", T("界面语言") == "Interface language",
                  store.settings.ui_language == "en", store.reportText == existingText,
                  store.reports.map(\.title) == existingTitles, store.settings.enabled == enabledBeforeLanguage else { throw Failure("English language switch changed content or monitoring state") }
            guard T("最近检查：\(T("尚未检查"))") == "Last check: Not checked yet" else { throw Failure("uninitialized last-check translation failed") }
            let savedLanguage = try JSONSerialization.jsonObject(with: Data(contentsOf: store.base.appendingPathComponent("settings.json"))) as? [String: Any]
            guard savedLanguage?["ui_language"] as? String == "en" else { throw Failure("language choice not persisted") }
            settingsWindow.contentView = NSHostingView(rootView: SettingsView(store: store))
            settingsWindow.makeKeyAndOrderFront(nil)
            RunLoop.main.run(until: Date().addingTimeInterval(0.3))
            _ = try? capture(settingsWindow, to: output.appendingPathComponent("mac-settings-english.png"))
            settingsWindow.orderOut(nil)
            // Exercise the actual missing-pack state machine with synthetic local catalogs only.
            // Tests never invoke the worker's network download or load a real user's settings.
            let language = AppLanguage.shared
            let spanishPack = store.base.appendingPathComponent("languages/es.json")
            let spanishData = try Data(contentsOf: spanishPack)
            let settingsBeforeMissing = try JSONSerialization.jsonObject(with: JSONEncoder().encode(store.settings)) as! NSDictionary
            try FileManager.default.removeItem(at: spanishPack)
            defer { try? spanishData.write(to: spanishPack, options: .atomic) }
            guard !language.isInstalled("es") else { throw Failure("fixture must not inherit a bundled Spanish language pack") }
            var downloaded = false
            let cancelledLanguageChange = try await language.change(to: "es", confirmDownload: { false }, download: { _ in downloaded = true })
            guard !cancelledLanguageChange, !downloaded, language.code == "en", store.settings.ui_language == "en" else { throw Failure("missing-pack cancellation changed selection or downloaded without consent") }
            var caughtDownloadFailure = false
            do {
                try await language.change(to: "es", confirmDownload: { true }, download: { _ in throw Failure("Synthetic offline download") })
            } catch { caughtDownloadFailure = true }
            guard caughtDownloadFailure, language.code == "en", !language.isDownloading,
                  (try JSONSerialization.jsonObject(with: JSONEncoder().encode(store.settings)) as! NSDictionary).isEqual(settingsBeforeMissing) else {
                throw Failure("failed language download changed settings or left busy state")
            }
            var caughtInvalidPack = false
            do {
                try await language.change(to: "es", confirmDownload: { true }, download: { _ in try Data("{}".utf8).write(to: spanishPack, options: .atomic) })
            } catch { caughtInvalidPack = true }
            guard caughtInvalidPack, language.code == "en", store.settings.ui_language == "en" else { throw Failure("invalid downloaded catalog activated") }
            try FileManager.default.removeItem(at: spanishPack)
            let switchedSpanish = try await language.change(to: "es", confirmDownload: { true }, download: { code in
                guard code == "es" else { throw Failure("wrong language requested") }
                try spanishData.write(to: spanishPack, options: .atomic)
            })
            guard switchedSpanish, language.code == "es", store.settings.ui_language == "es",
                  T("邮件小秘书") == "Asistente de correo electrónico", T("界面语言") == "Idioma de la interfaz",
                  store.reportText == existingText, store.reports.map(\.title) == existingTitles,
                  store.settings.enabled == enabledBeforeLanguage else { throw Failure("Spanish language download/switch lost report text or monitoring state") }
            var spanishSettings = try JSONSerialization.jsonObject(with: JSONEncoder().encode(store.settings)) as! [String: Any]
            var englishSettings = settingsBeforeMissing as! [String: Any]
            spanishSettings.removeValue(forKey: "ui_language"); englishSettings.removeValue(forKey: "ui_language")
            guard (spanishSettings as NSDictionary).isEqual(to: englishSettings) else { throw Failure("language switch changed mailbox, AI or report settings") }
            guard let spanishGuide = MailAccountGuide.url(language: "es"), spanishGuide.lastPathComponent == "Mail-account-setup-es.txt",
                  try String(contentsOf: spanishGuide, encoding: .utf8).count > 1000 else { throw Failure("Spanish downloaded guide missing") }
            try verifyHelp([T("使用指南"), T("如何获取授权码？"), T("检查更新"), T("关于邮件小秘书")], heading: T("帮助"))
            settingsWindow.contentView = NSHostingView(rootView: SettingsView(store: store))
            settingsWindow.makeKeyAndOrderFront(nil)
            try await Task.sleep(nanoseconds: 300_000_000)
            _ = try? capture(settingsWindow, to: output.appendingPathComponent("mac-settings-spanish.png"))
            settingsWindow.orderOut(nil)
            checks.append("Spanish pack activation and application name; missing-pack cancel, offline failure, invalid pack and successful consented retry tested with local fixtures; mailbox/AI/report settings preserved")
            AppLanguage.shared.select("zh")
            try verifyHelp(["使用指南", "如何获取授权码？", "检查更新", "关于邮件小秘书"], heading: "帮助")
            guard T("邮件小秘书") == "邮件小秘书", store.settings.ui_language == "zh" else { throw Failure("Chinese switch failed") }
            checks.append("system language detection; live English/Chinese switch persists, preserves original email/report text and monitoring; English settings rendered")
            let updateSuite = "BensonMailLanguageFixture-" + UUID().uuidString
            let updateDefaults = UserDefaults(suiteName: updateSuite)!
            defer { updateDefaults.removePersistentDomain(forName: updateSuite) }
            let syntheticManifest: [String: Any] = ["schema_version": 1, "platforms": [AppUpdater.platform: [
                "version": "202610200001", "url": "https://updates.example.invalid/fixture.dmg",
                "sha256": String(repeating: "0", count: 64), "notes": ["zh": "模拟更新", "en": "Fixture update", "es": "Actualización de prueba"]
            ]]]
            let syntheticManifestBytes = try JSONSerialization.data(withJSONObject: syntheticManifest)
            var manifestRequests: [URLRequest] = []
            let migratedUpdater = AppUpdater(defaults: updateDefaults, currentVersion: "000000000000",
                downloadRoot: store.base.appendingPathComponent("update-test"), endpoint: { URL(string: AppUpdater.canonicalManifest) },
                fetch: { request in
                    manifestRequests.append(request)
                    if request.url?.absoluteString == AppUpdater.canonicalManifest { throw URLError(.timedOut) }
                    guard request.url?.absoluteString == AppUpdater.manifestAPI else { throw Failure("unexpected manifest fallback host") }
                    return (syntheticManifestBytes, HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: "HTTP/1.1", headerFields: nil)!)
                })
            await migratedUpdater.check(manual: true)
            guard manifestRequests.count == 2, manifestRequests.last?.value(forHTTPHeaderField: "Accept") == "application/vnd.github.raw+json",
                  migratedUpdater.available?.version == "202610200001",
                  migratedUpdater.available?.localizedNotes(for: "es") == "Actualización de prueba" else { throw Failure("unified repository manifest/API fallback failed") }
            checks.append("unified repository raw manifest timeout falls back to API with correct Accept; Spanish update notes preserved; synthetic transport only")
            let fixtureAIProvider = store.settings.ai_provider
            store.settings.ai_provider = "api"
            try store.save()
            let mainWindow = NSWindow(contentRect: NSRect(x: 60, y: 60, width: 1120, height: 760), styleMask: [.titled, .closable, .resizable], backing: .buffered, defer: false)
            mainWindow.title = "Workspace layout fixture"
            mainWindow.appearance = NSAppearance(named: .aqua)
            mainWindow.contentView = NSHostingView(rootView: ContentView(store: store))
            mainWindow.makeKeyAndOrderFront(nil)
            try await Task.sleep(nanoseconds: 250_000_000)
            guard let root = mainWindow.contentView else { throw Failure("main layout window missing") }
            let preservedReport = store.selected?.id
            let preservedSource = store.reportText
            func allFields(_ view: NSView) -> [NSTextField] {
                ((view as? NSTextField).map { [$0] } ?? []) + view.subviews.flatMap { allFields($0) }
            }
            func editField(_ placeholder: String, _ value: String) throws -> NSTextField {
                guard let field = allFields(root).first(where: { $0.placeholderString == T(placeholder) }) else { throw Failure("draft field missing: " + placeholder) }
                mainWindow.makeFirstResponder(field)
                guard let editor = mainWindow.fieldEditor(false, for: field) as? NSTextView else { throw Failure("native field editor missing") }
                editor.selectAll(nil); editor.insertText(value, replacementRange: editor.selectedRange())
                mainWindow.makeFirstResponder(nil)
                return field
            }
            // Complete the real setup sheet after the permanent page views have mounted.
            store.needsAccountSetup = true
            try await Task.sleep(nanoseconds: 250_000_000)
            store.mailAccount = "setup-saved@example.invalid"
            store.settings.mailbox?.account = store.mailAccount
            store.settings.api_base = "https://setup-saved.invalid/v1"
            store.settings.api_model = "setup-saved-model"
            try store.save()
            store.needsAccountSetup = false
            try await Task.sleep(nanoseconds: 300_000_000)
            guard allFields(root).contains(where: { $0.stringValue == "setup-saved@example.invalid" }),
                  allFields(root).contains(where: { $0.stringValue == "https://setup-saved.invalid/v1" }) else { throw Failure("main page drafts did not refresh after first-run setup") }
            checks.append("finishing first-run setup refreshes permanently mounted mailbox and AI drafts; subsequent navigation preserves unsaved edits")
            store.workspacePage = .mailbox
            try await Task.sleep(nanoseconds: 250_000_000)
            _ = try editField("邮箱地址，例如 name@example.com", "unsaved-layout@example.invalid")
            store.workspacePage = .ai
            try await Task.sleep(nanoseconds: 250_000_000)
            _ = try editField("基础地址，例如 https://服务商地址/v1", "https://unsaved-layout.invalid/v1")
            for page in [WorkspacePage.general, .mailbox, .ai, .reports] {
                store.workspacePage = page
                try await Task.sleep(nanoseconds: 250_000_000)
                try capture(mainWindow, to: output.appendingPathComponent("workspace-" + String(describing: page) + ".png"))
            }
            guard allFields(root).contains(where: { $0.stringValue == "unsaved-layout@example.invalid" }),
                  allFields(root).contains(where: { $0.stringValue == "https://unsaved-layout.invalid/v1" }),
                  store.selected?.id == preservedReport, store.reportText == preservedSource else { throw Failure("navigation lost unsaved native drafts or report selection") }
            func nativeField(_ placeholder: String) throws -> NSTextField {
                guard let field = allFields(root).first(where: { $0.placeholderString == T(placeholder) }) else { throw Failure("login fixture native field missing") }
                return field
            }
            func finishLoginSetup(_ connection: MailConnection) async throws {
                store.needsAccountSetup = true
                try await Task.sleep(nanoseconds: 250_000_000)
                store.mailAccount = connection.account
                store.settings.mailbox = connection
                store.settings.mailboxes = [MailboxProfile(connection: connection)]
                try store.save()
                store.needsAccountSetup = false
                store.workspacePage = .mailbox
                try await Task.sleep(nanoseconds: 300_000_000)
            }
            func nativeViews(_ view: NSView) -> [NSView] { [view] + view.subviews.flatMap { nativeViews($0) } }
            func openAdvanced() async throws {
                if allFields(root).contains(where: { $0.placeholderString == T("登录用户名；留空使用邮箱地址") && !$0.isHiddenOrHasHiddenAncestor }) { return }
                guard let anchor = nativeViews(root).first(where: { $0.identifier?.rawValue == "mail-advanced-disclosure" }) else { throw Failure("native advanced disclosure anchor missing") }
                mainWindow.makeKeyAndOrderFront(nil)
                NSApp.activate(ignoringOtherApps: true)
                anchor.scrollToVisible(anchor.bounds)
                try await Task.sleep(nanoseconds: 150_000_000)
                let point = anchor.convert(NSPoint(x: anchor.bounds.minX - 7, y: anchor.bounds.midY), to: nil)
                for kind in [NSEvent.EventType.leftMouseDown, .leftMouseUp] {
                    guard let event = NSEvent.mouseEvent(with: kind, location: point, modifierFlags: [], timestamp: ProcessInfo.processInfo.systemUptime,
                        windowNumber: mainWindow.windowNumber, context: nil, eventNumber: 0, clickCount: 1, pressure: 1) else { throw Failure("native disclosure mouse event missing") }
                    NSApp.postEvent(event, atStart: false)
                }
                try await Task.sleep(nanoseconds: 350_000_000)
                guard allFields(root).contains(where: { $0.placeholderString == T("登录用户名；留空使用邮箱地址") && !$0.isHiddenOrHasHiddenAncestor }) else { throw Failure("native mouse click did not expand advanced connection options: anchor=\(anchor.frame), point=\(point)") }
            }
            var defaultLogin = MailConnection()
            defaultLogin.account = "old-default@example.invalid"
            defaultLogin.username = defaultLogin.account
            var mixedCaseDefault = defaultLogin
            mixedCaseDefault.username = "  OLD-DEFAULT@EXAMPLE.INVALID  "
            let mixedCaseIdentity = mixedCaseDefault.identity
            var explicitCustom = MailConnection()
            explicitCustom.account = "old@example.invalid"; explicitCustom.username = "distinct-login"
            guard MailAccountDraft.load(mixedCaseDefault).username.isEmpty,
                  MailAccountDraft.changingAccount(mixedCaseDefault, to: "next@example.invalid").login == "next@example.invalid",
                  mixedCaseDefault.identity == mixedCaseIdentity,
                  MailAccountDraft.load(MailAccountDraft.changingAccount(explicitCustom, to: "next@example.invalid")).username == "distinct-login" else { throw Failure("trimmed case-insensitive default mapping changed persisted data or a distinct custom login") }
            let persistedIdentity = defaultLogin.identity
            try await finishLoginSetup(defaultLogin)
            guard !allFields(root).contains(where: { $0.placeholderString == T("登录用户名；留空使用邮箱地址") && !$0.isHiddenOrHasHiddenAncestor }) else { throw Failure("login username should stay inside collapsed advanced options") }
            try await openAdvanced()
            guard try nativeField("登录用户名；留空使用邮箱地址").stringValue.isEmpty,
                  MailAccountDraft.load(defaultLogin).identity == persistedIdentity,
                  store.settings.mailbox?.username == defaultLogin.account else { throw Failure("default login was not cleared only in the editable draft") }
            _ = try editField("邮箱地址，例如 name@example.com", "new-default@example.invalid")
            try await Task.sleep(nanoseconds: 150_000_000)
            var nativeDefault = defaultLogin
            nativeDefault.account = try nativeField("邮箱地址，例如 name@example.com").stringValue
            nativeDefault.username = try nativeField("登录用户名；留空使用邮箱地址").stringValue
            guard try nativeDefault.validated().login == "new-default@example.invalid" else { throw Failure("native edited address retained stale default login") }
            // Also cover a user explicitly typing the old address as the login before editing it.
            _ = try editField("登录用户名；留空使用邮箱地址", "new-default@example.invalid")
            try await Task.sleep(nanoseconds: 150_000_000)
            _ = try editField("邮箱地址，例如 name@example.com", "next-default@example.invalid")
            try await Task.sleep(nanoseconds: 150_000_000)
            guard try nativeField("登录用户名；留空使用邮箱地址").stringValue.isEmpty else { throw Failure("explicit old-address login did not follow native address edit") }
            var customLogin = defaultLogin
            customLogin.account = "custom-account@example.invalid"
            customLogin.username = "distinct-server-login"
            try await finishLoginSetup(customLogin)
            try await openAdvanced()
            let nativeCustom = try nativeField("登录用户名；留空使用邮箱地址")
            guard nativeCustom.stringValue == customLogin.username, !nativeCustom.isHiddenOrHasHiddenAncestor,
                  MailAccountDraft.load(customLogin).identity == customLogin.identity else { throw Failure("distinct custom login was changed or missing after expanding advanced options") }
            _ = try editField("邮箱地址，例如 name@example.com", "custom-edited@example.invalid")
            for page in [WorkspacePage.ai, .reports, .general, .mailbox] {
                store.workspacePage = page
                try await Task.sleep(nanoseconds: 150_000_000)
            }
            guard try nativeField("登录用户名；留空使用邮箱地址").stringValue == customLogin.username,
                  try nativeField("邮箱地址，例如 name@example.com").stringValue == "custom-edited@example.invalid" else { throw Failure("custom login or unsaved address lost across native page navigation") }
            try capture(mainWindow, to: output.appendingPathComponent("mailbox-advanced-custom-login.png"))
            AppLanguage.shared.select("en")
            guard T("当前使用自定义登录用户名：") == "Custom login username in use: ",
                  T("登录用户名") == "Login username" else { throw Failure("login guidance English translation missing") }
            AppLanguage.shared.select("zh")
            checks.append("actual native username fields: saved default becomes blank without changing persisted identity; edited address supplies the login; explicit old-address login clears; username stays inside collapsed advanced options; actual native mouse click expands it; distinct custom login survives address edits, setup completion and page navigation; bilingual hints")
            mainWindow.orderOut(nil)
            store.settings.ai_provider = fixtureAIProvider
            checks.append("actual native field edits survive mailbox/AI/general/report navigation; report selection and content retained; four native layout snapshots captured")
            checks.append(contentsOf: try await ReportConversationSelfTest.run(base: store.base))
            let value: [String: Any] = ["ok": true, "checks": checks]
            try JSONSerialization.data(withJSONObject: value, options: [.prettyPrinted, .sortedKeys]).write(to: output.appendingPathComponent("result.json"))
        } catch {
            try? FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
            let value: [String: Any] = ["ok": false, "error": error.localizedDescription, "checks": checks]
            try? JSONSerialization.data(withJSONObject: value, options: [.prettyPrinted]).write(to: output.appendingPathComponent("result.json"))
        }
        NSApp.terminate(nil)
    }
    static func capture(_ window: NSWindow, to output: URL) throws {
        guard let view = window.contentView,
              let bitmap = view.bitmapImageRepForCachingDisplay(in: view.bounds) else { throw Failure("native snapshot allocation failed") }
        view.layoutSubtreeIfNeeded()
        view.cacheDisplay(in: view.bounds, to: bitmap)
        // Native cached layers can be transparent where the window supplies its background.
        let image = NSImage(size: view.bounds.size)
        image.lockFocus()
        NSColor(calibratedWhite: window.appearance?.name == .aqua ? 0.96 : 0.16, alpha: 1).setFill()
        view.bounds.fill()
        bitmap.draw(in: view.bounds)
        image.unlockFocus()
        guard let tiff = image.tiffRepresentation, let flattened = NSBitmapImageRep(data: tiff),
              let data = flattened.representation(using: .png, properties: [:]) else { throw Failure("native snapshot encoding failed") }
        try data.write(to: output)
    }

    struct Failure: LocalizedError {
        let text: String
        init(_ text: String) { self.text = text }
        var errorDescription: String? { text }
    }
}

// Non-interactive location marker for synthetic native mouse-event fixtures.
// It is inserted only in --self-test mode; the production disclosure remains unchanged.
struct NativeTestAnchor: NSViewRepresentable {
    let identifier: String
    final class Marker: NSView { override func hitTest(_ point: NSPoint) -> NSView? { nil } }
    func makeNSView(context: Context) -> NSView { let view = Marker(); view.identifier = NSUserInterfaceItemIdentifier(identifier); return view }
    func updateNSView(_ view: NSView, context: Context) {}
}

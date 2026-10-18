import AppKit
import Foundation
import Security

/// Installs only this user's launch agents. State and credentials survive upgrades.
enum ServiceInstaller {
    static let label = "com.benson.codex-mail-163"
    static var worker: URL {
        Bundle.main.bundleURL.appendingPathComponent("Contents/Resources/worker/MailWorker")
    }
    static func prepare(base: URL, home: URL = FileManager.default.homeDirectoryForCurrentUser,
                        app: URL = Bundle.main.bundleURL, executable: URL = worker) throws -> URL {
        let fm = FileManager.default
        guard fm.isExecutableFile(atPath: executable.path) else {
            throw MailCredentials.Failure("安装包缺少后台组件，请重新安装完整的邮件小秘书。")
        }
        // A mounted installer/translocated copy is not a persistent service location.
        if app.path.hasPrefix("/Volumes/") || app.path.contains("/AppTranslocation/") {
            throw MailCredentials.Failure("请先将邮件小秘书拖入“应用程序”文件夹，再从那里打开。")
        }
        try fm.createDirectory(at: base, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
        let directory = home.appendingPathComponent("Library/LaunchAgents")
        try fm.createDirectory(at: directory, withIntermediateDirectories: true)
        let agent = directory.appendingPathComponent(label + ".plist")
        let value: [String: Any] = [
            "Label": label,
            "ProgramArguments": [executable.path, "--home", base.path, "--app", app.path, "--daemon"],
            "WorkingDirectory": base.path,
            "RunAtLoad": true, "KeepAlive": true, "ThrottleInterval": 15,
            "StandardOutPath": base.appendingPathComponent("daemon.log").path,
            "StandardErrorPath": base.appendingPathComponent("daemon-error.log").path,
            "EnvironmentVariables": ["PATH": "/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin:/usr/local/bin"],
        ]
        let bytes = try PropertyListSerialization.data(fromPropertyList: value, format: .xml, options: 0)
        if (try? Data(contentsOf: agent)) != bytes {
            // The caller stops/reloads an old job only after pending processing finishes.
            try bytes.write(to: agent, options: .atomic)
            try fm.setAttributes([.posixPermissions: 0o600], ofItemAtPath: agent.path)
        }
        return agent
    }
    static func launch(base: URL) throws {
        let domain = "gui/\(getuid())"
        let target = domain + "/" + label
        let agent = try prepare(base: base)
        let marker = base.appendingPathComponent("worker-installation.json")
        let fingerprint = worker.path + "|" + (Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "dev")
        let previous = (try? String(contentsOf: marker, encoding: .utf8)) ?? ""
        _ = MailStore.run("/bin/launchctl", ["enable", target])
        if previous != fingerprint {
            let status = base.appendingPathComponent("mail_watch/service.json")
            let deadline = Date().addingTimeInterval(920)
            while Date() < deadline,
                  MailStore.run("/bin/launchctl", ["print", target]) == 0,
                  let bytes = try? Data(contentsOf: status),
                  let value = try? JSONSerialization.jsonObject(with: bytes) as? [String: Any],
                  let phase = value["phase"] as? String, ["checking", "analyzing"].contains(phase),
                  let raw = value["heartbeat"] as? String,
                  let heartbeat = MailStore.parseDate(raw),
                  Date().timeIntervalSince(heartbeat) < 1100 {
                Thread.sleep(forTimeInterval: 1)
            }
            _ = MailStore.run("/bin/launchctl", ["bootout", target])
        } else if MailStore.run("/bin/launchctl", ["kickstart", target]) == 0 { return }
        guard MailStore.run("/bin/launchctl", ["bootstrap", domain, agent.path]) == 0 else {
            throw MailCredentials.Failure("无法注册后台服务。请在系统设置 → 通用 → 登录项中检查是否允许后台运行。")
        }
        try fingerprint.write(to: marker, atomically: true, encoding: .utf8)
    }
    static func stop(name: String = label) throws {
        let target = "gui/\(getuid())/" + name
        _ = MailStore.run("/bin/launchctl", ["bootout", target])
        guard MailStore.run("/bin/launchctl", ["print", target]) != 0 else {
            throw MailCredentials.Failure("后台服务仍未退出，请稍后重试。")
        }
    }
    struct UninstallOptions {
        var preserveConfiguration = false
        var preserveReports = true
        var deleteReports: Bool { !preserveReports }
    }
    @MainActor static func uninstallChoices() -> (NSStackView, NSButton, NSButton) {
        let preserve = NSButton(checkboxWithTitle: T("保留配置"), target: nil, action: nil)
        preserve.state = .off
        preserve.setAccessibilityIdentifier("uninstall-preserve-config")
        let reports = NSButton(checkboxWithTitle: T("保留邮件报告"), target: nil, action: nil)
        reports.state = .on
        reports.setAccessibilityIdentifier("uninstall-preserve-reports")
        let explanation = NSTextField(wrappingLabelWithString: T("勾选表示保留，取消勾选表示删除。邮件报告默认保留。"))
        explanation.preferredMaxLayoutWidth = 340
        let stack = NSStackView(views: [preserve, reports, explanation])
        stack.orientation = .vertical; stack.alignment = .leading; stack.spacing = 10
        stack.setFrameSize(NSSize(width: 340, height: stack.fittingSize.height))
        return (stack, preserve, reports)
    }
    @MainActor static func runReportConfirmation(_ alert: NSAlert) -> NSApplication.ModalResponse {
        // A button has one key equivalent: Return activates Cancel; handle Escape for this modal only.
        let monitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { event in
            if event.keyCode == 53, NSApp.modalWindow === alert.window {
                NSApp.stopModal(withCode: .alertSecondButtonReturn)
                return nil
            }
            return event
        }
        defer { if let monitor { NSEvent.removeMonitor(monitor) } }
        return alert.runModal()
    }
    /// Authorization always precedes service, credential, report or application removal.
    @MainActor @discardableResult static func performWhenAuthorized(
        options: UninstallOptions, reports: URL,
        confirmation: @MainActor (NSAlert) -> NSApplication.ModalResponse = { runReportConfirmation($0) },
        operation: () throws -> Void
    ) rethrows -> Bool {
        if options.deleteReports {
            let warning = NSAlert()
            warning.alertStyle = .warning
            warning.messageText = T("确认删除邮件报告？")
            warning.informativeText = T("将永久删除以下目录日期子文件夹中由邮件小秘书生成的 Markdown / TXT 报告及对应邮件索引，并清理空的日期子文件夹。其他文件和所选根目录保留。此操作无法撤销。") + "\n\n" + reports.path
            warning.addButton(withTitle: T("删除报告并卸载"))
            warning.addButton(withTitle: T("取消"))
            warning.layout()
            warning.buttons[0].keyEquivalent = ""
            warning.buttons[1].keyEquivalent = "\r"
            guard confirmation(warning) == .alertFirstButtonReturn else { return false }
        }
        try operation()
        return true
    }
    @MainActor static func uninstall(base: URL) {
        let alert = NSAlert()
        alert.messageText = T("卸载邮件小秘书？")
        alert.informativeText = T("将停止后台服务并移除应用、缓存和登录项。请选择要保留的内容。")
        let (choices, preserve, preserveReports) = uninstallChoices()
        alert.accessoryView = choices
        alert.addButton(withTitle: T("卸载")); alert.addButton(withTitle: T("取消"))
        guard alert.runModal() == .alertFirstButtonReturn else { return }
        let options = UninstallOptions(preserveConfiguration: preserve.state == .on, preserveReports: preserveReports.state == .on)
        do {
            try performWhenAuthorized(options: options, reports: MailStore.shared.output.standardizedFileURL) {
                let fm = FileManager.default
                let domain = "gui/\(getuid())"
                for name in [label, "com.benson.mail-ui"] {
                    _ = MailStore.run("/bin/launchctl", ["bootout", domain + "/" + name])
                    let path = fm.homeDirectoryForCurrentUser.appendingPathComponent("Library/LaunchAgents/\(name).plist")
                    if fm.fileExists(atPath: path.path) { try fm.removeItem(at: path) }
                }
                if !options.preserveConfiguration {
                    for service in ["Codex-Mail-163", "BensonMail-IMAP", "BensonMail-AI-API"] {
                        SecItemDelete([kSecClass as String: kSecClassGenericPassword,
                                       kSecAttrService as String: service] as CFDictionary)
                    }
                }
                // Reports may have been deliberately saved inside the app's data directory.
                let reports = MailStore.shared.output.standardizedFileURL
                var retainedSettings = MailStore.shared.settings
                if options.deleteReports {
                    try removeReports(in: reports)
                } else if (reports.path == base.standardizedFileURL.path ||
                    reports.path.hasPrefix(base.standardizedFileURL.path + "/") ||
                    reports.path.hasPrefix(Bundle.main.bundleURL.path + "/")), fm.fileExists(atPath: reports.path) {
                    let preserved = fm.homeDirectoryForCurrentUser.appendingPathComponent("Documents/邮件-卸载保留-" + UUID().uuidString.prefix(8))
                    try fm.createDirectory(at: preserved, withIntermediateDirectories: true)
                    // Move only dated report folders if the selected output is the data root.
                    if reports.path == base.standardizedFileURL.path {
                        for child in try fm.contentsOfDirectory(at: reports, includingPropertiesForKeys: nil)
                        where child.lastPathComponent.range(of: #"^\d{4}-\d{2}-\d{2}$"#, options: .regularExpression) != nil {
                            try fm.moveItem(at: child, to: preserved.appendingPathComponent(child.lastPathComponent))
                        }
                    } else {
                        try fm.removeItem(at: preserved)
                        try fm.moveItem(at: reports, to: preserved)
                    }
                    retainedSettings.output_dir = preserved.path
                }
                try removeUserData(base: base, preserving: options.preserveConfiguration ? retainedSettings : nil)
                try fm.trashItem(at: Bundle.main.bundleURL, resultingItemURL: nil)
                MailStore.shared.uninstalling = true
                NSApp.terminate(nil)
            }
        } catch {
            let failure = NSAlert(); failure.messageText = T("卸载未完成")
            failure.informativeText = T(error.localizedDescription); failure.runModal()
        }
    }
    /// Never recursively remove a user-selected report root or follow directory/file links.
    static func removeReports(in root: URL) throws {
        let fm = FileManager.default
        let keys: Set<URLResourceKey> = [.isDirectoryKey, .isRegularFileKey, .isSymbolicLinkKey]
        guard let rootValues = try? root.resourceValues(forKeys: keys), rootValues.isDirectory == true,
              rootValues.isSymbolicLink != true else { return }
        for day in try fm.contentsOfDirectory(at: root, includingPropertiesForKeys: Array(keys)) {
            let values = try day.resourceValues(forKeys: keys)
            guard values.isDirectory == true, values.isSymbolicLink != true,
                  day.lastPathComponent.range(of: #"^\d{4}-\d{2}-\d{2}$"#, options: .regularExpression) != nil else { continue }
            for file in try fm.contentsOfDirectory(at: day, includingPropertiesForKeys: Array(keys)) where ["txt", "md"].contains(file.pathExtension.lowercased()) {
                let info = try file.resourceValues(forKeys: keys)
                guard info.isRegularFile == true, info.isSymbolicLink != true,
                      let text = try? String(contentsOf: file, encoding: .utf8),
                      let first = text.split(separator: "\n", maxSplits: 1).first, first.hasPrefix("邮件编号：") else { continue }
                let uid = first.dropFirst("邮件编号：".count).trimmingCharacters(in: .whitespaces)
                guard !uid.isEmpty, uid.allSatisfy(\.isNumber) else { continue }
                try fm.removeItem(at: file)
                let metadata = file.deletingPathExtension().appendingPathExtension("mail.json")
                if let properties = try? metadata.resourceValues(forKeys: keys), properties.isRegularFile == true,
                   properties.isSymbolicLink != true { try fm.removeItem(at: metadata) }
            }
            if try fm.contentsOfDirectory(atPath: day.path).isEmpty { try fm.removeItem(at: day) }
        }
    }
    static func removeUserData(base: URL, preserving settings: MailSettings?) throws {
        let fm = FileManager.default
        // Encode before deleting anything, so invalid settings cannot cause partial preservation.
        let bytes = try settings.map { try JSONEncoder().encode($0) }
        if fm.fileExists(atPath: base.path) { try fm.trashItem(at: base, resultingItemURL: nil) }
        if let bytes {
            try fm.createDirectory(at: base, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
            try bytes.write(to: base.appendingPathComponent("settings.json"), options: .atomic)
            try fm.setAttributes([.posixPermissions: 0o600], ofItemAtPath: base.appendingPathComponent("settings.json").path)
        }
    }
}

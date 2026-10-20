import SwiftUI
import AppKit

/// Language catalogs are opt-in downloads. Existing reports, mailbox identities and secrets stay untouched.
final class AppLanguage: ObservableObject {
    static let shared = AppLanguage()
    static let supported = ["zh", "en", "es"]
    static let appNames = ["邮件小秘书", "Mail Secretary", "Email Assistant", "Asistente de correo electrónico"]
    @Published private(set) var code: String
    @Published private(set) var isDownloading = false
    private var exact: [String: String] = [:]
    private var templates: [(NSRegularExpression, String)] = []
    private var guides: [String: String] = [:]
    private let base: URL
    private let startupLanguage: String
    private var startupHandled = false

    struct Catalog {
        let exact: [String: String]
        let templates: [(NSRegularExpression, String)]
        let guides: [String: String]
    }
    struct LanguageError: LocalizedError {
        let message: String
        var errorDescription: String? { message }
    }
    static func detect(_ preferred: [String]) -> String {
        let first = preferred.first?.lowercased() ?? "en"
        if first.hasPrefix("zh") { return "zh" }
        return first.hasPrefix("es") ? "es" : "en"
    }
    var canPersistInitialLanguage: Bool { code == startupLanguage && isInstalled(startupLanguage) }
    var localeIdentifier: String { ["zh": "zh_CN", "en": "en_US", "es": "es_ES"][code] ?? "en_US" }
    static func appName(_ language: String) -> String {
        ["zh": "邮件小秘书", "en": "Email Assistant", "es": "Asistente de correo electrónico"][language] ?? "Email Assistant"
    }
    private init() {
        let args = CommandLine.arguments
        let fixture = args.firstIndex(of: "--fixture").flatMap { $0 + 1 < args.count ? args[$0 + 1] : nil }
        base = fixture.map { URL(fileURLWithPath: $0) } ?? FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/BensonMail")
        let saved = (try? Data(contentsOf: base.appendingPathComponent("settings.json"))).flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String: Any] }
        let desired: String
        if let i = args.firstIndex(of: "--ui-language"), i + 1 < args.count, Self.supported.contains(args[i + 1]) { desired = args[i + 1] }
        else if args.contains("--self-test") { desired = "zh" }
        else if let value = saved?["ui_language"] as? String, Self.supported.contains(value) { desired = value }
        else { desired = Self.detect(Locale.preferredLanguages) }
        startupLanguage = desired
        code = "zh"
        if let catalog = catalog(for: desired) { install(catalog, language: desired) }
    }
    func catalog(for language: String) -> Catalog? {
        guard Self.supported.contains(language) else { return nil }
        let local = base.appendingPathComponent("languages/\(language).json")
        let bundled = Bundle.main.resourceURL?.appendingPathComponent("languages/\(language).json")
        for url in [local, bundled].compactMap({ $0 }) {
            guard let data = try? Data(contentsOf: url), data.count <= 8 * 1024 * 1024,
                  let row = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                  row["schema_version"] as? Int == 1, row["language"] as? String == language,
                  row["platform"] as? String == "macos", let exact = row["exact"] as? [String: String],
                  let guideTexts = row["guides"] as? [String: String],
                  let mail = guideTexts["mail_account"], !mail.isEmpty,
                  let quick = guideTexts["quick_start"], !quick.isEmpty,
                  let patterns = row["templates"] as? [[String: Any]] else { continue }
            var result: [(NSRegularExpression, String)] = []
            var valid = true
            for pattern in patterns {
                guard let source = pattern["pattern"] as? String,
                      let regex = try? NSRegularExpression(pattern: source, options: .dotMatchesLineSeparators),
                      let target = pattern["en"] as? String else { valid = false; break }
                result.append((regex, target))
            }
            if valid { return Catalog(exact: exact, templates: result, guides: guideTexts) }
        }
        return nil
    }
    func isInstalled(_ language: String) -> Bool { catalog(for: language) != nil }
    private func install(_ catalog: Catalog, language: String) {
        exact = catalog.exact; templates = catalog.templates; guides = catalog.guides; code = language
    }
    /// Small built-in bootstrap catalog is limited to the download dialog, so English/Spanish users can install their first language.
    static func bootstrap(_ text: String, language: String) -> String {
        let en = [
            "你没有下载这个语言，是否现在下载？": "You have not downloaded this language. Download it now?",
            "下载语言": "Download language", "下载": "Download", "取消": "Cancel", "重试": "Retry", "稍后": "Later",
            "语言下载失败": "Language download failed", "正在下载语言…": "Downloading language…",
            "下载简体中文": "Download Simplified Chinese", "下载英文": "Download English", "下载西班牙文": "Download Spanish",
            "界面语言": "Interface language", "语言更改立即生效，下次打开时保留。": "Language changes apply immediately and are remembered.",
            "语言包已安装": "Language pack installed", "语言包尚未下载": "Language pack not downloaded",
            "下载失败，请检查网络后重试。": "Download failed. Check your internet connection and retry.",
            "无法读取下载的语言包，请重试或检查文件权限。": "Cannot read the downloaded language pack. Retry or check file permissions.",
            "请先下载当前语言包，再打开指南。": "Download the current language pack before opening the guide.",
            "好": "OK", "帮助": "Help", "使用指南": "User guide", "如何获取授权码？": "How do I get an authorization code?",
            "检查更新": "Check for updates", "关于邮件小秘书": "About Email Assistant",
            "前往 GitHub 下载最新版": "Download the latest version from GitHub"
        ]
        let es = [
            "你没有下载这个语言，是否现在下载？": "No has descargado este idioma. ¿Quieres descargarlo ahora?",
            "下载语言": "Descargar idioma", "下载": "Descargar", "取消": "Cancelar", "重试": "Reintentar", "稍后": "Más tarde",
            "语言下载失败": "Error al descargar el idioma", "正在下载语言…": "Descargando idioma…",
            "下载简体中文": "Descargar chino simplificado", "下载英文": "Descargar inglés", "下载西班牙文": "Descargar español",
            "界面语言": "Idioma de la interfaz", "语言更改立即生效，下次打开时保留。": "El cambio de idioma se aplica al instante y se guarda.",
            "语言包已安装": "Paquete de idioma instalado", "语言包尚未下载": "Paquete de idioma sin descargar",
            "下载失败，请检查网络后重试。": "No se pudo descargar. Comprueba la conexión a Internet y vuelve a intentarlo.",
            "无法读取下载的语言包，请重试或检查文件权限。": "No se puede leer el paquete descargado. Reintenta o revisa los permisos de los archivos.",
            "请先下载当前语言包，再打开指南。": "Descarga el paquete del idioma actual antes de abrir la guía.",
            "好": "Aceptar", "帮助": "Ayuda", "使用指南": "Guía de uso", "如何获取授权码？": "¿Cómo obtener un código de autorización?",
            "检查更新": "Buscar actualizaciones", "关于邮件小秘书": "Acerca de Asistente de correo electrónico",
            "前往 GitHub 下载最新版": "Descargar la última versión desde GitHub"
        ]
        if text == "邮件小秘书" { return appName(language) }
        return (language == "es" ? es[text] : language == "en" ? en[text] : nil) ?? text
    }
    func translate(_ text: String) -> String {
        if text == "邮件小秘书" { return Self.appName(code) }
        guard code != "zh" else { return text }
        if let value = exact[text] { return value }
        if let value = SenderPolicyLocalization.translate(text, language: code) { return value }
        if text.contains("邮箱连接失败："), text.contains("\n服务器："), text.contains("\n阶段：") {
            let labels = code == "es" ? ["服务器：": "Servidor: ", "阶段：": "Etapa: ", "具体原因：": "Detalles: "] : ["服务器：": "Server: ", "阶段：": "Stage: ", "具体原因：": "Details: "]
            return text.components(separatedBy: "\n").map { line in
                if let marker = line.range(of: "邮箱连接失败：") {
                    let hint = String(line[marker.upperBound...])
                    return String(line[..<marker.lowerBound]) + (code == "es" ? "Error de conexión al correo: " : "Email connection failed: ") + (exact[hint] ?? hint)
                }
                for (source, target) in labels where line.hasPrefix(source) {
                    let value = String(line.dropFirst(source.count))
                    return target + (exact[value] ?? value).replacingOccurrences(of: "[已隐藏凭据]", with: code == "es" ? "[credenciales ocultas]" : "[credentials hidden]")
                }
                return line
            }.joined(separator: "\n")
        }
        for (regex, translated) in templates {
            guard let match = regex.firstMatch(in: text, range: NSRange(text.startIndex..., in: text)) else { continue }
            var value = translated
            let placeholders = try! NSRegularExpression(pattern: #"\{(\d+)\}"#)
            for slot in placeholders.matches(in: translated, range: NSRange(translated.startIndex..., in: translated)).reversed() {
                guard let numberRange = Range(slot.range(at: 1), in: translated), let number = Int(translated[numberRange]),
                      number + 1 < match.numberOfRanges, let capture = Range(match.range(at: number + 1), in: text),
                      let target = Range(slot.range, in: value) else { continue }
                let captured = String(text[capture])
                let replacement = text.hasPrefix("AI 接口") && number == 0
                    ? (exact[captured] ?? SenderPolicyLocalization.translate(captured, language: code) ?? captured) : captured
                value.replaceSubrange(target, with: replacement)
            }
            return value
        }
        return Self.bootstrap(text, language: code)
    }
    @MainActor private func activate(_ value: String, catalog: Catalog) throws {
        let store = MailStore.shared
        let old = store.settings.ui_language
        store.settings.ui_language = value
        do { try store.save() }
        catch { store.settings.ui_language = old; throw error }
        install(catalog, language: value)
        DispatchQueue.main.async { MailHelp.refreshTitle() }
        for window in NSApp.windows where Self.appNames.contains(window.title) { window.title = T("邮件小秘书") }
    }
    /// Internal installed-only switch. Production controls use requestSelect, which asks before a network download.
    @MainActor func select(_ value: String) {
        guard let catalog = catalog(for: value) else { return }
        do { try activate(value, catalog: catalog) }
        catch { MailStore.shared.problem = T("语言设置保存失败：") + error.localizedDescription }
    }
    @MainActor @discardableResult
    func change(to value: String, confirmDownload: () -> Bool, download: (String) async throws -> Void) async throws -> Bool {
        guard Self.supported.contains(value), !isDownloading else { return false }
        isDownloading = true
        defer { isDownloading = false }
        if let catalog = catalog(for: value) { try activate(value, catalog: catalog); return true }
        guard confirmDownload() else { return false }
        try await download(value)
        guard let catalog = catalog(for: value) else {
            throw LanguageError(message: Self.bootstrap("无法读取下载的语言包，请重试或检查文件权限。", language: code))
        }
        try activate(value, catalog: catalog)
        return true
    }
    @MainActor func requestSelect(_ value: String, promptLanguage: String? = nil) {
        guard !isDownloading else { return }
        let dialogLanguage = promptLanguage ?? code
        Task { @MainActor in
            var retry = true
            while retry {
                retry = false
                do {
                    try await change(to: value, confirmDownload: {
                        let alert = NSAlert()
                        alert.messageText = Self.bootstrap("下载语言", language: dialogLanguage)
                        alert.informativeText = Self.bootstrap("你没有下载这个语言，是否现在下载？", language: dialogLanguage) + "\n\n" + ["zh": "简体中文", "en": "English", "es": "Español"][value, default: value]
                        alert.addButton(withTitle: Self.bootstrap("下载", language: dialogLanguage))
                        alert.addButton(withTitle: Self.bootstrap("取消", language: dialogLanguage))
                        NSApp.activate(ignoringOtherApps: true)
                        return alert.runModal() == .alertFirstButtonReturn
                    }, download: { language in try await Self.download(language, base: self.base) })
                } catch {
                    let alert = NSAlert()
                    alert.alertStyle = .warning
                    alert.messageText = Self.bootstrap("语言下载失败", language: dialogLanguage)
                    alert.informativeText = Self.bootstrap("下载失败，请检查网络后重试。", language: dialogLanguage) + "\n\n" + error.localizedDescription
                    alert.addButton(withTitle: Self.bootstrap("重试", language: dialogLanguage))
                    alert.addButton(withTitle: Self.bootstrap("稍后", language: dialogLanguage))
                    retry = alert.runModal() == .alertFirstButtonReturn
                }
            }
        }
    }
    @MainActor func ensureStartupLanguage() {
        guard !startupHandled, !CommandLine.arguments.contains("--self-test") else { return }
        startupHandled = true
        if !isInstalled(startupLanguage) { requestSelect(startupLanguage, promptLanguage: startupLanguage) }
    }
    private static func download(_ language: String, base: URL) async throws {
        let executable = ServiceInstaller.worker
        let basePath = base.path
        try await Task.detached(priority: .userInitiated) {
            let process = Process()
            let output = Pipe()
            process.executableURL = executable
            process.arguments = ["--home", basePath, "--download-language", language]
            process.standardOutput = output
            // The worker returns a redacted, structured error; do not expose arbitrary stderr to the UI.
            process.standardError = FileHandle.nullDevice
            try process.run()
            let bytes = output.fileHandleForReading.readDataToEndOfFile()
            process.waitUntilExit()
            guard let result = try? JSONSerialization.jsonObject(with: bytes) as? [String: Any],
                  result["ok"] as? Bool == true, process.terminationStatus == 0 else {
                let result = (try? JSONSerialization.jsonObject(with: bytes)) as? [String: Any]
                let reason = result?["error"] as? String
                throw LanguageError(message: reason ?? "Language download failed (worker exit \(process.terminationStatus)).")
            }
        }.value
    }
    func guideURL(_ kind: String, language: String? = nil) -> URL? {
        let target = language ?? code
        guard Self.supported.contains(target), let text = catalog(for: target)?.guides[kind], !text.isEmpty else { return nil }
        let name = kind == "mail_account" ? "Mail-account-setup-\(target).txt" : "Quick-start-\(target).txt"
        let directory = base.appendingPathComponent("languages/guides/\(target)")
        let file = directory.appendingPathComponent(name)
        do {
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            try Data(text.utf8).write(to: file, options: .atomic)
            return file
        } catch { return nil }
    }
}
func T(_ text: String) -> String { AppLanguage.shared.translate(text) }

struct LanguageSettings: View {
    @ObservedObject private var language = AppLanguage.shared
    private let choices = [("zh", "简体中文", "下载简体中文"), ("en", "English", "下载英文"), ("es", "Español", "下载西班牙文")]
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Picker(T("界面语言"), selection: Binding(get: { language.code }, set: { language.requestSelect($0) })) {
                ForEach(choices, id: \.0) { choice in Text(choice.1).tag(choice.0) }
            }.accessibilityIdentifier("ui-language").disabled(language.isDownloading)
            ForEach(choices, id: \.0) { choice in
                HStack {
                    Text(choice.1)
                    Spacer()
                    if language.isInstalled(choice.0) { Text(T("语言包已安装")).foregroundStyle(.secondary) }
                    else { Button(T(choice.2)) { language.requestSelect(choice.0) }.disabled(language.isDownloading) }
                }.font(.caption)
            }
            if language.isDownloading { ProgressView(T("正在下载语言…")).controlSize(.small) }
            Text(T("语言更改立即生效，下次打开时保留。")).font(.caption).foregroundStyle(.secondary)
        }
    }
}

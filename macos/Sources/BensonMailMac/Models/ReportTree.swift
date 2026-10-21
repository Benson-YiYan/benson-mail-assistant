import Foundation

/// The visible tree is derived from the filtered index, so search and filters keep
/// their normal scope while folder counts only include matching reports.
enum ReportTree {
    /// Upgraded apps may still have an older downloaded catalog. Keep new labels
    /// readable before the user downloads a refreshed language pack.
    static func translate(_ text: String, language: String) -> String? {
        let labels: [String: (String, String)] = [
            "报告树": ("Report tree", "Árbol de informes"),
            "按邮箱、日期、发件人逐层浏览；搜索和筛选仍然生效。": ("Browse by account, date and sender; search and filters still apply.", "Navega por cuenta, fecha y remitente; la búsqueda y los filtros siguen activos."),
            "上一级": ("Up one level", "Subir un nivel"),
            "全部邮箱": ("All accounts", "Todas las cuentas"),
            "选择邮箱": ("Choose an account", "Elige una cuenta"),
            "选择日期": ("Choose a date", "Elige una fecha"),
            "选择发件人": ("Choose a sender", "Elige un remitente"),
            "未识别的邮箱": ("Unidentified account", "Cuenta sin identificar"),
            "未识别的发件人": ("Unidentified sender", "Remitente sin identificar"),
            "报告目录整理失败，原报告仍保留；请检查运行记录。": ("Could not organize report folders. Original reports are retained; check the activity log.", "No se pudieron organizar las carpetas de informes. Se conservan los originales; consulta el registro de actividad.")
        ]
        guard let row = labels[text] else { return nil }
        return language == "es" ? row.1 : language == "en" ? row.0 : nil
    }
    struct Folder: Identifiable {
        let key: String
        let count: Int
        var id: String { key }
    }
    static func key(_ report: Report, level: Int) -> String {
        switch level {
        case 0: return report.mailboxAccount
        case 1: return report.dateLabel
        default: return report.senderAddress
        }
    }
    static func reports(_ reports: [Report], in path: [String]) -> [Report] {
        reports.filter { report in path.enumerated().allSatisfy { key(report, level: $0.offset) == $0.element } }
    }
    static func folders(_ reports: [Report], in path: [String]) -> [Folder] {
        guard path.count < 3 else { return [] }
        let grouped = Dictionary(grouping: self.reports(reports, in: path)) { key($0, level: path.count) }
        return grouped.map { Folder(key: $0.key, count: $0.value.count) }.sorted {
            path.count == 1 ? $0.key > $1.key : $0.key.localizedStandardCompare($1.key) == .orderedAscending
        }
    }
    static func validPath(_ path: [String], in reports: [Report]) -> [String] {
        var valid: [String] = []
        for component in path.prefix(3) {
            guard folders(reports, in: valid).contains(where: { $0.key == component }) else { break }
            valid.append(component)
        }
        return valid
    }
}

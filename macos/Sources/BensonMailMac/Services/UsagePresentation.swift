import Foundation
import CoreFoundation

@MainActor enum UsagePresentation {
    /// Each value must be reported in its own right. A zero unknown-call counter
    /// never makes an absent token count or cost known.
    static func formatted(_ raw: Any?, allowNegative: Bool = false) -> String {
        let number: NSNumber
        if let value = raw as? NSNumber, CFGetTypeID(value) != CFBooleanGetTypeID() { number = value }
        else if let value = raw as? String, let parsed = Double(value.trimmingCharacters(in: .whitespacesAndNewlines)), parsed.isFinite {
            number = NSDecimalNumber(string: value.trimmingCharacters(in: .whitespacesAndNewlines), locale: Locale(identifier: "en_US_POSIX"))
        } else { return T("未知") }
        guard number.doubleValue.isFinite, allowNegative || number.doubleValue >= 0 else { return T("未知") }
        let formatter = NumberFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.numberStyle = .decimal; formatter.usesGroupingSeparator = true
        formatter.groupingSize = 3; formatter.minimumFractionDigits = 0; formatter.maximumFractionDigits = 8
        return formatter.string(from: number) ?? T("未知")
    }
    static func number(_ record: [String: Any], _ key: String) -> String { formatted(record[key]) }
    static func cost(_ record: [String: Any], amountKey: String = "estimated_cost", currencyKey: String = "currency", allowNegative: Bool = false) -> String {
        let amount = formatted(record[amountKey], allowNegative: allowNegative)
        guard amount != T("未知"), let currency = record[currencyKey] as? String,
              !currency.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return T("未知") }
        return amount + " " + currency
    }
    static func balanceStatus(_ record: [String: Any]) -> String {
        switch record["status"] as? String {
        case "ok": return T("账户余额查询成功。")
        case "unsupported": return T("此服务暂不支持账户余额查询。")
        case "not_api": return T("当前 AI 方式不支持账户余额查询，请使用受支持的 API 服务。")
        default: return balanceError(record["error_code"] as? String)
        }
    }
    private static func balanceError(_ code: String?) -> String {
        switch code {
        case "permission": return T("当前 API Key 没有查询余额的权限；AI 调用仍可能正常。")
        case "authentication": return T("API Key 认证失败，请检查已保存的 Key。")
        case "missing_key": return T("尚未保存 API Key，请在 AI 服务中配置后重试。")
        case "invalid_key": return T("保存的 API Key 格式无效，请检查后重新保存。")
        case "credentials": return T("无法读取已保存的 AI 配置或 API Key，请检查文件和钥匙串权限后重试。")
        case "timeout": return T("账户余额查询超时，请检查网络和代理后重试。")
        case "rate_limit": return T("余额查询过于频繁，请稍后重试。")
        case "tls": return T("余额查询的安全连接失败，请检查代理、系统时间和网络。")
        case "dns": return T("无法解析余额服务地址，请检查网络和 DNS。")
        case "server", "http": return T("余额服务返回错误，请稍后重试或查看服务商状态。")
        case "redirect": return T("余额接口返回了不允许的重定向，查询已停止。")
        case "invalid_response", "response_too_large": return T("服务商返回的余额数据无效或过大，请稍后重试。")
        case "internal": return T("账户余额查询失败，请稍后重试。")
        default: return T("账户余额查询失败，请检查网络和服务商配置后重试。")
        }
    }
    static func provider(_ record: [String: Any]) -> String {
        switch (record["provider"] as? String)?.lowercased() {
        case "deepseek": return "DeepSeek"
        case "openrouter": return "OpenRouter"
        case "codex": return "Codex"
        case "deepseek_harness": return "DeepSeek Harness"
        default: return T("当前 AI 服务")
        }
    }
    static func checkedAt(_ record: [String: Any], locale: String) -> String {
        guard let raw = record["checked_at"] as? String else { return T("未知") }
        let iso = ISO8601DateFormatter(); iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        var date = iso.date(from: raw)
        if date == nil { iso.formatOptions = [.withInternetDateTime]; date = iso.date(from: raw) }
        guard let date else { return T("未知") }
        let formatter = DateFormatter(); formatter.locale = Locale(identifier: locale)
        formatter.dateStyle = .medium; formatter.timeStyle = .medium
        return formatter.string(from: date)
    }
}

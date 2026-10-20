import Foundation
import CoreFoundation

@MainActor enum UsagePresentation {
    /// Each value must be reported in its own right. A zero unknown-call counter
    /// never makes an absent token count or cost known.
    static func number(_ record: [String: Any], _ key: String) -> String {
        guard let number = record[key] as? NSNumber,
              CFGetTypeID(number) != CFBooleanGetTypeID(), number.doubleValue.isFinite,
              number.doubleValue >= 0 else { return T("未知") }
        let formatter = NumberFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.numberStyle = .decimal; formatter.usesGroupingSeparator = true
        formatter.groupingSize = 3; formatter.minimumFractionDigits = 0; formatter.maximumFractionDigits = 8
        return formatter.string(from: number) ?? T("未知")
    }
    static func cost(_ record: [String: Any]) -> String {
        let amount = number(record, "estimated_cost")
        guard amount != T("未知"), let currency = record["currency"] as? String,
              !currency.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return T("未知") }
        return amount + " " + currency
    }
}

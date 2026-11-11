import SwiftUI

/// Native, content-sized chat tables avoid nested web views in the conversation.
enum ChatMarkdown {
    enum Block: Equatable {
        case text(String)
        case table([[String]])
    }

    static func cells(_ line: String) -> [String]? {
        let value = line.trimmingCharacters(in: .whitespaces)
        guard value.contains("|") else { return nil }
        var result: [String] = [], cell = "", escaped = false, code = false
        for character in value {
            if escaped {
                if character != "|" { cell.append("\\") }
                cell.append(character); escaped = false
            } else if character == "\\" { escaped = true
            } else if character == "`" { code.toggle(); cell.append(character)
            } else if character == "|" && !code {
                result.append(cell.trimmingCharacters(in: .whitespaces)); cell = ""
            } else { cell.append(character) }
        }
        if escaped { cell.append("\\") }
        result.append(cell.trimmingCharacters(in: .whitespaces))
        if value.hasPrefix("|") { result.removeFirst() }
        if value.hasSuffix("|"), result.last == "" { result.removeLast() }
        return result
    }

    static func blocks(_ text: String) -> [Block] {
        let lines = text.components(separatedBy: .newlines)
        var result: [Block] = [], prose: [String] = [], index = 0
        var fence: String?
        func flush() {
            if !prose.isEmpty { result.append(.text(prose.joined(separator: "\n"))); prose = [] }
        }
        while index < lines.count {
            let trimmed = lines[index].trimmingCharacters(in: .whitespaces)
            if trimmed.hasPrefix("```") || trimmed.hasPrefix("~~~") {
                let marker = String(trimmed.prefix(3))
                if fence == marker { fence = nil } else if fence == nil { fence = marker }
                prose.append(lines[index]); index += 1; continue
            }
            if fence == nil, index + 1 < lines.count,
               let header = cells(lines[index]), !header.isEmpty,
               let separator = cells(lines[index + 1]), separator.count == header.count,
               separator.allSatisfy({ $0.range(of: #"^:?-{3,}:?$"#, options: .regularExpression) != nil }) {
                flush()
                var rows = [header]
                index += 2
                while index < lines.count, let row = cells(lines[index]), !lines[index].isEmpty {
                    rows.append(Array((row + Array(repeating: "", count: header.count)).prefix(header.count)))
                    index += 1
                }
                result.append(.table(rows))
            } else { prose.append(lines[index]); index += 1 }
        }
        flush()
        return result
    }
}

struct ChatMarkdownView: View {
    let text: String
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            ForEach(Array(ChatMarkdown.blocks(text).enumerated()), id: \.offset) { _, block in
                switch block {
                case .text(let content):
                    Text(.init(content)).textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                case .table(let rows):
                    ScrollView(.horizontal) {
                        Grid(alignment: .topLeading, horizontalSpacing: 0, verticalSpacing: 0) {
                            ForEach(rows.indices, id: \.self) { row in
                                GridRow {
                                    ForEach(rows[row].indices, id: \.self) { column in
                                        Text(.init(rows[row][column]))
                                            .fontWeight(row == 0 ? .semibold : .regular)
                                            .textSelection(.enabled)
                                            .frame(minWidth: 100, maxWidth: 280, alignment: .leading)
                                            .padding(8)
                                            .frame(maxHeight: .infinity, alignment: .topLeading)
                                            .background(row == 0 ? Color.primary.opacity(0.08) : Color.clear)
                                            .border(Color.secondary.opacity(0.3), width: 0.5)
                                    }
                                }
                            }
                        }.fixedSize(horizontal: true, vertical: false)
                    }.accessibilityIdentifier("mail-chat-table")
                }
            }
        }
    }
}

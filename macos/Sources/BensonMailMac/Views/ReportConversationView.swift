import AppKit
import SwiftUI

struct ReportConversationView: View {
    @ObservedObject private var language = AppLanguage.shared
    @ObservedObject var conversation: ReportConversationStore
    let path: String
    private var state: ReportConversationState { conversation.state(path) }
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Label(T("对邮件提问"), systemImage: "bubble.left.and.bubble.right").font(.headline)
                Spacer()
                Button(T("恢复对话"), systemImage: "arrow.clockwise") { Task { await conversation.load(path, force: true) } }.disabled(state.busy)
            }
            if state.compressed {
                Label(T("较早的对话已压缩为摘要，后续提问会继续使用摘要与最近的消息。"), systemImage: "text.alignleft")
                    .font(.caption).foregroundStyle(.secondary)
            }
            ScrollViewReader { scroll in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 12) {
                        if state.messages.isEmpty {
                            Text(T("可以针对这封邮件和附件继续提问，也可以添加文件。对话会自动保存。"))
                                .font(.callout).foregroundStyle(.secondary).frame(maxWidth: .infinity, alignment: .leading)
                        }
                        ForEach(state.messages) { message in
                            VStack(alignment: .leading, spacing: 5) {
                                Label(T(message.role == "user" ? "你" : message.role == "assistant" ? "AI 助手" : "对话摘要"), systemImage: message.role == "user" ? "person.crop.circle" : "sparkles")
                                    .font(.caption.bold()).foregroundStyle(.secondary)
                                Text(.init(message.content)).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading)
                                ForEach(Array(message.files.enumerated()), id: \.offset) { _, file in
                                    Label(URL(fileURLWithPath: file).lastPathComponent, systemImage: "paperclip").font(.caption).foregroundStyle(.secondary)
                                }
                            }.padding(10).background(message.role == "user" ? Color.accentColor.opacity(0.07) : Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: 8))
                        }
                        Color.clear.frame(height: 1).id("conversation-bottom")
                    }.padding(.trailing, 6)
                }.onChange(of: state.messages.count) { _, _ in scroll.scrollTo("conversation-bottom", anchor: .bottom) }
            }.frame(minHeight: 75, maxHeight: .infinity)
            if !state.error.isEmpty {
                HStack(alignment: .top) {
                    Image(systemName: "exclamationmark.triangle").foregroundStyle(.orange)
                    Text(T(state.error)).font(.caption).textSelection(.enabled)
                    Spacer()
                }.accessibilityIdentifier("mail-chat-error")
            }
            if !state.files.isEmpty {
                ScrollView(.horizontal) {
                    HStack {
                        ForEach(state.files, id: \.self) { file in
                            HStack(spacing: 5) {
                                Label(URL(fileURLWithPath: file).lastPathComponent, systemImage: "paperclip").lineLimit(1)
                                Button { conversation.removeFile(file, for: path) } label: { Image(systemName: "xmark.circle.fill") }
                                    .buttonStyle(.plain).accessibilityLabel(T("移除附件") + " " + URL(fileURLWithPath: file).lastPathComponent)
                            }.font(.caption).padding(5).background(.quaternary, in: RoundedRectangle(cornerRadius: 5))
                        }
                    }
                }.disabled(state.busy)
            }
            TextField(T("输入有关这封邮件的问题…"), text: Binding(get: { state.draft }, set: { conversation.draft($0, for: path) }), axis: .vertical)
                .lineLimit(2...4).textFieldStyle(.roundedBorder).disabled(state.busy).accessibilityIdentifier("mail-chat-question")
            HStack {
                Button(T("添加附件"), systemImage: "paperclip") { conversation.chooseFiles(for: path) }.disabled(state.busy)
                if state.busy { ProgressView().controlSize(.small); Text(T(state.operation)).font(.caption).foregroundStyle(.secondary) }
                Spacer()
                Button(T("发送问题"), systemImage: "paperplane.fill") { Task { await conversation.send(path) } }
                    .disabled(state.busy || (state.draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && state.files.isEmpty))
                    .keyboardShortcut(.return, modifiers: [.command])
                    .accessibilityIdentifier("mail-chat-send")
            }
        }.padding(.top, 10).frame(maxWidth: .infinity, maxHeight: .infinity).task(id: path) { await conversation.load(path) }
    }
}

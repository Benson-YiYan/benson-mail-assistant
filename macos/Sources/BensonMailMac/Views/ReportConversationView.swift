import AppKit
import SwiftUI

private struct ChatComposer: NSViewRepresentable {
    @Binding var text: String
    let enabled: Bool
    let enterToSend: Bool
    let send: () -> Void

    func makeNSView(context: Context) -> NSScrollView {
        let scroll = NSScrollView()
        scroll.hasVerticalScroller = true
        scroll.drawsBackground = false
        let editor = ChatComposerTextView()
        editor.delegate = context.coordinator
        editor.font = .systemFont(ofSize: NSFont.systemFontSize)
        editor.isRichText = false
        editor.isAutomaticQuoteSubstitutionEnabled = false
        editor.textContainerInset = NSSize(width: 5, height: 5)
        editor.enterToSend = enterToSend
        editor.send = send
        scroll.documentView = editor
        return scroll
    }

    func updateNSView(_ scroll: NSScrollView, context: Context) {
        guard let editor = scroll.documentView as? ChatComposerTextView else { return }
        editor.enterToSend = enterToSend
        editor.send = send
        editor.isEditable = enabled
        editor.isSelectable = true
        if editor.string != text {
            editor.string = text
        }
    }

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    final class Coordinator: NSObject, NSTextViewDelegate {
        var parent: ChatComposer
        init(_ parent: ChatComposer) { self.parent = parent }
        func textDidChange(_ notification: Notification) {
            guard let editor = notification.object as? NSTextView else { return }
            parent.text = editor.string
        }
    }
}

private final class ChatComposerTextView: NSTextView {
    var enterToSend = false
    var send: (() -> Void)?

    override func keyDown(with event: NSEvent) {
        let isEnter = event.keyCode == 36 || event.keyCode == 76
        if enterToSend, isEnter {
            if event.modifierFlags.contains(.shift) {
                super.keyDown(with: event)
            } else {
                send?()
            }
            return
        }
        super.keyDown(with: event)
    }
}

struct ReportConversationView: View {
    @ObservedObject private var language = AppLanguage.shared
    @ObservedObject var conversation: ReportConversationStore
    let path: String
    let enterToSend: Bool
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
            ChatComposer(text: Binding(get: { state.draft }, set: { conversation.draft($0, for: path) }),
                         enabled: !state.busy, enterToSend: enterToSend) {
                Task { await conversation.send(path) }
            }
                .frame(minHeight: 42, maxHeight: 90)
                .overlay(alignment: .topLeading) {
                    if state.draft.isEmpty {
                        Text(T("输入有关这封邮件的问题…")).foregroundStyle(.secondary)
                            .padding(.horizontal, 10).padding(.vertical, 9).allowsHitTesting(false)
                    }
                }
                .overlay(RoundedRectangle(cornerRadius: 5).stroke(Color(nsColor: .separatorColor)))
                .accessibilityIdentifier("mail-chat-question")
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

# Email Assistant

[简体中文](README.md) · [Español](README.es.md) · [Download](https://github.com/Benson-YiYan/benson-mail-assistant/releases/latest)

Turn each new email into six sections: **notice, sender, summary, actions, attachment contents and a suggested reply**.

Native Windows and Mac interfaces, multiple mailboxes and your choice of AI. **Checks without new mail or pending retries do not call AI. Replies are never sent automatically.**

## Download

Download an installer from the [latest release](https://github.com/Benson-YiYan/benson-mail-assistant/releases/latest). You do not need the source code or a terminal.

| Computer | Package | Requirements |
| --- | --- | --- |
| Windows x64 | `BensonMail-Windows-x64-Setup-….exe` | Windows 10 / 11 |
| Apple silicon Mac | `BensonMail-Mac-AppleSilicon-….dmg` | macOS 14+ |
| Intel Mac | `BensonMail-Mac-Intel-….dmg` | macOS 14+ |

Windows and Mac packages in one release may have different version numbers. Verify downloads using `SHA256SUMS.txt`.

- **Windows:** run Setup and choose the installation folder and shortcuts. Existing installations can be upgraded in place.
- **Mac:** open the matching DMG and drag the app into Applications. Check your processor in About This Mac.
- Windows Setup checks .NET 8 and Windows App Runtime 1.8 (WinUI 3), asks for confirmation before downloading missing components, and reuses compatible installations. Mac includes its required runtime. Neither platform requires Python or Homebrew setup.
- Installers are not publisher code-signed, and the Mac app is not Apple-notarized. Verify the download source and follow the operating system's approval controls if prompted.

## Get started

1. **Connect a mailbox.** Choose a preset or custom IMAP settings, enable IMAP with your provider, and enter the required app password, authorization code or OAuth2 token. A setup guide is available in the app.
2. **Choose AI.** Configure a Chat Completions-compatible API base URL, key and model, or use your installed and configured Codex / DeepSeek Harness. Harness is not bundled, and no free AI service is included. API mode does not require Codex.
3. **Choose a report folder and start monitoring.** Checks default to 60 seconds and can be customized. Empty checks do not call AI.

**A newly added mailbox's first check records a starting point; it does not analyze your entire old inbox.** After that, monitoring catches up on messages received while paused or powered off, provided they remain in the selected folder.

## Features

- Multiple mailboxes, provider presets and custom IMAP host, port and encryption.
- Six-section Markdown reports, with legacy TXT viewing support.
- Local search across message bodies, senders and attachment names; date, sender and attachment filters.
- Simplified Chinese, English and Spanish interfaces and new reports; existing reports remain unchanged.
- Tray/menu bar operation, configurable intervals and report locations.
- In-app update downloads: when several sources are available, bounded speed probes select a faster route; network failures try another source. SHA256 is verified before installation. Uninstall can retain settings and reports.

Attachment analysis depends on extractable text; scanned images and encrypted documents may not be readable. Search covers locally saved mail data and reports, not your entire remote inbox.

## Screenshots

Screenshots show synthetic test messages, not real user mail.

![Windows report view](docs/images/windows.png)

![Mac report view](docs/images/macos.png)

## Data and limitations

Your selected AI service receives message text and readable attachment text. Choose a service suitable for that data. Credentials use operating system protection; never include credentials or private messages in issues. AI connection tests may use provider credits.

OAuth2 access tokens must currently be supplied and renewed manually. Windows installer/update flows were tested on a GitHub Windows runner. Intel Mac tests ran under Rosetta, not on physical Intel hardware.

## Guides and development

| Platform | User guide | Build and test |
| --- | --- | --- |
| Windows | [English](windows/README.en.md) / [中文](windows/README.md) / [Español](windows/README.es.md) | [Development](windows/docs/DEVELOPMENT.md) |
| Mac | [English](macos/README.en.md) / [中文](macos/README.md) / [Español](macos/README.es.md) | [Development](macos/docs/DEVELOPMENT.md) |

Source lives in `windows/` and `macos/`. Public build adaptations may differ from the commits used for the verified downloadable packages; release notes identify their versions and test scope.

[Report a problem](https://github.com/Benson-YiYan/benson-mail-assistant/issues) with your OS version, app version and sanitized error details.

If this little secretary saves you time, a ⭐ is welcome.

## Languages and language packs

The interface, installer and uninstaller support **Simplified Chinese, English and Spanish**. First use selects Chinese for Chinese system languages, Spanish for Spanish system languages and English otherwise. You can change it in General settings. Windows Setup offers **Download Simplified Chinese**, **Download English** and **Download Spanish**.

Only installed language packs can be used. Choosing a missing language asks “You have not downloaded this language. Download it now?” Confirm to download; cancelling or a failed download keeps the current language. New reports use the selected language with the same six analysis requirements; existing reports are not translated. The product name is **Email Assistant** in English and **Asistente de correo electrónico** in Spanish.

## Mailbox proxies

Each mailbox can use Direct, System proxy, HTTP CONNECT or SOCKS5. In mailbox settings, open Advanced connection and proxy options; start v2rayN or your proxy app and use its actual listening host, port and protocol. Save and test before resuming monitoring. A failed proxy never silently switches to Direct. The setting covers IMAP tests and monitoring, not AI API traffic. PAC scripts and authenticated proxies are not supported.

## Update distribution / 更新分发

Stable manifest: [`distribution/manifest.json`](distribution/manifest.json). Source, documentation, language packs and installers are maintained in this repository: [Benson-YiYan/benson-mail-assistant](https://github.com/Benson-YiYan/benson-mail-assistant). Platform packages remain separate assets in the same release.

The legacy update address `benson-mail-updates/main/manifest.json` remains available. The update server synchronizes the same manifest there so older versions can continue checking for and downloading updates. The separate `benson-mail-updates` repository contains only this compatibility entry. If an update check fails, a “Download the latest version from GitHub” button appears. Installing over the existing version preserves mailbox and AI settings and reports.

## Summarize again and ask about an email

Select a report and choose Summarize again to regenerate all six sections in the current interface language. A failed attempt preserves the previous report. The saved email index provides the original message; older reports without that index show an explanation.

Ask about this email supports follow-up questions and additional files selected with the file picker. Each email has its own saved conversation that can be reopened. Model context includes the original email, readable attachments, current report and conversation. Long conversations compress earlier turns into a summary while keeping recent messages, with a compression indicator. Compression is not word-for-word preservation; the complete conversation remains locally saved. Quote and verify critical figures or wording.

These actions call your configured AI and may incur charges. Supplementary files are read only for text extraction; unreadable or oversized files cause an explicit error. No emails are sent. Conversation history is stored in local application data. Uninstalling removes it even when mailbox and AI settings are retained; copy any conversations you need before uninstalling.

## Sender rules and spam

Under Mailboxes and checking → Block emails, choose a blacklist or whitelist. Blacklisted senders are skipped; a whitelist summarizes only listed senders. An empty whitelist skips all new emails. Rules apply to every configured mailbox and match complete sender addresses without case sensitivity. Add, select in bulk, or remove addresses.

“Do not summarize spam (some providers may not support this)” uses explicit server flags, spam headers or junk folders. It does not guess from the subject or call AI to classify spam. Only the configured mail folder is checked; providers that expose no spam indicators cannot be recognized. The option is off by default.

Skipped emails are grouped by sender in the local records. Summarize one or several with the current language and AI settings. This is a one-time override and does not change the rules; failures keep the records. Delete record removes only the local record, never the original email. Rules apply to newly checked messages and do not remove existing reports.

Drag the divider between the report and the email conversation to resize both areas.

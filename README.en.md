# Mail Secretary

[简体中文](README.md) · [Download](https://github.com/Benson-YiYan/benson-mail-assistant/releases/latest)

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
- Runtimes are included: no Python, .NET or Homebrew installation is required.
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
- English and Chinese interfaces and new reports; existing reports remain unchanged.
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
| Windows | [English](windows/README.en.md) / [中文](windows/README.md) | [Development](windows/docs/DEVELOPMENT.md) |
| Mac | [English](macos/README.en.md) / [中文](macos/README.md) | [Development](macos/docs/DEVELOPMENT.md) |

Source lives in `windows/` and `macos/`. Public build adaptations may differ from the commits used for the verified downloadable packages; release notes identify their versions and test scope.

[Report a problem](https://github.com/Benson-YiYan/benson-mail-assistant/issues) with your OS version, app version and sanitized error details.

If this little secretary saves you time, a ⭐ is welcome.

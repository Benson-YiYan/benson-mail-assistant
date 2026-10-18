# Mail Secretary for Mac

[简体中文](README.md) · [Project guide](../README.en.md)

Each new email becomes six sections: **notice, sender, summary, actions, attachment contents and a suggested reply**. Supports multiple mailboxes, your choice of AI, Markdown previews, search and filters. Empty checks do not call AI; replies are never sent automatically.

## Install

Requires **macOS 14 or later**. In Apple menu → About This Mac, check whether you have Apple silicon or Intel. Use the DMG containing `Mac-AppleSilicon` or `Mac-Intel` respectively.
Download the matching DMG from the public [GitHub Releases](https://github.com/Benson-YiYan/benson-mail-assistant/releases/latest). Each release includes `SHA256SUMS.txt` for integrity checks.
Open the DMG, drag Mail Secretary into Applications, then open it there. The app includes its runtime; no Python or Homebrew setup is needed. API mode does not require Codex.
The app is not Developer ID-signed or Apple-notarized. Check the file's source if macOS cannot verify its developer. Version numbers use the actual build time in Beijing time.

## First setup

1. Choose an email provider, or Other email (custom IMAP). Enter the full address and the provider-required authorization code, app password or OAuth2 access token. Enable IMAP with the provider. Custom providers also need the host, port and encryption. Use the bundled authorization-code guide, then save and test.
2. In AI service, choose an API, Codex or DeepSeek Harness, save and test it.
3. In General settings, use Browse to select the report folder, then start monitoring.

API mode needs a Chat Completions-compatible base URL, API key and model name. Codex needs an existing signed-in installation with a working command-line component. Harness needs an existing configured installation supporting `headless --json`; it is not bundled or downloaded. AI connection tests send a small message and may incur provider charges.
Presets include 163, 126, Yeah, QQ/Foxmail, Tencent Exmail, Gmail, Outlook/Microsoft 365, iCloud and Yahoo. Account authorization is still required. OAuth2 tokens currently need manual replacement after expiry; enterprise policies may restrict IMAP.

## Navigation

- **Email reports:** select a message on the left and read it on the right. Copy the source, open the file, search and filter.
- **Email and checks:** manage mailboxes, test connections, change the interval and control monitoring. Pause and wait for the current task before editing connections.
- **AI service:** choose, configure and test AI.
- **General settings:** language, report folder, sign-in startup, updates and uninstall.

The Help menu provides the usage guide, authorization-code tutorial, update check and About. Switching pages preserves unsaved email and AI inputs.

## Reports and monitoring

Checks default to 60 seconds and can be set from 10 to 86400 seconds. **The first check of a new mailbox records its current position; it does not analyze the entire old inbox.** With saved progress, mail received while paused or offline is checked after resuming if still in the selected folder.
New files use `selected-folder/date/subject-received-time.md`, with Beijing dates and times and collision avoidance. The preview renders headings, bold, nested lists, links, tables and code. Older TXT reports remain readable, searchable and filterable.
Search uses locally saved bodies, senders, attachment names and report text, not the whole remote mailbox. Changing the folder affects new reports; older files remain where they were saved.

## Updates, quitting and uninstall

Updates are checked every five hours or through Help → Check for updates. Downloads, progress and verification happen inside the app. Installation requires your action, preserves settings and reports, and attempts rollback on failure.
Closing the window keeps monitoring in the menu bar. Quitting through the Dock, menus or Command-Q stops monitoring and saves a paused state. Reopen and start monitoring to resume.
Uninstall is in General settings. Settings and reports have separate retention choices; report deletion requires confirmation. Keeping settings retains this app's Keychain credentials for reinstallation; cached mail and progress are cleared.

## Connection problems and data

Test the email connection and copy its stage, exception type and sanitized server response. Check credentials for authentication failures, webmail or administrator settings for disabled IMAP, provider security notices for Unsafe Login, and host, port, network, clock and proxy for DNS, timeout or TLS errors.
Credentials and API keys are stored in the login Keychain. Message and readable attachment contents go to your chosen AI. Mailbox access is read-only; the app does not send replies. Images, scans, encrypted and unsupported attachments have reading limits. Review the original before using a draft.
The first launch follows the system language, using Chinese for Chinese languages and English otherwise. New reports follow your selected UI language; drafts follow the incoming message. Existing reports remain unchanged.

## Development

Sources are in `Sources` and `Runtime`. See [Development and release builds](docs/DEVELOPMENT.md) for environment setup, Apple silicon/Intel builds, offline verification and DMG packaging.
End users can use the DMG. Intel builds are tested through Rosetta on Apple silicon, rather than on a physical Intel Mac.

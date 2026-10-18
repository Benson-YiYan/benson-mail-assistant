# Mail Secretary for Windows

[简体中文](README.md)

Each new email becomes six useful sections: **notice, sender, summary, actions, attachment contents and a suggested reply**. Supports multiple mailboxes, your choice of AI, Markdown previews, search and filters. Empty checks do not call AI. Replies are never sent automatically.

## Install

Requires **Windows 10 / 11, x64**. Download `BensonMail-Windows-x64-Setup-<version>.exe` from [GitHub Releases](https://github.com/Benson-YiYan/benson-mail-assistant-windows/releases/latest), run it, choose the installation folder and shortcuts, then open the app. The final page can optionally delete the downloaded installer after it closes.
This repository is private; downloads require an authorized GitHub account. Existing users can also use **Check for updates**. Version numbers use the actual build time in Beijing time: `yyyyMMddHHmm`. Each release includes `SHA256SUMS.txt` to verify the installer.
The installer includes its runtimes: no Python, .NET, WinUI or terminal setup is needed. API mode does not require Codex. The installer is not publisher code-signed; check its source if Windows displays a warning.

## First setup

1. **Email:** choose a provider or Other email (custom IMAP), enter the full address and the provider-required app password, authorization code or OAuth2 access token. Enable IMAP with the provider. Custom providers also need the host, port and encryption. Use **How do I get an authorization code?**, then save and test the connection.
2. **AI:** choose one of the options below, save it and test the connection.
3. **Folder:** use Browse to choose the report folder, then start monitoring.

| AI option | Requirements |
| --- | --- |
| API | Chat Completions-compatible base URL, API key and model name |
| Codex | Installed, signed-in Codex with a working command-line component |
| DeepSeek Harness | An existing configured installation supporting `headless --json` |

API mode accepts the provider's base URL, such as one ending in `/v1`, or the full `/chat/completions` URL. Harness is not bundled or downloaded. Testing AI sends a small message and may incur provider charges.
Presets include 163, 126, Yeah, QQ/Foxmail, Tencent Exmail, Gmail, Outlook/Microsoft 365, iCloud and Yahoo. Presets supply connection settings; account authorization is still required.
OAuth2 tokens must currently be supplied and replaced manually. The Microsoft helper needs a usable client ID and browser authorization; administrator approval may also be required. It does not refresh tokens automatically.

## Monitoring and reports

- Checks default to 60 seconds; choose any interval from 10 to 86400 seconds.
- **The first check of a newly added mailbox records its current position. It does not analyze the entire existing inbox.**
- With saved progress, messages received while paused or offline are checked on resume if still in the selected folder. Pause and wait for current work before editing connection settings.
- New reports use `selected-folder/date/subject-received-time.md`, with dates and times in Beijing time. Collisions are avoided.
- The preview renders headings, bold, lists, links, tables and code blocks. Existing TXT reports remain readable, searchable and filterable.
- Search uses locally saved bodies, senders, attachment names and reports. Combine date, sender and attachment filters. It does not scan the remote mailbox.
- Open report opens the saved file; Open report folder opens its folder.

## Updates and removal

Updates are checked every five hours and on request. Download, cancel, retry and verification happen inside the app; installation requires your action. Settings, reports and shortcut choices are preserved.
Closing the window keeps monitoring in the tray. Use the envelope to restore it. Exiting stops the current session; Windows sign-in startup is optional.
Uninstall from its shortcut or Windows Installed apps. A running app requires confirmation to exit; wait for active mail processing to finish. Settings and reports have separate retention switches, and report deletion needs confirmation. Retained credentials only work for the same Windows user on the same computer.

## Connection problems

Run Test email connection and copy the stage, exception type and server response. Authentication failures call for checking the account and provider-required credentials; IMAP-disabled errors call for checking webmail or administrator settings. Unsafe Login calls for checking provider security notices. DNS, timeout and TLS errors call for checking the host, port, network, clock and proxy.
If an old version only says “Operation failed. Check settings and file permissions,” update first: that message does not establish a permissions problem.

## Data and language

Credentials and API keys are encrypted for the current Windows user. Messages and readable attachment contents go to your selected AI. Mailbox access is read-only. Images, scanned, encrypted and unsupported attachments have reading limits; review the original before using a reply draft.
The first launch uses Chinese for Chinese system languages and English otherwise. You can change it later. New reports follow that language; reply drafts follow the incoming message. Existing reports remain unchanged.

## Development

Current code is on [`build/windows-app`](https://github.com/Benson-YiYan/benson-mail-assistant-windows/tree/build/windows-app). See the [development guide](https://github.com/Benson-YiYan/benson-mail-assistant-windows/blob/build/windows-app/docs/DEVELOPMENT.md).

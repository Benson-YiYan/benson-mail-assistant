# Email Assistant for Windows

[简体中文](README.md) · [Español](README.es.md)

Each new email becomes six useful sections: **notice, sender, summary, actions, attachment contents and a suggested reply**. Supports multiple mailboxes, your choice of AI, Markdown previews, search and filters. Empty checks do not call AI. Replies are never sent automatically.

## Install

Requires **Windows 10 / 11, x64**. Download `BensonMail-Windows-x64-Setup-<version>.exe` from [GitHub Releases](https://github.com/Benson-YiYan/benson-mail-assistant/releases/latest), run it, choose the installation folder and shortcuts, then open the app. The final page can optionally delete the downloaded installer after it closes.
Installers are available from the public releases. Existing users can also use **Check for updates**. Version numbers use the actual build time in Beijing time: `yyyyMMddHHmm`. Each release includes `SHA256SUMS.txt` to verify the installer.
No Python or terminal setup is needed. API mode does not require Codex. Setup checks **.NET 8 (x64)** and **Windows App Runtime 1.8 (x64, providing WinUI 3)**. Missing components are listed for explicit confirmation before download and installation; compatible installed components are reused. Shared component installation may require administrator approval. Declining or a failed prerequisite installation leaves the old application untouched. Successful upgrades remove obsolete bundled runtime copies only when their recorded paths and SHA256 match. Uninstalling the app keeps system shared runtimes. The installer is not publisher code-signed; check its source if Windows displays a warning.

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
The first launch uses Chinese for Chinese system languages, Spanish for Spanish system languages and English otherwise. You can change it later. New reports follow that language; reply drafts follow the incoming message. Existing reports remain unchanged.

## Development

Source is in `windows/` on the main branch. See the [development guide](docs/DEVELOPMENT.md) and [project overview](../README.en.md).

## Languages and language packs

The interface, installer and uninstaller support **Simplified Chinese, English and Spanish**. First use selects Chinese for Chinese system languages, Spanish for Spanish system languages and English otherwise. You can change it in General settings. Windows Setup offers **Download Simplified Chinese**, **Download English** and **Download Spanish**.

Only installed language packs can be used. Choosing a missing language asks “You have not downloaded this language. Download it now?” Confirm to download; cancelling or a failed download keeps the current language. New reports use the selected language with the same six analysis requirements; existing reports are not translated. The product name is **Email Assistant** in English and **Asistente de correo electrónico** in Spanish.

## Mailbox proxies

Each mailbox can use Direct, System proxy, HTTP CONNECT or SOCKS5. In mailbox settings, open Advanced connection and proxy options; start v2rayN or your proxy app and use its actual listening host, port and protocol. Save and test before resuming monitoring. A failed proxy never silently switches to Direct. The setting covers IMAP tests and monitoring, not AI API traffic. PAC scripts and authenticated proxies are not supported.

## Summarize again and ask about an email

Select a report and choose Summarize again to regenerate all six sections in the current interface language. A failed attempt preserves the previous report. The saved email index provides the original message; older reports without that index show an explanation.

Ask about this email supports follow-up questions and additional files selected with the file picker. Each email has its own saved conversation that can be reopened. Model context includes the original email, readable attachments, current report and conversation. Long conversations compress earlier turns into a summary while keeping recent messages, with a compression indicator. Compression is not word-for-word preservation; the complete conversation remains locally saved. Quote and verify critical figures or wording.

These actions call your configured AI and may incur charges. Supplementary files are read only for text extraction; unreadable or oversized files cause an explicit error. No emails are sent. Conversation history is stored in local application data. Uninstalling removes it even when mailbox and AI settings are retained; copy any conversations you need before uninstalling.

## Sender rules and spam

Under Mailboxes and checking → Block emails, choose a blacklist or whitelist. Blacklisted senders are skipped; a whitelist summarizes only listed senders. An empty whitelist skips all new emails. Rules apply to every configured mailbox and match complete sender addresses without case sensitivity. Add, select in bulk, or remove addresses.

“Do not summarize spam (some providers may not support this)” uses explicit server flags, spam headers or junk folders. It does not guess from the subject or call AI to classify spam. Only the configured mail folder is checked; providers that expose no spam indicators cannot be recognized. The option is off by default.

Skipped emails are grouped by sender in the local records. Summarize one or several with the current language and AI settings. This is a one-time override and does not change the rules; failures keep the records. Delete record removes only the local record, never the original email. Rules apply to newly checked messages and do not remove existing reports.

Drag the divider between the report and the email conversation to resize both areas.

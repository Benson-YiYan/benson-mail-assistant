# Email Assistant for Mac

[简体中文](README.md) · [Español](README.es.md) · [Project guide](../README.en.md)

Each new email becomes six sections: **notice, sender, summary, actions, attachment contents and a suggested reply**. Supports multiple mailboxes, your choice of AI, Markdown previews, search and filters. Empty checks do not call AI; replies are never sent automatically.

## Install

Requires **macOS 14 or later**. In Apple menu → About This Mac, check whether you have Apple silicon or Intel. Use the DMG containing `Mac-AppleSilicon` or `Mac-Intel` respectively.
Download the matching DMG from the public [GitHub Releases](https://github.com/Benson-YiYan/benson-mail-assistant/releases/latest). Each release includes `SHA256SUMS.txt` for integrity checks.
Open the DMG, drag Email Assistant into Applications, then open it there. The app includes its runtime; no Python or Homebrew setup is needed. API mode does not require Codex.
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

The Help menu provides the usage guide, authorization-code tutorial, update check and About. Leaving a settings page with unsaved edits asks for confirmation.

## Reports and monitoring

Checks default to 60 seconds and can be set from 10 to 86400 seconds. **The first check of a new mailbox records its current position; it does not analyze the entire old inbox.** With saved progress, mail received while paused or offline is checked after resuming if still in the selected folder.
New files use `selected-folder/receiving-account/date/From sender-address/subject-received-time.md`, with Beijing dates and times and collision avoidance. Enable Report tree to browse account → date → sender → report, with an Up button and breadcrumb; disable it for a flat list. Search and filters still apply. Startup organizes identifiable older reports while retaining original-email and conversation links. The preview renders headings, bold, nested lists, links, tables and code. Older TXT reports remain readable, searchable and filterable.
Search uses locally saved bodies, senders, attachment names and report text, not the whole remote mailbox. Changing the folder affects new reports; older files remain where they were saved.

## Updates, quitting and uninstall

Updates are checked every hour or through Help → Check for updates. Downloads, progress and verification happen inside the app. Installation requires your action, preserves settings and reports, and attempts rollback on failure.
Closing the window keeps monitoring in the menu bar. Quitting through the Dock, menus or Command-Q stops monitoring and saves a paused state. Reopen and start monitoring to resume.
Uninstall is in General settings. Settings and reports have separate retention choices; report deletion requires confirmation. Keeping settings retains this app's Keychain credentials for reinstallation; cached mail and progress are cleared.

## Connection problems and data

Test the email connection and copy its stage, exception type and sanitized server response. Check credentials for authentication failures, webmail or administrator settings for disabled IMAP, provider security notices for Unsafe Login, and host, port, network, clock and proxy for DNS, timeout or TLS errors.
Credentials and API keys are stored in the login Keychain. Message and readable attachment contents go to your chosen AI. Mailbox access is read-only; the app does not send replies. Images, scans, encrypted and unsupported attachments have reading limits. Review the original before using a draft.
The first launch follows the system language, using Chinese for Chinese languages, Spanish for Spanish languages and English otherwise. New reports follow your selected UI language; drafts follow the incoming message. Existing reports remain unchanged.

## Development

Sources are in `Sources` and `Runtime`. See [Development and release builds](docs/DEVELOPMENT.md) for environment setup, Apple silicon/Intel builds, offline verification and DMG packaging.
End users can use the DMG. Intel builds are tested through Rosetta on Apple silicon, rather than on a physical Intel Mac.

## Languages and language packs

The interface, installer and uninstaller support **Simplified Chinese, English and Spanish**. First use selects Chinese for Chinese system languages, Spanish for Spanish system languages and English otherwise. You can change it in General settings. Windows Setup offers **Download Simplified Chinese**, **Download English** and **Download Spanish**.

Only installed language packs can be used. Choosing a missing language asks “You have not downloaded this language. Download it now?” Confirm to download; cancelling or a failed download keeps the current language. New reports use the selected language with the same six analysis requirements; existing reports are not translated. The product name is **Email Assistant** in English and **Asistente de correo electrónico** in Spanish.

## Mailbox proxies

Each mailbox can use Direct, System proxy, HTTP CONNECT or SOCKS5. In mailbox settings, open Advanced connection and proxy options; start v2rayN or your proxy app and use its actual listening host, port and protocol. Save and test before resuming monitoring. A failed proxy never silently switches to Direct. The setting covers IMAP tests and monitoring, not AI API traffic. PAC scripts and authenticated proxies are not supported.

### If macOS blocks the first launch

The app has an ad-hoc signature and is not signed with an Apple Developer ID or notarized by Apple. Verify the GitHub release and its SHA256 first. Try opening it once, then open System Settings → Privacy & Security and use Open Anyway if macOS offers it; confirm the next prompt. Do not disable Gatekeeper globally. If your Mac is managed or the option is unavailable, ask its administrator.

## Summarize again and ask about an email

Select a report and choose Summarize again to regenerate all six sections in the current interface language. A failed attempt preserves the previous report. The saved email index provides the original message; older reports without that index show an explanation.

Ask about this email supports follow-up questions and additional files selected with the file picker. Each email has its own saved conversation that can be reopened. Factual answers use the original email and readable original attachments. Conversation is included, but generated reports, previous answers and compressed summaries are not factual evidence. Long conversations compress earlier turns into a summary while keeping recent messages, with a compression indicator. Compression is not word-for-word preservation; the complete conversation remains locally saved. Quote and verify critical figures or wording.

These actions call your configured AI and may incur charges. Supplementary files are read only for text extraction; unreadable or oversized files cause an explicit error. No emails are sent. Conversation history is stored in local application data. Uninstalling removes it even when mailbox and AI settings are retained; copy any conversations you need before uninstalling.

## Sender rules and spam

Under Mailboxes and checking → Block emails, choose a blacklist or whitelist. Blacklisted senders are skipped; a whitelist summarizes only listed senders. An empty whitelist skips all new emails. Rules apply to every configured mailbox and match complete sender addresses without case sensitivity. Add, select in bulk, or remove addresses.

“Do not summarize spam (some providers may not support this)” uses explicit server flags, spam headers or junk folders. It does not guess from the subject or call AI to classify spam. Only the configured mail folder is checked; providers that expose no spam indicators cannot be recognized. The option is off by default.

Skipped emails are grouped by sender in the local records. Summarize one or several with the current language and AI settings. This is a one-time override and does not change the rules; failures keep the records. Delete record removes only the local record, never the original email. Rules apply to newly checked messages and do not remove existing reports.

Drag the divider between the report and the email conversation to resize both areas.

## New workflows and reliability improvements

- **Reply drafts:** choose tone, language and instructions, then edit the recipient, subject and body before saving locally or copying. The app never sends the draft automatically.
- **Enhanced attachment reading:** images and scanned PDFs first use native local OCR; extracted text then goes to the selected AI. System language support, file limits and recognition quality apply. Unreadable content is reported, and recognition is not guaranteed.
- **Older-mail processing:** select a mailbox and date range, preview the pending count, then confirm to queue. Processing may incur AI charges and still follows sender and spam rules.
- **Sources and continuous questions:** inspect saved original mail, attachment extraction and reading limitations. Questions use the original message and readable original attachments as factual evidence; generated reports and earlier AI replies do not replace originals. Missing sources for older mail are reported.
- **Notifications and quiet hours:** system notifications can be paused independently of monitoring. Quiet hours, including overnight periods, keep checking mail and saving reports.
- **Diagnostics:** manually export sanitized operational information for troubleshooting, excluding keys, message bodies, attachments and chat contents.
- **One Save per settings page:** mailbox, AI and General settings stage edits until their page Save. Leaving a page with unsaved edits asks for confirmation. Language, report folder and login startup are managed in General settings.

[简体中文完整指南](Resources/Quick-start-zh.txt) · [Complete English guide](Resources/Quick-start-en.txt) · [Guía completa en español](Resources/Quick-start-es.txt)

## Step-by-step guide to all features and settings

[Complete user guide](Resources/Quick-start-en.txt)

## Cost sources and account balances

Open the usage records from AI settings to view input/output tokens, upstream-reported costs, local estimates and the number of calls covered by each source. Upstream costs take precedence per call; those calls are excluded from local estimates. Missing costs are estimated from saved rates and token usage, or shown as Unknown when the required data is absent. Currencies are kept separate; historical records are not guessed or repriced.

Official OpenRouter `usage.cost` is recorded in USD. Compatible APIs must explicitly return `usage.cost` with `cost_currency`, or a cost object containing `amount` and `currency`. Other providers continue to use estimates. An upstream-reported amount is not a substitute for the final bill.

Query account balance runs only when clicked, supports official DeepSeek and OpenRouter endpoints, and does not generate AI content. Balances belong to the entire provider account and may include other applications; balance changes cannot be attributed to this app. OpenRouter balance queries require management permissions, so a normal inference key may be refused. Do not replace an inference key with a management key merely to query balances. A failed query is not displayed as a zero balance.

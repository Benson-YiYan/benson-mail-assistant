# 邮件小秘书 · Mail Secretary

原生 Windows / Mac 邮件助手，自动生成六项邮件报告：新邮件提醒、发件人、摘要、待办、附件内容、建议回复。支持多个邮箱、自定义 IMAP、兼容 API、用户已安装的 Codex / DeepSeek Harness，以及中文 / English。

## 下载与安装

| 电脑 | 文件 | 版本 |
| --- | --- | --- |
| Windows 10 / 11 x64 | `BensonMail-Windows-x64-Setup-202610181547.exe` | 202610181547 |
| Apple 芯片 Mac，macOS 14+ | `BensonMail-Mac-AppleSilicon-202610181459.dmg` | 202610181459 |
| Intel Mac，macOS 14+ | `BensonMail-Mac-Intel-202610181459.dmg` | 202610181459 |

Windows：运行 EXE，选择安装位置和快捷方式；已有版本可覆盖安装。Mac：打开对应 DMG，将应用拖入“应用程序”。运行环境已包含，无需另装 Python、.NET 或 Homebrew。API 模式无需安装 Codex；Harness 模式使用用户已安装的 Harness。

`SHA256SUMS.txt` 包含上述三个安装包的 SHA256。Windows 安装包没有发布者代码签名；Mac 使用本地签名，未经 Apple Developer ID 签名及公证。

## 本版内容

- Windows：修复更新接力及旧目录升级，加入启动确认、日志、取消保护和升级后启动新版；清理内容仍匹配旧版 SHA256 的淘汰运行库。独立程序文件约 251 MiB，较记录的旧版基线减少 30.45%。
- Mac：四页原生侧栏、完整高度的 Markdown 报告、固定表单操作按钮、切页保留未保存输入、首次设置同步。
- 两平台：多邮箱、报告筛选搜索、自定义检查间隔和保存目录、中英文报告、脱敏邮箱连接诊断。没有新邮件或待重试任务时不调用 AI；不会自动发送回复。

## 源码与验证

统一源码在 `windows/` 和 `macos/`。本次发布复用已验证的 Windows 202610181547 和 Mac 202610181459 安装包，**没有重新构建或修改它们**。发布标签包含随后完成的公开仓库构建适配和文档整理，因此该标签的源码不声称与安装包构建提交逐字一致，也不保证可重现相同字节。

Windows 在 GitHub Windows runner 验证真实安装、升级、取消、重新打开新版、配置与报告保留、旧运行库清理和卸载；公开仓库的首次构建及测试也已通过。Mac 两种架构完成界面、独立运行时、DMG 和更新包测试；Intel 在 Rosetta 下验证，没有物理 Intel Mac 测试。上述回归使用合成数据，没有连接真实邮箱或外部 AI。

---

# English

Mail Secretary is a native Windows and Mac email assistant. Each new message becomes six sections: notice, sender, summary, actions, attachment contents and a suggested reply. Supports multiple mailboxes, custom IMAP, compatible APIs, installed Codex / DeepSeek Harness, English and Chinese.

## Download

Choose the Windows x64 Setup EXE (Windows 10/11, version **202610181547**), AppleSilicon DMG, or Intel DMG (macOS 14+, both version **202610181459**) from the table above. Run Setup on Windows; on Mac, open the matching DMG and drag the app into Applications. Runtimes are included. API mode does not require Codex; Harness mode uses your installed Harness.

Verify all three packages with `SHA256SUMS.txt`. Windows packages are not publisher code-signed. Mac apps have local signatures without Apple Developer ID signing or notarization.

## Changes

- Windows: repaired updater handoff and legacy-directory upgrades, startup acknowledgment, actionable logs, safe cancellation and verified relaunch. Obsolete runtime cleanup requires matching legacy SHA256 fingerprints. The standalone payload is about 251 MiB, 30.45% below the recorded legacy baseline.
- Mac: four-page native sidebar, full-height Markdown reader, fixed form actions, preserved input drafts and synchronized first-run setup.
- Both: multiple mailboxes, report search/filters, custom check intervals and report folders, bilingual reports and sanitized mail diagnostics. Empty checks without pending retries do not call AI. Replies are never sent automatically.

## Source and verification

Source is unified under `windows/` and `macos/`. This release reuses the exact previously verified packages listed above; **they were not rebuilt or modified**. The release tag additionally contains public-repository build adaptations and documentation cleanup, so its source is not claimed to be identical to the original binary build commits or byte-reproducible.

Windows installer, upgrade, cancellation, relaunch, settings/report retention, obsolete-runtime cleanup and uninstall flows passed on a GitHub Windows runner. The first public-repository build and tests also passed. Both Mac architectures passed UI, standalone-runtime, DMG and updater checks; Intel testing used Rosetta, not a physical Intel Mac. Regression tests used synthetic data without real mailbox or external AI requests.

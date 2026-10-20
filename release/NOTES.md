# 邮件小秘书 · Email Assistant · Asistente de correo electrónico

## 简体中文

- 邮箱与检查、AI 服务、通用设置整页编辑，每页统一保存；修复 Mac 保存后仍显示未保存的问题。Windows 单独提供通用设置页。
- 新增可编辑的回复草稿、附件文字／OCR 增强、历史邮件补总结、报告来源查看和脱敏诊断包导出。草稿不会自动发送。
- 对邮件提问使用保存的原邮件和可读取附件；支持补充文件与保留对话。报告与聊天区域可拖动调整，展开／折叠整行可点击。
- 免打扰时间与独立的系统通知开关；暂停通知不影响收信和总结。
- 输入／输出 Token 分开显示。上游返回费用优先，其余调用按保存单价估算，信息不足显示“未知”；标明各来源覆盖次数，不混加币种或重复计费。
- 手动查询官方 DeepSeek／OpenRouter 账户余额。查询不生成 AI 内容；账户余额不归属于本软件。OpenRouter 余额查询可能因普通推理 Key 权限不足而被拒绝。
- Windows 下载更新后选择“稍后”会继续后台下载，检查更新处显示进度。同步中文、英文、西班牙语界面与指南。

## English

- Edit a settings page and save it once. Fix the Mac page remaining dirty after saving; give Windows its own General settings page.
- Editable reply drafts, enhanced attachment text/OCR, historical-mail backfill, source inspection and sanitized diagnostic export. Drafts are never sent automatically.
- Email Q&A uses the saved original message and readable attachments, with additional files and saved conversations. Resize report/chat panes and click the full disclosure row.
- Quiet hours and a separate system-notification switch; monitoring and analysis continue while notifications are paused.
- Show input/output tokens separately. Prefer upstream-reported costs per call, otherwise use saved-rate estimates or Unknown. Show coverage counts and keep currencies separate without double counting.
- Manually query official DeepSeek/OpenRouter account balances without AI generation. Balances are account-wide; ordinary OpenRouter inference keys may lack balance-query permissions.
- Windows update downloads continue after Later, with progress in Check for updates. Chinese, English and Spanish UI/help are updated.

## Español

- Edita cada página de configuración y guarda una sola vez. Se corrige el estado sin guardar de Mac y Windows incorpora su propia página General.
- Borradores editables, lectura de adjuntos/OCR mejorada, resúmenes de correos históricos, consulta de fuentes y exportación de diagnósticos anonimizados. No se envían borradores automáticamente.
- Las preguntas usan el correo original guardado y los adjuntos legibles; admiten archivos adicionales e historial. Paneles ajustables y filas completas para desplegar o plegar.
- Horario de no molestar y control independiente de notificaciones; la recepción y los resúmenes continúan aunque se silencien.
- Tokens de entrada/salida separados. Se prioriza el coste informado por el proveedor, se estima con precios guardados o se muestra Desconocido. Se indican las llamadas cubiertas, sin duplicar costes ni sumar monedas distintas.
- Consulta manual del saldo oficial de DeepSeek/OpenRouter, sin generar contenido de IA. El saldo corresponde a toda la cuenta; una clave normal de OpenRouter puede no tener permiso para consultarlo.
- En Windows, Más tarde mantiene la descarga en segundo plano y muestra el progreso. Interfaz y guías actualizadas en chino, inglés y español.

## Packages / 安装包

| Platform | Version | File |
| --- | --- | --- |
| Windows x64 | 202610202319 | `BensonMail-Windows-x64-Setup-202610202319.exe` |
| Mac Apple silicon | 202610202318 | `BensonMail-Mac-AppleSilicon-202610202318.dmg` |
| Mac Intel | 202610202318 | `BensonMail-Mac-Intel-202610202318.dmg` |

Six optional data-only language packs are included. Verify the three installers and language packs with `SHA256SUMS.txt`.

## Verification / 验证

Binary source: `966c122de175b6a107960cebaa18c0148d1274d9`. The release tag additionally includes documentation and release metadata updates; executable code has not changed and these verified packages have not been rebuilt.

Windows build and checks: GitHub Actions run **39446932052** (backend, native UI, packaged application, installation/uninstallation, runtime prerequisites and update handoff). Mac: both architectures compile; bundle signatures and disk-image checksums pass; packaged worker billing/unsupported-balance paths pass with synthetic data. Intel validation uses Rosetta, not a physical Intel Mac. No real AI keys, real balances or paid AI calls were used for these billing tests.

Windows requires .NET 8 and Windows App Runtime 1.8; Setup detects existing components and asks before installing missing ones. Mac requires macOS 14+. Windows packages are not publisher code-signed; Mac bundles use local signatures without Apple notarization.

Upstream cost data is available only when the provider returns recognized fields. Account-balance lookup is limited to supported official endpoints and permissions. Provider statements remain the final billing reference.

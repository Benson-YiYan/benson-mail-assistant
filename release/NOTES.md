# 邮件小秘书 · Email Assistant · Asistente de correo electrónico

## 简体中文

- “回复”“原文”“报告溯源”分开显示。回复支持按要求生成、编辑、选择已添加的发件邮箱，并在确认收件人和正文后发送。
- Mac 强调色统一为蓝色；修复首次配置后整页设置草稿不刷新，以及修改邮箱地址后默认登录用户名未跟随的问题。
- Windows 邮箱连接测试支持未保存的设置草稿，复用原连接凭据，解除保存与连接测试的互相依赖。
- 同步中、英、西班牙语指南。

## English

- Separate Reply, Original message and Report provenance actions. Generate and edit replies, select a configured sending mailbox, and confirm the recipient and content before sending.
- Use blue consistently on Mac. Refresh staged settings after initial setup and keep the default login username aligned with a changed address.
- Test unsaved Windows mailbox settings using existing credentials where applicable, removing the save/test dependency.
- Update Chinese, English and Spanish guides.

## Español

- Acciones separadas para Responder, Correo original y Procedencia del informe. Genera y edita respuestas, elige un buzón configurado y confirma destinatario y contenido antes de enviar.
- Color azul uniforme en Mac. Se actualiza la configuración tras la preparación inicial y el usuario predeterminado sigue los cambios de dirección.
- Windows permite probar la configuración sin guardar y reutilizar credenciales existentes cuando corresponde.
- Guías actualizadas en chino, inglés y español.

## Packages / 安装包

| Platform | Version | File |
| --- | --- | --- |
| Windows x64 | 202610221251 | `BensonMail-Windows-x64-Setup-202610221251.exe` |
| Mac Apple silicon | 202610221553 | `BensonMail-Mac-AppleSilicon-202610221553.dmg` |
| Mac Intel | 202610221555 | `BensonMail-Mac-Intel-202610221555.dmg` |

Six optional language packs and SHA256SUMS.txt are included.

## Verification / 验证

Windows: GitHub Actions 39724411004 passed native build, backend, UI and installation checks. Subsequent source changes affect Mac only. Mac: both architectures passed full native UI tests, packaged worker tests, disposable launchd tests and DMG update preparation; disk images passed hdiutil verification. Intel tests use Rosetta, not a physical Intel Mac. Synthetic fixtures only; no real email was sent by these tests.

Windows requires .NET 8 and Windows App Runtime 1.8. Mac requires macOS 14+. Windows installers are not publisher-signed; Mac uses local signatures without Apple notarization.

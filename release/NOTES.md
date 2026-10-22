# 邮件小秘书 · 连接修复与错误诊断

## 简体中文
- 修复 Mac 安装包缺少运行时证书策略文件，导致 HTTPS、邮件提问及 AI 测试报 FileNotFoundError。
- Mac AI 与邮箱连接测试显示等待状态和就近结果，防止重复测试。
- 两版增加稳定错误码，区分本地文件、权限、DNS、TLS、超时、连接拒绝和接口 HTTP 状态；保留系统错误号并隐藏凭据。

## English
- Fix the missing Mac runtime certificate policy file that prevented HTTPS and AI requests.
- Show Mac connection test activity and inline results; prevent duplicate AI tests.
- Add diagnostic codes on both platforms for local files, permissions, DNS, TLS, timeout, refused connections and HTTP status. Preserve OS error numbers and redact credentials.

## Español
- Corrige el archivo de certificados ausente en Mac que impedía HTTPS y las solicitudes de IA.
- Muestra actividad y resultados de las pruebas de conexión en Mac y evita pruebas duplicadas.
- Añade códigos en ambas plataformas para archivos, permisos, DNS, TLS, tiempo de espera, conexiones rechazadas y estados HTTP; oculta credenciales.

Mac Apple silicon: 202610230736. Mac Intel: 202610230739. Intel verification uses Rosetta.
Windows: GitHub Actions 39872819050. Mac packages pass TLS context, runtime and update preparation checks. AI connection succeeded with the repaired runtime; tests do not send email.

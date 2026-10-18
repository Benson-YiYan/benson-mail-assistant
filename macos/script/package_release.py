"""Create a drag-to-Applications disk image, with no user settings or secrets."""
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import tempfile

project = Path(__file__).resolve().parents[1]
app = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else project / 'dist/邮件小秘书.app'
info = plistlib.loads((app / 'Contents/Info.plist').read_bytes())
version = info['CFBundleVersion']
destination = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else project / 'dist'
destination.mkdir(parents=True, exist_ok=True)
architectures = set(subprocess.check_output(
    ['/usr/bin/lipo', '-archs', str(app / 'Contents/MacOS/BensonMailMac')], text=True).split())
worker_architectures = set(subprocess.check_output(
    ['/usr/bin/lipo', '-archs', str(app / 'Contents/Resources/worker/MailWorker')], text=True).split())
if architectures == {'x86_64'}:
    platform_name, supported = 'Intel', 'Intel 芯片 Mac'
elif architectures == {'arm64'}:
    platform_name, supported = 'AppleSilicon', 'Apple 芯片 Mac（M1/M2/M3/M4 等）'
else:
    raise RuntimeError('Unsupported application architectures')
if not architectures.issubset(worker_architectures):
    raise RuntimeError('Application and bundled worker architectures do not match')
target = destination / f'BensonMail-Mac-{platform_name}-{version}.dmg'
subprocess.run(['/usr/bin/codesign', '--verify', '--deep', '--strict', str(app)], check=True)
for file in app.rglob('*'):
    if file.name in {'settings.json', 'state.json', 'secret.bin', 'mail.json', 'message.eml'}:
        raise RuntimeError('User data must not be packaged')
with tempfile.TemporaryDirectory(prefix='BensonMail-dmg-') as temporary:
    stage = Path(temporary)
    shutil.copytree(app, stage / app.name, symlinks=True)
    (stage / 'Applications').symlink_to('/Applications')
    (stage / '安装与使用.txt').write_text(f'''邮件小秘书 Mac 独立版 {version}

适用：{supported}，macOS 14 或以上。

1. 将“邮件小秘书.app”拖到旁边的 Applications（应用程序）文件夹。
2. 从“应用程序”打开邮件小秘书。不要直接从安装镜像启动后台服务。
3. 在首次配置向导中选择邮箱服务商；也可选“其他邮箱（自定义 IMAP）”，填写服务器和凭据。
4. 选择 API，填写基础地址、模型名、API Key，保存；或使用已安装并登录的 Codex、已安装配置的 DeepSeek Harness。
   Harness 可自动检测或浏览选择 dsh 启动器，不捆绑、不下载运行时。
5. 用“浏览……”选择报告目录，点击“完成配置并开始监听”。

无需安装 Python、Homebrew、命令行工具或 .NET。API 模式无需 Codex。
首次检查仅记录现有邮件；之后的新邮件生成六项 Markdown（.md）报告，旧 TXT 报告仍可查看。
主窗口侧栏有“邮件报告”“邮箱与检查”“AI 服务”“通用设置”。
默认每60秒检查，间隔在“邮箱与检查”调整，报告目录在“通用设置”选择；无新邮件不调用 AI。
关闭窗口后继续在菜单栏监听；从 Dock、菜单或 ⌘Q 退出会停止后台并保存暂停状态。
再次打开后点击“开始监听”恢复，暂停期间的新邮件会补查；已暂停状态不会因登录而自动恢复。
报告包含发件人、摘要、待办、附件内容、建议回复等六项内容。
支持正文、发件人、附件名搜索与日期、发件人、有无附件筛选。
凭据保存在系统钥匙串，不在安装包或普通配置里。
可在侧栏“邮箱与检查”添加多个邮箱并分别启用或暂停；AI、报告目录和检查间隔共用。
各账号首次检查独立记录基线。需要 OAuth2 的邮箱可手动填写访问令牌，过期需自行更新，本版不自动登录或续期。
来信与可读取的附件文字发送给你选择的 AI，软件不会自动发送回复。

卸载：侧栏“通用设置” → 卸载邮件小秘书。将停止后台并移除应用和缓存，保留已保存的 Markdown / TXT 报告。
可选“保留邮箱及 AI 配置，下次重装不用再配置”；勾选后保留配置和钥匙串凭据。
不勾选会删除配置和本软件的钥匙串凭据。缓存及收信进度清除，重装后首次检查重新记录基线。

此版本使用本地临时签名，尚无 Apple Developer ID 签名和公证。
从其他电脑下载时，macOS 可能阻止首次打开；
确认安装包来自 Benson 后，可按系统提示在“系统设置 → 隐私与安全性”允许打开。
不要关闭系统安全保护。
''', encoding='utf-8')
    (stage / 'Read me - English.txt').write_text(f"""Mail Secretary for Mac {version}

Requires macOS 14 or later. Use the package matching your Mac processor.
1. Drag 邮件小秘书.app into Applications, then launch it from Applications.
2. Choose an email preset or Other mailbox (custom IMAP), then enter server and credentials.
3. Choose your AI: an API with base URL, model name and API key, or your installed and configured Codex or DeepSeek Harness. Harness is not bundled or downloaded.
4. Use Browse to choose the report folder, then finish setup and start monitoring.
No Python, Homebrew or developer tools are required. API mode does not require Codex.

Chinese system languages initially select Chinese; all others select English.
Change the language and report folder in General settings. New six-section reports use that language.
Reply drafts follow the incoming message language, with an explanation in the report language.
Existing Markdown and TXT reports and original email content remain unchanged.

The first check records a starting point. Future new messages generate reports.
The sidebar has Mail reports, Mailbox & checks, AI service and General settings.
The default check interval is 60 seconds and can be customized in Mailbox & checks. No new mail means no AI calls.
Closing the window keeps monitoring in the menu bar. Quitting stops monitoring and saves a paused state.
After reopening, click Start monitoring to resume and catch up on messages received while paused.
Add multiple mailboxes in Mailbox & checks. Reports, AI and the check interval are shared.
Search message bodies, senders and attachment names; filter by dates, sender and attachments.
Your selected AI receives message contents and readable attachment text. Replies are never sent automatically.
Credentials are kept in the macOS Keychain, not in this installer.
OAuth2 access tokens must be supplied and renewed manually; automatic sign-in and renewal are not supported.

Uninstall from General settings. You may keep mailbox and AI configuration for reinstalling.
Full removal deletes this app's settings and Keychain credentials. Saved Markdown and TXT reports are retained.
Cached mail and progress are removed; reinstalling records a new starting point.

This app is locally signed, without Apple Developer ID signing or notarization.
If macOS blocks the first launch after a download, verify the package came from Benson and follow the system prompt in System Settings > Privacy & Security to allow it. Keep system security enabled.
""", encoding='utf-8')
    subprocess.run(['/usr/bin/hdiutil', 'create', '-volname', '邮件小秘书-' + version,
                    '-srcfolder', str(stage), '-ov', '-format', 'UDZO', str(target)], check=True)
print(target)

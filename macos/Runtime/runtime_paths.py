"""Keep writable state outside the signed application bundle."""
import os
from pathlib import Path
import shutil
import sys

def data_home():
    override = os.environ.get('BENSON_MAIL_HOME')
    if override:
        return Path(override).expanduser()
    if getattr(sys, 'frozen', False):
        return Path.home() / 'Library/Application Support/BensonMail'
    return Path(__file__).resolve().parent

def codex_executable():
    candidates = [
        os.environ.get('BENSON_CODEX_PATH', ''),
        '/Applications/Codex.app/Contents/Resources/codex',
        str(Path.home() / 'Applications/Codex.app/Contents/Resources/codex'),
        '/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex',
        shutil.which('codex') or '',
        '/opt/homebrew/bin/codex', '/usr/local/bin/codex',
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return candidate
    raise RuntimeError('未找到 Codex 命令行组件。请安装并登录 Codex，或在设置中选择 API 模式。')

def child_command(module, *args):
    if getattr(sys, 'frozen', False):
        return [sys.executable, '--' + module, *map(str, args)]
    return [sys.executable, str(Path(__file__).resolve().parent / (module + '.py')), *map(str, args)]

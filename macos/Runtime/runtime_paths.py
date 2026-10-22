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

def codex_executable(explicit=""):
    import json
    saved = {}
    try: saved = json.loads((data_home() / "settings.json").read_text())
    except (OSError, ValueError): pass
    def resolve(chosen):
        if not chosen:
            return None
        path = Path(chosen).expanduser()
        if path.is_dir():
            resources = path / 'Contents/Resources'
            for pattern in ('codex', 'codex-cli/bin/codex', 'codex-cli/**/bin/codex', 'app.asar.unpacked/**/codex'):
                for candidate in resources.glob(pattern):
                    if candidate.is_file() and os.access(candidate, os.X_OK):
                        return str(candidate)
        elif path.is_file() and os.access(path, os.X_OK):
            return str(path)
        return None

    # Resolve each user choice before considering any automatically found install.
    for chosen in (explicit, os.environ.get('BENSON_CODEX_PATH', ''), saved.get('codex_path', '')):
        resolved = resolve(chosen)
        if resolved:
            return resolved
        if chosen == explicit and explicit:
            raise RuntimeError('所选位置没有可用的 Codex 命令行组件。')
    import subprocess
    app_roots = []
    try:
        found = subprocess.run(['/usr/bin/mdfind', 'kMDItemCFBundleIdentifier == "com.openai.codex" || kMDItemCFBundleIdentifier == "com.openai.chat"'], capture_output=True, text=True, timeout=5)
        if found.returncode == 0:
            app_roots.extend(p for p in found.stdout.splitlines() if p.endswith('.app'))
    except (OSError, subprocess.TimeoutExpired):
        pass
    candidates = [
        shutil.which('codex') or '',
        '/opt/homebrew/bin/codex', '/usr/local/bin/codex',
        *app_roots,
        '/Applications/ChatGPT.app', str(Path.home() / 'Applications/ChatGPT.app'),
        '/Applications/Codex.app', str(Path.home() / 'Applications/Codex.app'),
    ]
    for candidate in candidates:
        resolved = resolve(candidate)
        if resolved:
            return resolved
    raise RuntimeError('未找到 Codex 命令行组件。请安装并登录 Codex，或在设置中选择 API 模式。')

def child_command(module, *args):
    if getattr(sys, 'frozen', False):
        return [sys.executable, '--' + module, *map(str, args)]
    return [sys.executable, str(Path(__file__).resolve().parent / (module + '.py')), *map(str, args)]

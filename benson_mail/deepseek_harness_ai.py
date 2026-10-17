"""Invoke the user's installed dsh CLI; never bundle or download Harness."""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time


def discover(path=''):
    candidates = [Path(path).expanduser()] if path.strip() else []
    if not path.strip():
        found = shutil.which('dsh')
        if found:
            candidates.append(Path(found))
        home = Path.home()
        if os.name == 'nt':
            for base in (Path(os.environ.get('LOCALAPPDATA', str(home))) / 'Programs', Path(os.environ.get('PROGRAMFILES', 'C:/Program Files'))):
                for name in ('DeepSeek Harness', 'deepseek-harness'):
                    candidates.append(base / name / 'resources/runtime/cli/bin/dsh.cmd')
            candidates.append(Path(os.environ.get('APPDATA', str(home))) / 'npm/dsh.cmd')
        else:
            for base in (Path('/Applications'), home / 'Applications'):
                candidates.append(base / 'DeepSeek Harness.app/Contents/Resources/runtime/cli/bin/dsh')
            candidates.extend(Path(p) for p in ('/opt/homebrew/bin/dsh', '/usr/local/bin/dsh', str(home / '.local/bin/dsh')))
    for candidate in candidates:
        if candidate.suffix.lower() == '.app':
            candidate = candidate / 'Contents/Resources/runtime/cli/bin/dsh'
        if candidate.is_file() and (os.name == 'nt' or os.access(candidate, os.X_OK)):
            return str(candidate.absolute())
    raise RuntimeError('未找到已安装的 DeepSeek Harness。请先安装并配置，在设置中选择 dsh（Windows 为 dsh.cmd 或 dsh.exe）。不会自动下载。')


def command(path, args):
    argv = [discover(path)] + args
    if os.name == 'nt' and Path(argv[0]).suffix.lower() in ('.cmd', '.bat'):
        # Only trusted launcher/patch paths and fixed flags enter cmd; mail goes to stdin.
        if any(any(c in value for c in ('%', '!', '\r', '\n', '"')) for value in argv):
            raise RuntimeError('Harness 启动路径含不支持的字符，请换一个安装位置。')
        return [os.environ.get('COMSPEC', 'cmd.exe'), '/d', '/s', '/c', '"' + ' '.join('"' + value + '"' for value in argv) + '"']
    return argv


def complete(base='', model='', key='', messages=(), stop=None, *, cli_path=''):
    # base/model/key are intentionally unused: configuration and credentials belong to dsh.
    if stop is not None and stop.is_set():
        raise RuntimeError('分析已停止，邮件将在下次重试。')
    system = '\n\n'.join(m['content'] for m in messages if m['role'] == 'system')
    prompt = '\n\n'.join(m['content'] for m in messages if m['role'] != 'system')
    if len((system + prompt).encode()) > 2 * 1024 * 1024:
        raise ValueError('本封邮件及附件文字过大，尚未发送给 AI。')
    with tempfile.TemporaryDirectory(prefix='BensonMail-Harness-') as temporary:
        root = Path(temporary)
        patch = root / 'mail.patch.json'
        rows = [{'id': name, 'disabled': True} for name in (
            'persistent-bash', 'persistent-pwsh', 'tool-fs', 'tool-working-directory',
            'tool-bash', 'tool-pwsh', 'tool-fs-search', 'tool-jobs', 'tool-skill',
            'tool-subagent', 'tool-subagent-fork', 'tool-subagent-control',
            'tool-subagent-list-agents', 'tool-workflow', 'tool-todo', 'tool-goal',
            'tool-web', 'tool-plugin-manager', 'mcp-resources', 'plan-mode')]
        # Headless disables GUI credentials by default; reuse the installed user's saved login.
        rows += [{'id': name, 'disabled': False} for name in ('credentials', 'authorization', 'deepseek-account')]
        rows.append({'id': 'system-prompt', 'config': {
            'includeHarnessIdentity': False, 'includeRuntimeContext': False,
            'personaPrefix': system}})
        patch.write_text(json.dumps(rows, ensure_ascii=False), encoding='utf-8')
        argv = command(cli_path, ['--profile', 'headless', '--patch', str(patch), '--json'])
        flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        # Do not retain reasoning or diagnostic output. The terminal JSON event contains the answer.
        with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as source:
            source.write(prompt.encode("utf-8")); source.seek(0)
            process = subprocess.Popen(argv, stdin=source, stdout=out,
                stderr=subprocess.DEVNULL, cwd=root, creationflags=flags, start_new_session=(os.name != 'nt'))
            try:
                deadline = time.monotonic() + 180
                while process.poll() is None:
                    if stop is not None and stop.is_set():
                        raise RuntimeError('分析已停止，邮件将在下次重试。')
                    if time.monotonic() >= deadline:
                        raise RuntimeError('DeepSeek Harness 响应超时，请检查其网络及模型设置。')
                    time.sleep(.1)
                out.seek(0)
                answer = ''
                for line in out:
                    try:
                        event = json.loads(line)
                    except (ValueError, UnicodeError):
                        continue
                    if event.get('type') == 'final':
                        answer = event.get('text', '')
                if process.returncode or not isinstance(answer, str) or not answer.strip():
                    raise RuntimeError('已安装的 DeepSeek Harness 执行失败（退出码 ' + str(process.returncode) + '）。请在 Harness 中检查登录、模型与网络，并确认版本支持 headless --json。')
                return answer
            finally:
                if process.poll() is None:
                    if os.name == 'nt':
                        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                            capture_output=True, creationflags=flags, timeout=10)
                    else:
                        os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=10)

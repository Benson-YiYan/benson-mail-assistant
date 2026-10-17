"""Official Harness SDK transport, isolated per request without agent tools."""
import json
import os
from pathlib import Path
import tempfile
import sys
import subprocess
import re


DEFAULT_BASE = 'https://api.deepseek.com'
DEFAULT_MODEL = 'deepseek-v4-flash'

class HarnessFailure(RuntimeError):
    pass


def _failure_detail(text):
    match = re.search(r'\b(401|403|404|429|5\d\d)\b', text)
    if match:
        code = match.group(1)
        hint = {'401': 'API Key 无效或已过期', '403': 'Key 没有访问权限',
                '404': '基础地址或模型不存在', '429': '服务限流或额度不足'}.get(code, 'AI 服务暂时不可用')
        return f'DeepSeek Harness 请求失败（HTTP {code}）：{hint}。'
    if 'timeout' in text.lower() or 'timed out' in text.lower():
        return 'DeepSeek Harness 连接超时，请检查网络和基础地址。'
    if 'STREAM_CLOSED' in text:
        return 'DeepSeek Harness 的响应提前中断，邮件已保留，可稍后重试。'
    return 'DeepSeek Harness 连接失败，请检查基础地址、模型、API Key 及安装包完整性。'

def _sdk():
    from deepseek_harness import DeepSeekHarness
    if sys.platform == 'win32':
        import deepseek_harness.client as client
        class WindowlessProcesses:
            def __getattr__(self, name):
                return getattr(subprocess, name)
            def Popen(self, *args, **kwargs):
                kwargs['creationflags'] = kwargs.get('creationflags', 0) | subprocess.CREATE_NO_WINDOW
                return subprocess.Popen(*args, **kwargs)
        # Affect this pinned SDK's launcher only, never global subprocess calls.
        client.subprocess = WindowlessProcesses()
    return DeepSeekHarness


def complete(base, model, key, messages, stop=None):
    from .ai_api import endpoint
    endpoint(base)  # Apply the same HTTPS and credential-in-URL validation.
    if not model.strip() or not key.strip():
        raise ValueError('请填写 DeepSeek Harness 的模型名和 API Key。')
    if stop is not None and stop.is_set():
        raise RuntimeError('分析已停止，邮件将在下次重试。')
    systems = '\n\n'.join(m['content'] for m in messages if m['role'] == 'system')
    prompt = '\n\n'.join(m['content'] for m in messages if m['role'] != 'system')
    if len((systems + prompt).encode()) > 2 * 1024 * 1024:
        raise ValueError('本封邮件及附件文字过大，尚未发送给 AI。')
    try:
        DeepSeekHarness = _sdk()
        with tempfile.TemporaryDirectory(prefix='BensonMail-Harness-') as temporary:
            root = Path(temporary)
            os.chmod(root, 0o700)
            workspace = root / 'workspace'
            workspace.mkdir()
            patch = root / 'mail.patch.yml'
            rows = [{'id': name, 'disabled': True} for name in (
                'persistent-bash', 'persistent-pwsh', 'tool-fs', 'tool-working-directory')]
            rows.append({'id': 'system-prompt', 'config': {
                'includeHarnessIdentity': False, 'includeRuntimeContext': False,
                'personaPrefix': systems}})
            # JSON is also valid YAML; mail content never becomes patch syntax.
            patch.write_text(json.dumps(rows, ensure_ascii=False), encoding='utf-8')
            with DeepSeekHarness(
                dsh_home=str(root / 'home'), cwd=str(workspace), profile='sdk-minimal',
                patches=(str(patch),), provider='deepseek-official', model=model.strip(),
                base_url=base.strip().rstrip('/'), api_key=key.strip(),
                initialize_timeout_seconds=30, request_timeout_seconds=180,
                shutdown_timeout_seconds=5,
            ) as harness:
                result = harness.run(prompt)
            if stop is not None and stop.is_set():
                raise RuntimeError('分析已停止，邮件将在下次重试。')
            if result.finish_reason != 'completed' or not result.final_response.strip():
                errors = [event.get('data', {}).get('reason', {}).get('error', {})
                          for event in result.events if event.get('type') == 'turn/end']
                raise HarnessFailure(_failure_detail(json.dumps(errors)))
            return result.final_response
    except ImportError:
        raise RuntimeError('安装包缺少 DeepSeek Harness 组件，请下载最新版完整安装包。') from None
    except HarnessFailure:
        raise
    except Exception as error:
        # SDK diagnostics may include request content or credentials.
        if str(error) in (
            '分析已停止，邮件将在下次重试。',
        ):
            raise
        raise RuntimeError(_failure_detail(str(error))) from None

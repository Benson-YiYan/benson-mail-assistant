"""Exercise the external CLI adapter with a separate synthetic executable process."""
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
from benson_mail.deepseek_harness_ai import complete


def fixture():
    args = sys.argv
    assert '--profile' in args and args[args.index('--profile') + 1] == 'headless'
    assert '--json' in args
    overlay = json.loads(Path(args[args.index('--patch') + 1]).read_text(encoding='utf-8'))
    assert any(r['id'] == 'tool-fs' and r.get('disabled') for r in overlay)
    assert any(r['id'] == 'credentials' and r.get('disabled') is False for r in overlay)
    assert '原提示词逐字保持' in json.dumps(overlay, ensure_ascii=False)
    body = sys.stdin.buffer.read().decode('utf-8')
    assert body == '模拟邮件正文'
    print(json.dumps({'type': 'text', 'text': '不要把中间事件当报告'}))
    print(json.dumps({'type': 'final', 'text': '六项邮件报告完成'}))


def run():
    if getattr(sys, 'frozen', False):
        launcher = [sys.executable, '--harness-fixture']
    else:
        source = str(Path(__file__).resolve().parents[1])
        launcher = [sys.executable, '-c', 'import sys; sys.path.insert(0, ' + repr(source) + '); from benson_mail.harness_smoke import fixture; fixture()']
    # Replace discovery only; actual launch, stdin, cancellation loop and event parsing run normally.
    with patch('benson_mail.deepseek_harness_ai.command', side_effect=lambda path, args: launcher + args):
        result = complete(messages=[{'role': 'system', 'content': '原提示词逐字保持'},
                                    {'role': 'user', 'content': '模拟邮件正文'}])
    assert result == '六项邮件报告完成'
    return {'ok': True, 'checks': ['external CLI process, stdin and final-event extraction',
        'original prompt preserved and tools disabled', 'saved Harness authentication enabled',
        'synthetic child process only; no AI request or bundled Harness runtime']}

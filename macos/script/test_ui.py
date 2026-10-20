"""Launch the actual signed app bundle against synthetic temporary files only."""
import datetime
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import importlib.util
import time

project = Path(__file__).resolve().parents[1]
evidence = Path(sys.argv[1]).resolve()
app = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else project / 'dist/邮件小秘书.app'
test_options = ['--markdown-self-test-only'] if '--markdown-only' in sys.argv[3:] else []
if '--policy-only' in sys.argv[3:]:
    test_options = ['--policy-self-test-only']
evidence.mkdir(parents=True, exist_ok=True)
(evidence / 'result.json').unlink(missing_ok=True)
with tempfile.TemporaryDirectory(prefix='BensonMail-UI-test-') as temporary:
    fixture = Path(temporary)
    spec=importlib.util.spec_from_file_location('pack_builder',project.parent/'script/build_language_packs.py')
    builder=importlib.util.module_from_spec(spec); spec.loader.exec_module(builder)
    (fixture/'languages').mkdir()
    for code in ('zh','en','es'):
        (fixture/'languages'/(code+'.json')).write_text(json.dumps(builder.payload('macos',code),ensure_ascii=False))
    data = fixture / 'mail_watch'
    data.mkdir()
    output = fixture / '模拟报告'
    folder = output / '2026-10-15'
    folder.mkdir(parents=True)
    (folder / '模拟来信：合同审阅-09-02.md').write_text(
        '邮件编号：101\n1. 新邮件提醒\n合同审阅 · 2026-10-15 09:02（北京时间）\n\n'
        '## 2. 谁发的\n**演示联系人** <demo@example.invalid>\n\n'
        '3. 说了啥\n请协助审阅附件中的合同草稿。\n\n'
        '4. 我要干什么\n核对合同条款；具体截止日期尚未提供。\n\n'
        '5. 附件里有什么\n模拟附件：合同草稿，包含付款及交付条款。\n\n'
        '6. 建议回复\n收到合同草稿，我会审阅后回复。请确认希望收到反馈的日期。\n', encoding='utf-8')
    for uid, sender, body, attachments in [
        (101, '演示联系人 <demo@example.invalid>', '正文专用暗号 Zebra', [{'filename': '付款明细专用.xlsx'}]),
        (102, 'Another <bob@example.invalid>', '第二封正文', []),
    ]:
        metadata = data / str(uid)
        metadata.mkdir()
        values = {'from': sender, 'bodies': [{'type': 'text/plain', 'text': body}], 'attachments': attachments}
        if uid == 101:
            values.update(subject='原始主题-12-34', received_at='2026-10-15T01:02:00+00:00')
        (metadata / 'mail.json').write_text(json.dumps(values, ensure_ascii=False))
    earlier = output / '2026-10-14'
    earlier.mkdir()
    (earlier / '另一封模拟邮件-10-00.txt').write_text('邮件编号：102\n第二份模拟报告', encoding='utf-8')
    (fixture / 'settings.json').write_text(json.dumps({'enabled': True, 'output_dir': str(output)}))
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    (data / 'service.json').write_text(json.dumps({'phase': 'idle', 'last_check': now, 'heartbeat': now, 'pending': []}))
    subprocess.run(['/usr/bin/open', '-n', str(app), '--args', '--fixture', str(fixture), '--self-test', str(evidence), *test_options], check=True)
    for _ in range(40):
        result_file = evidence / 'result.json'
        if result_file.exists():
            result = json.loads(result_file.read_text())
            print(json.dumps(result, ensure_ascii=False, indent=2))
            sys.exit(0 if result.get('ok') else 1)
        time.sleep(1)
    raise RuntimeError('GUI self-test did not finish in 40 seconds')

"""Exercise actual JSONL process delivery, rather than simulating streamed typing."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

RUNTIME = Path(__file__).resolve().parents[1] / 'Runtime'
spec = importlib.util.spec_from_file_location('cli_stream_under_test', RUNTIME / 'cli_stream.py')
cli_stream = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli_stream)


class CLIStreamTests(unittest.TestCase):
    def test_process_delivers_event_before_tool_finishes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            script = root / 'fixture.py'
            script.write_text("import json,time,pathlib\nprint(json.dumps({'type':'text','text':'actual chunk'}),flush=True)\ndeadline=time.monotonic()+5\nwhile not pathlib.Path('received').exists() and time.monotonic()<deadline:time.sleep(.01)\npathlib.Path('finished').touch()\nprint(json.dumps({'type':'final','text':'actual chunk'}),flush=True)\n")
            received = []
            def event(value):
                if value['type'] == 'text':
                    self.assertFalse((root / 'finished').exists())
                    (root / 'received').touch()
                received.append(value)
            code = cli_stream.run_jsonl([sys.executable, str(script)], '', root, event)
            self.assertEqual(code, 0)
            self.assertEqual([v['type'] for v in received], ['text', 'final'])

    def test_only_agent_text_and_incremental_snapshot_suffixes_are_forwarded(self):
        received = []
        callback = cli_stream.codex_events(received.append)
        callback({'type':'item.completed','item':{'id':'r','type':'reasoning','text':'secret'}})
        callback({'type':'item.updated','item':{'id':'a','type':'agent_message','text':'Hello'}})
        callback({'type':'item.updated','item':{'id':'a','type':'agent_message','text':'Hello world'}})
        callback({'type':'item.completed','item':{'id':'a','type':'agent_message','text':'Hello world'}})
        callback({'type':'item.updated','item':{'id':'a','type':'agent_message','text':None}})
        self.assertEqual(received, ['Hello', ' world'])

    def test_timeout_terminates_tool(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(RuntimeError, 'AI_CLI_TIMEOUT'):
                cli_stream.run_jsonl([sys.executable, '-c', 'import time;time.sleep(10)'], '', folder, lambda _: None, timeout=.05)

    def test_harness_forwards_committed_text_without_thinking_or_final_duplication(self):
        if RUNTIME.name == 'Runtime':
            sys.path.insert(0, str(RUNTIME))
            import deepseek_harness_ai as harness
        else:
            sys.path.insert(0, str(RUNTIME.parent))
            from benson_mail import deepseek_harness_ai as harness
        with tempfile.TemporaryDirectory() as folder:
            script = Path(folder) / 'harness_fixture.py'
            script.write_text("import json\nfor event in [{'type':'thinking','text':'secret reasoning'},{'type':'text','text':'# Actual answer'},{'type':'final','text':'# Actual answer'}]:print(json.dumps(event),flush=True)\n")
            received = []
            with patch.object(harness, 'command', return_value=[sys.executable, str(script)]):
                result = harness.complete(messages=[{'role':'user','content':'question'}], on_delta=received.append)
            self.assertEqual(result, '# Actual answer')
            self.assertEqual(received, ['# Actual answer'])

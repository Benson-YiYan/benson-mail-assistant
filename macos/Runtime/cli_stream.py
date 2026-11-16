"""Bounded JSONL subprocess reader for installed AI tools; never forwards raw logs."""
import json
import os
import signal
from pathlib import Path
import subprocess
import time

MAX_EVENT_BYTES = 4 * 1024 * 1024
MAX_OUTPUT_BYTES = 16 * 1024 * 1024


def run_jsonl(args, prompt, directory, on_event, *, timeout=600, stop=None):
    directory = Path(directory)
    source_path, events_path = directory / 'prompt.input', directory / 'events.output'
    source_path.write_bytes(prompt.encode('utf-8'))
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    with source_path.open('rb') as source, events_path.open('wb') as output:
        process = subprocess.Popen(args, stdin=source, stdout=output, stderr=subprocess.DEVNULL,
            cwd=directory, creationflags=flags, start_new_session=(os.name != 'nt'))
        try:
            deadline = time.monotonic() + timeout
            pending, consumed, exited_seen = b'', 0, False
            with events_path.open('rb') as reader:
                while True:
                    if stop is not None and stop.is_set():
                        raise RuntimeError('[AI_CANCELLED] AI operation cancelled.')
                    if time.monotonic() >= deadline:
                        raise RuntimeError('[AI_CLI_TIMEOUT] AI tool timed out; existing data was preserved.')
                    chunk = reader.read(65536)
                    if chunk:
                        consumed += len(chunk)
                        if consumed > MAX_OUTPUT_BYTES:
                            raise RuntimeError('[AI_CLI_LIMIT] AI tool output exceeded the safety limit.')
                        pending += chunk
                        while b'\n' in pending:
                            line, pending = pending.split(b'\n', 1)
                            if len(line) > MAX_EVENT_BYTES:
                                raise RuntimeError('[AI_CLI_LIMIT] AI tool event exceeded the safety limit.')
                            _deliver(line, on_event)
                        if len(pending) > MAX_EVENT_BYTES:
                            raise RuntimeError('[AI_CLI_LIMIT] AI tool event exceeded the safety limit.')
                        continue
                    if process.poll() is not None:
                        if not exited_seen:
                            exited_seen = True
                            continue
                        # The exited child has closed stdout. The previous read drained all bytes.
                        if pending:
                            _deliver(pending, on_event)
                        return process.returncode
                    time.sleep(.05)
        finally:
            if process.poll() is None:
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                        capture_output=True, creationflags=flags, timeout=10)
                else:
                    os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=10)


def _deliver(line, callback):
    try:
        event = json.loads(line)
    except (ValueError, UnicodeError):
        return
    if isinstance(event, dict):
        callback(event)


def codex_events(on_delta):
    """Forward assistant message snapshots only; reasoning/tool events stay private."""
    previous = {}
    def receive(event):
        if event.get('type') not in ('item.started', 'item.updated', 'item.completed'):
            return
        item = event.get('item')
        if not isinstance(item, dict) or item.get('type') != 'agent_message':
            return
        text, identity = item.get('text'), item.get('id', 'assistant')
        if not isinstance(text, str) or not isinstance(identity, str):
            return
        old = previous.get(identity, '')
        if text.startswith(old):
            delta = text[len(old):]
            if delta:
                on_delta(delta)
            previous[identity] = text
    return receive

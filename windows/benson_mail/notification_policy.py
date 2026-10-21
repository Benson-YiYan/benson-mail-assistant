"""System notification preferences, independent of mailbox processing.

Quiet hours use the computer's current local time. Suppressed notices are
discarded, not delayed until the next morning; mail reports are still saved.
"""
import json
import re
from datetime import datetime
from pathlib import Path

DEFAULTS = {
    'notifications_enabled': True,
    'quiet_hours': {'enabled': False, 'start': '22:00', 'end': '08:00'},
}


def minute_of_day(value):
    if not isinstance(value, str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', value):
        raise ValueError('Time must use HH:mm (00:00–23:59)')
    hour, minute = map(int, value.split(':'))
    return hour * 60 + minute


def normalize_preferences(value):
    """Validate controls before saving, keeping existing unknown config intact."""
    result = {**DEFAULTS, **(value or {})}
    if not isinstance(result['notifications_enabled'], bool):
        raise ValueError('notifications_enabled must be a boolean')
    quiet = result['quiet_hours']
    if not isinstance(quiet, dict) or not isinstance(quiet.get('enabled', False), bool):
        raise ValueError('quiet_hours.enabled must be a boolean')
    quiet = {**DEFAULTS['quiet_hours'], **quiet}
    for key in ('start', 'end'):
        minute_of_day(quiet[key])
    result['quiet_hours'] = quiet
    return result


def notifications_allowed(config=None, now=None):
    """Invalid quiet-hour times cannot accidentally silence every notification."""
    value = config or {}
    if value.get('notifications_enabled', True) is False:
        return False
    quiet = value.get('quiet_hours', {})
    if not isinstance(quiet, dict):
        return True
    if quiet.get('enabled', False) is not True:
        return True
    try:
        start = minute_of_day(quiet.get('start', DEFAULTS['quiet_hours']['start']))
        end = minute_of_day(quiet.get('end', DEFAULTS['quiet_hours']['end']))
    except ValueError:
        return True
    clock = now or datetime.now().astimezone()
    minute = clock.hour * 60 + clock.minute
    if start == end:
        return False
    in_quiet_hours = start <= minute < end if start < end else minute >= start or minute < end
    return not in_quiet_hours


def read_preferences(path, fallback=None):
    """Reload settings live; preserve the last known preference on transient I/O."""
    result = dict(fallback or {})
    try:
        stored = json.loads(Path(path).read_text(encoding='utf-8'))
        if isinstance(stored, dict):
            result.update({key: stored[key] for key in DEFAULTS if key in stored})
    except (OSError, ValueError):
        pass
    return result


def notification_callback(callback, config_path, fallback=None):
    """Remove only native notification payloads; preserve report/status events."""
    def dispatch(event):
        if 'notification' in event and not notifications_allowed(read_preferences(config_path, fallback)):
            event = {key: value for key, value in event.items() if key != 'notification'}
            if not event:
                return
        callback(event)
    return dispatch

import importlib.util
import json
from datetime import datetime
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('notification_policy', Path(__file__).parents[1] / 'benson_mail' / 'notification_policy.py')
policy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(policy)


class NotificationPolicyTests(unittest.TestCase):
    def time(self, hour, minute=0):
        return datetime(2026, 10, 20, hour, minute)

    def test_defaults_allow_and_pause_is_independent(self):
        self.assertTrue(policy.notifications_allowed({'enabled': False}))
        self.assertFalse(policy.notifications_allowed({'enabled': True, 'notifications_enabled': False}))

    def test_overnight_start_inclusive_end_exclusive(self):
        config = {'quiet_hours': {'enabled': True, 'start': '22:00', 'end': '08:00'}}
        for hour, minute, allowed in [(21, 59, True), (22, 0, False), (23, 59, False), (0, 0, False), (7, 59, False), (8, 0, True)]:
            with self.subTest(hour=hour, minute=minute):
                self.assertEqual(policy.notifications_allowed(config, self.time(hour, minute)), allowed)

    def test_same_day_and_all_day(self):
        config = {'quiet_hours': {'enabled': True, 'start': '09:30', 'end': '17:00'}}
        self.assertTrue(policy.notifications_allowed(config, self.time(9, 29)))
        self.assertFalse(policy.notifications_allowed(config, self.time(9, 30)))
        self.assertTrue(policy.notifications_allowed(config, self.time(17)))
        config['quiet_hours']['end'] = '09:30'
        self.assertFalse(policy.notifications_allowed(config, self.time(3)))

    def test_invalid_time_is_rejected_on_save_and_not_silent_at_runtime(self):
        for invalid in ('24:00', '8:00', '08:60', None):
            config = {'quiet_hours': {'enabled': True, 'start': invalid, 'end': '08:00'}}
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    policy.normalize_preferences(config)
                self.assertTrue(policy.notifications_allowed(config))

    def test_live_disk_switch_preserves_reports_without_delaying_notices(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.json'
            events = []
            dispatch = policy.notification_callback(events.append, path, {'notifications_enabled': True})
            dispatch({'notification': {'title': 'new'}})
            path.write_text(json.dumps({'notifications_enabled': False}))
            dispatch({'notification': {'title': 'muted'}})
            dispatch({'notification': {'title': 'complete'}, 'report': 'mail.md', 'status': 'running'})
            self.assertEqual(events, [{'notification': {'title': 'new'}}, {'report': 'mail.md', 'status': 'running'}])
            path.write_text(json.dumps({'notifications_enabled': True}))
            dispatch({'notification': {'title': 'next'}})
            self.assertEqual(events[-1]['notification']['title'], 'next')
            self.assertEqual(len(events), 3)


if __name__ == '__main__':
    unittest.main()

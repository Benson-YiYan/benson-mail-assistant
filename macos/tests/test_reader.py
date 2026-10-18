from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Runtime'))
from worker_selftest import reader_test

class ReaderIntegrationTests(unittest.TestCase):
    def test_custom_mailbox_reader_and_state_mismatch_guard(self):
        with tempfile.TemporaryDirectory(prefix='BensonMail-reader-test-') as directory:
            reader_test(Path(directory))

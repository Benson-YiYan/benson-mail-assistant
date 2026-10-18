import hashlib
from pathlib import Path
import tempfile
import unittest
from benson_mail.installer_cleanup import verified_installer


class InstallerValidation(unittest.TestCase):
    def test_renamed_installer_and_exact_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'Renamed setup.exe'
            source.write_bytes(b'MZsynthetic installer')
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            self.assertEqual(verified_installer(source, digest), source.absolute())
            source.write_bytes(b'MZchanged after consent')
            with self.assertRaises(ValueError):
                verified_installer(source, digest)
            self.assertTrue(source.exists())

    def test_non_executable_and_directory_are_never_targets(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'report.txt'
            source.write_bytes(b'MZreport')
            with self.assertRaises(ValueError):
                verified_installer(source, hashlib.sha256(source.read_bytes()).hexdigest())
            with self.assertRaises(ValueError):
                verified_installer(directory, '0' * 64)
            self.assertTrue(source.exists())

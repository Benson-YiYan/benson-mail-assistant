"""Migration only names absent shipped files and fingerprints their exact old bytes."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('payload_manifest',Path(__file__).resolve().parents[1]/'script'/'payload_manifest.py')
manifest=importlib.util.module_from_spec(spec);spec.loader.exec_module(manifest)


class PayloadManifestTests(unittest.TestCase):
    def test_only_absent_owned_paths_are_migration_candidates(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);old=root/'old';new=root/'new';old.mkdir();new.mkdir()
            (old/'System.Windows.Forms.dll').write_bytes(b'old runtime')
            (old/'Retained.dll').write_bytes(b'old retained runtime')
            (new/'retained.dll').write_bytes(b'updated runtime')
            (old/'BensonMail-200001010000.exe').write_bytes(b'old app')
            baseline=root/'baseline.json';baseline.write_text(json.dumps(manifest.fingerprint(old)))
            manifest.migration(new,baseline)
            rows=(new/'.benson-obsolete-files.tsv').read_text().splitlines()
            self.assertEqual(rows,[manifest.fingerprint(old)['System.Windows.Forms.dll']+'\tSystem.Windows.Forms.dll'])
            self.assertTrue((new/'retained.dll').exists())
            self.assertIn('retained.dll',json.loads((new/'.benson-payload.json').read_text()))
    def test_manifest_rejects_parent_traversal(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);baseline=root/'baseline.json'
            baseline.write_text(json.dumps({'../user-report.txt':'0'*64}))
            with self.assertRaises(ValueError):manifest.migration(root,baseline)

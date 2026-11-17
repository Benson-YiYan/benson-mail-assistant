"""Regression checks for build-time translations, independent of either desktop OS."""
import copy
import json
from pathlib import Path
import re
import unittest
from build_language_packs import payload, validate_catalog, ROOT, LANGUAGES
from chinglish import transliterate


class CatalogValidationTests(unittest.TestCase):
    def test_all_shipping_languages_and_dynamic_placeholders(self):
        for platform in ('macos', 'windows'):
            english, spanish = (payload(platform, code) for code in ('en', 'es'))
            self.assertEqual(set(english['exact']), set(spanish['exact']))
            self.assertEqual([row['pattern'] for row in english['templates']],
                             [row['pattern'] for row in spanish['templates']])
            for code in LANGUAGES:
                pack = payload(platform, code)
                self.assertEqual(pack["language"], code)
                self.assertTrue(pack["guides"]["quick_start"])

    def test_chinglish_is_phonetic_and_preserves_technical_literals(self):
        self.assertEqual(transliterate("Mail Reports"), "喵·瑞泼特斯")
        self.assertEqual(transliterate("Mailbox & Checks"), "喵博克斯·&·切克斯")
        self.assertEqual(transliterate("General Settings"), "杰讷勒尔·塞听斯")
        text = "Send {0} to user@example.com [SMTP_AUTH] via `codex --version`.\nhttps://example.com/a.json"
        result = transliterate(text)
        for literal in ("{0}", "user@example.com", "[SMTP_AUTH]", "`codex --version`", "https://example.com/a.json", "\n"):
            self.assertIn(literal, result)
        self.assertNotIn("Send", result)
        for platform, folder in (("macos", "macos/Resources"), ("windows", "windows/native")):
            pack = payload(platform, "chinglish")
            self.assertEqual(pack["exact"]["邮件报告"], "喵·瑞泼特斯")
            self.assertEqual(pack["exact"]["邮箱与检查"], "喵博克斯·&·切克斯")
            self.assertEqual(pack["exact"], json.loads((ROOT/folder/"ui-chinglish.json").read_text(encoding="utf-8"))["exact"],
                             "Regenerate the checked-in native Chinglish catalog after changing English labels")
            self.assertIn("Carnegie Mellon", pack["notices"])
            self.assertNotIn("Select a report", pack["guides"]["quick_start"])

    def test_static_ui_labels_have_both_translations(self):
        for platform, folder, suffix in (("macos", "macos/Sources", "*.swift"), ("windows", "windows/native", "*.cs")):
            english = payload(platform, "en")
            missing = set()
            for source in (ROOT/folder).rglob(suffix):
                if "Test" in source.name:
                    continue
                for value in re.findall(r'(?:L\.)?T\("((?:\\.|[^"\\])*)"\)', source.read_text(encoding="utf-8")):
                    if not re.search(r'[\u3400-\u9fff]', value) or r'\(' in value:
                        continue  # Swift interpolation is covered by dynamic templates.
                    try:
                        text = json.loads('"' + value + '"')
                    except ValueError:
                        continue
                    if text not in english["exact"] and not any(re.search(row["pattern"], text, re.S) for row in english["templates"]):
                        missing.add(text)
            self.assertFalse(missing, f"{platform} untranslated UI labels: {sorted(missing)}")

    def test_source_language_leaks_and_bad_templates_stop_the_build(self):
        valid = {'exact': {'屏蔽邮件': 'Blocked mail'},
                 'templates': [{'pattern': r'^Skipped: (.*?)$', 'en': 'Skipped: {0}'}]}
        validate_catalog(valid, 'fixture', 'en')
        misplaced = copy.deepcopy(valid)
        misplaced['打开报告'] = 'Open report'
        with self.assertRaises(ValueError):
            validate_catalog(misplaced, 'fixture', 'en')
        for target in ('屏蔽邮件', ''):
            damaged = copy.deepcopy(valid)
            damaged['exact']['屏蔽邮件'] = target
            with self.assertRaises(ValueError):
                validate_catalog(damaged, 'fixture', 'en')
        for target in ('Skipped: {1}', '已屏蔽：{0}'):
            damaged = copy.deepcopy(valid)
            damaged['templates'][0]['en'] = target
            with self.assertRaises(ValueError):
                validate_catalog(damaged, 'fixture', 'en')
        damaged = copy.deepcopy(valid)
        damaged['templates'].append({'pattern': r'^Skipped: (.*?)$', 'en': 'Different: {0}'})
        with self.assertRaises(ValueError):
            validate_catalog(damaged, 'fixture', 'en')


if __name__ == '__main__':
    unittest.main()

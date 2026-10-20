"""Regression checks for build-time translations, independent of either desktop OS."""
import copy
import unittest
from build_language_packs import payload, validate_catalog


class CatalogValidationTests(unittest.TestCase):
    def test_all_shipping_languages_and_dynamic_placeholders(self):
        for platform in ('macos', 'windows'):
            english, spanish = (payload(platform, code) for code in ('en', 'es'))
            self.assertEqual(set(english['exact']), set(spanish['exact']))
            self.assertEqual([row['pattern'] for row in english['templates']],
                             [row['pattern'] for row in spanish['templates']])

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

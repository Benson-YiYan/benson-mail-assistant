"""Offline install, integrity, retry and language-preservation gates."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from benson_mail import language_packs as packs

class LanguagePackTests(unittest.TestCase):
    def payload(self,code='es',platform='windows'):
        return json.dumps({'schema_version':1,'language':code,'platform':platform,
            'exact':{'邮件小秘书':'Asistente de correo electrónico'},'templates':[],
            'guides':{'mail_account':'Pasos de configuración','quick_start':'Guía rápida'}},ensure_ascii=False).encode()
    def manifest(self,data):
        return {'schema_version':1,'language_packs':{'windows-es':{
            'url':'https://primary.example.invalid/es.json','mirrors':['https://mirror.example.invalid/es.json'],
            'size':len(data),'sha256':hashlib.sha256(data).hexdigest()}}}
    def test_missing_pack_is_not_installed_and_no_network_is_called(self):
        with tempfile.TemporaryDirectory() as root, patch.object(packs,'fetch_bytes') as fetch:
            self.assertEqual(packs.status(root,'windows')['available'],[])
            fetch.assert_not_called()
    def test_verified_install_and_account_settings_untouched(self):
        data=self.payload()
        with tempfile.TemporaryDirectory() as root:
            setting=Path(root)/'config.json'; setting.write_text('{"ui_language":"en","account":"synthetic@example.invalid"}')
            before=setting.read_bytes()
            result=packs.download(root,'es','windows',self.manifest(data),lambda _: data)
            self.assertTrue(result['ok']); self.assertEqual(Path(result['path']).read_bytes(),data)
            self.assertEqual(packs.status(root,'windows')['available'],['es'])
            self.assertEqual(setting.read_bytes(),before)
    def test_failed_primary_retries_mirror_with_independent_verified_bytes(self):
        data=self.payload(); calls=[]
        def fetch(url):
            calls.append(url)
            if 'primary' in url: raise packs.LanguagePackError('fixture transport failed')
            return data
        with tempfile.TemporaryDirectory() as root:
            self.assertTrue(packs.download(root,'es','windows',self.manifest(data),fetch)['ok'])
            self.assertEqual(len(calls),2)
            self.assertFalse(list(Path(root).rglob('*.part')))
    def test_wrong_hash_or_schema_does_not_replace_existing_pack(self):
        data=self.payload()
        with tempfile.TemporaryDirectory() as root:
            packs.download(root,'es','windows',self.manifest(data),lambda _:data)
            target=Path(root)/'languages/es.json'
            for damaged in (data+b' ',self.payload(platform='OTHER')):
                manifest=self.manifest(damaged) if b'OTHER' in damaged else self.manifest(data)
                with self.assertRaises(packs.LanguagePackError): packs.download(root,'es','windows',manifest,lambda _:damaged)
                self.assertEqual(target.read_bytes(),data)
                self.assertFalse(list(Path(root).rglob('*.part')))
    def test_unsupported_paths_and_http_urls_never_download(self):
        data=self.payload()
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(packs.LanguagePackError): packs.download(root,'../es','windows',self.manifest(data),lambda _:self.fail('must not fetch'))
            manifest=self.manifest(data); manifest['language_packs']['windows-es']['url']='http://insecure.example.invalid/es.json'
            with self.assertRaises(packs.LanguagePackError): packs.download(root,'es','windows',manifest,lambda _:self.fail('must not fetch'))
    def test_native_installed_pack_and_corrupt_cache(self):
        data=self.payload()
        with tempfile.TemporaryDirectory() as root,tempfile.TemporaryDirectory() as installed:
            directory=Path(installed)/'languages'; directory.mkdir(); (directory/'es.json').write_bytes(data)
            cache=Path(root)/'languages'; cache.mkdir(); (cache/'es.json').write_text('broken')
            self.assertEqual(packs.status(root,'windows',installed)['paths']['es'],str(directory/'es.json'))
    def test_manifest_api_fallback_uses_canonical_single_repo(self):
        calls=[]
        def fetch(url):
            calls.append(url)
            if url==packs.MANIFEST_URL: raise packs.LanguagePackError('fixture')
            return json.dumps({'schema_version':1,'language_packs':{}}).encode()
        self.assertEqual(packs.load_manifest(fetch)['schema_version'],1)
        self.assertEqual(calls,[packs.MANIFEST_URL,packs.API_URL])
        self.assertIn('benson-mail-assistant/',packs.MANIFEST_URL)
        self.assertIn('/distribution/manifest.json',packs.API_URL)

"""Exercise the slim frozen worker using synthetic local data only."""
import io
import tempfile
from pathlib import Path
import zipfile


def run():
    import ssl
    import certifi
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
    from .ai_api import tls_context
    from .core import attachment_text
    from . import platform_windows as platform
    from .mailbox_config import proxy_transport_selftest
    proxy_transport_selftest()
    context = tls_context()
    assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
    assert Path(certifi.where()).stat().st_size > 100000
    assert attachment_text('sample.txt', '附件正文'.encode()) == '附件正文'
    for suffix, name, xml in [
        ('docx', 'word/document.xml', '<document><t>Document fixture</t></document>'),
        ('pptx', 'ppt/slides/slide1.xml', '<slide><t>Slide fixture</t></slide>'),
        ('xlsx', 'xl/worksheets/sheet1.xml', '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Sheet fixture</t></is></c></row></sheetData></worksheet>')]:
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive: archive.writestr(name, xml)
        assert 'fixture' in attachment_text('sample.' + suffix, stream.getvalue())
    writer = PdfWriter(); page = writer.add_blank_page(width=100, height=100)
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): font})})
    content = DecodedStreamObject(); content.set_data(b'BT /F1 12 Tf 10 50 Td (PDF fixture) Tj ET')
    page[NameObject('/Contents')] = writer._add_object(content)
    stream = io.BytesIO(); writer.write(stream)
    assert 'PDF fixture' in attachment_text('sample.pdf', stream.getvalue())
    with tempfile.TemporaryDirectory(prefix='BensonMail-runtime-fixture-') as temporary:
        path = Path(temporary) / 'synthetic-secret.bin'
        platform.save_secret(path, 'fixture', 'SYNTHETIC-NOT-A-CREDENTIAL')
        assert platform.load_secret(path, 'fixture') == 'SYNTHETIC-NOT-A-CREDENTIAL'
        # Exercise the real frozen download module with synthetic bytes and an injected transport only.
        # This ensures its JSON/hash/atomic-write dependencies survived packaging without opening the network.
        import hashlib
        import json
        from . import language_packs
        root = Path(temporary) / 'language-fixture'
        assert language_packs.status(root, 'windows', installed=root)['available'] == []
        payload = json.dumps({'schema_version': 1, 'language': 'es', 'platform': 'windows',
            'exact': {'邮件小秘书': 'Asistente de correo electrónico'}, 'templates': [],
            'guides': {'mail_account': 'Guía de prueba', 'quick_start': 'Inicio de prueba'}}, ensure_ascii=False).encode()
        manifest = {'schema_version': 1, 'language_packs': {'windows-es': {
            'url': 'https://language-fixture.invalid/es.json', 'size': len(payload),
            'sha256': hashlib.sha256(payload).hexdigest()}}}
        fetched = []
        def synthetic_fetch(url):
            fetched.append(url)
            return payload
        outcome = language_packs.download(root, 'es', 'windows', manifest=manifest, fetch=synthetic_fetch)
        assert outcome['ok'] and Path(outcome['path']).read_bytes() == payload
        assert len(fetched) == 1 and language_packs.status(root, 'windows', installed=root)['available'] == ['es']
        try:
            language_packs.download(root, 'es', 'windows', manifest=manifest, fetch=lambda url: b'corrupted')
        except language_packs.LanguagePackError:
            pass
        else:
            raise AssertionError('Corrupted language pack was accepted')
        assert Path(outcome['path']).read_bytes() == payload
        assert not list((root / 'languages').glob('*.part'))
        from unittest.mock import patch
        from . import mail_chat
        chat_root = Path(temporary) / 'chat-fixture'
        reports = chat_root / 'reports'
        reports.mkdir(parents=True)
        (chat_root / 'config.json').write_text(json.dumps({'ui_language': 'es', 'output_dir': str(reports)}), encoding='utf-8')
        report = reports / 'synthetic.md'
        report.write_text('Original report', encoding='utf-8')
        from .report_metadata import write_metadata
        write_metadata(chat_root, report, {'subject': 'Fixture', 'body': 'Original fact 42', 'attachments': []})
        selected = chat_root / 'notes.txt'
        selected.write_text('User-selected fact 99', encoding='utf-8')
        with patch.object(mail_chat, '_complete', return_value='Informe nuevo') as model:
            mail_chat.report_retry(chat_root, report)
            assert 'español' in model.call_args.args[2][0]['content']
            mail_chat.chat_send(chat_root, report, 'Fixture question', [str(selected)])
            assert 'User-selected fact 99' in model.call_args.args[2][-1]['content']
            mail_chat.chat_send(chat_root, report, 'Fixture follow-up')
            assert 'Fixture question' in json.dumps(model.call_args.args[2])
        assert len(mail_chat.chat_history(chat_root, report)['messages']) == 4
    return {'ok': True, 'checks': [
        'Local HTTP CONNECT/SOCKS5 remote-DNS tunnels and native system proxy detection',
        'Frozen text, DOCX, PPTX, XLSX and PDF attachment readers',
        'Native certificate verification and bundled CA roots retained',
        'Current-user DPAPI round trip using synthetic local credential',
        'Frozen language module downloads synthetic verified bytes atomically and preserves packs after rejected corruption',
        'Frozen report regeneration, selected file extraction and persisted multi-turn email context use synthetic AI only',
        'No mailbox connection, AI call or external network request']}

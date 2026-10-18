"""API transport for the existing mail prompt; local attachments stay read-only."""
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile
from xml.etree import ElementTree
from ai_api import complete, endpoint
from mail_prompt import analysis_prompt
from runtime_paths import data_home

BASE = data_home()
LIMIT = 20 * 1024 * 1024

def limited(text):
    return text if len(text) <= 100000 else text[:100000] + '\n【部分读取：超过文字长度上限，后续内容未提供】'

def attachment_text(path, folder):
    try:
        path = Path(path).resolve()
        if not path.is_relative_to(folder.resolve()):
            return '【未读取：附件路径不在本封邮件目录内】'
        if path.stat().st_size > LIMIT:
            return '【未读取：附件超过20MB】'
        suffix = path.suffix.lower()
        if suffix in ('.txt', '.csv', '.md', '.json', '.xml', '.html'):
            raw = path.read_bytes()
            for encoding in ('utf-8-sig', 'gb18030', 'utf-16'):
                try: return limited(raw.decode(encoding))
                except UnicodeError: pass
            return '【未读取：无法识别文字编码】'
        if suffix in ('.docx', '.pptx', '.xlsx'):
            with zipfile.ZipFile(path) as archive:
                names = [n for n in archive.namelist() if re.fullmatch(
                    r'(word/(document|header\d+|footer\d+)|ppt/slides/slide\d+|xl/(sharedStrings|workbook|worksheets/sheet\d+))\.xml', n)]
                if sum(archive.getinfo(n).file_size for n in names) > LIMIT:
                    return '【未读取：解压后的附件文字过大】'
                shared = []
                if suffix == '.xlsx' and 'xl/sharedStrings.xml' in names:
                    root = ElementTree.fromstring(archive.read('xl/sharedStrings.xml'))
                    shared = [''.join(t.text or '' for t in item.iter() if t.tag.endswith('}t')) for item in root]
                parts = ['【Office仅提取文字，不含图片、图表和宏；Excel不计算公式，日期数字保留原值】']
                for name in names:
                    if suffix == '.xlsx' and not name.startswith('xl/worksheets/'): continue
                    root = ElementTree.fromstring(archive.read(name))
                    parts.append(name)
                    if suffix == '.xlsx':
                        for row in root.iter():
                            if row.tag.split('}')[-1] != 'row': continue
                            values = []
                            for cell in row:
                                raw = next((v.text or '' for v in cell if v.tag.endswith('}v')), '')
                                if cell.get('t') == 's':
                                    try: raw = shared[int(raw)] if int(raw) >= 0 else '【无效索引】'
                                    except (ValueError, IndexError): raw = '【无效索引】'
                                elif cell.get('t') == 'inlineStr':
                                    raw = ''.join(t.text or '' for t in cell.iter() if t.tag.endswith('}t'))
                                if any(v.tag.endswith('}f') for v in cell): raw += '【公式缓存值，未计算】'
                                values.append(cell.get('r', '?') + '=' + raw)
                            parts.append(' | '.join(values))
                    else:
                        parts.append(' '.join(t.text for t in root.iter() if t.text and t.tag.split('}')[-1] == 't'))
                return limited('\n'.join(parts))
        if suffix == '.pdf':
            try:
                from pypdf import PdfReader
                text = '\n'.join(page.extract_text() or '' for page in PdfReader(io.BytesIO(path.read_bytes())).pages)
            except ImportError:
                executable = shutil.which('pdftotext') or next((p for p in ('/opt/homebrew/bin/pdftotext', '/usr/local/bin/pdftotext') if Path(p).exists()), None)
                if not executable: return '【未读取：本机缺少PDF文字解析器】'
                result = subprocess.run([executable, str(path), '-'], capture_output=True, timeout=30)
                if result.returncode: return '【未读取：PDF损坏或加密】'
                text = result.stdout.decode('utf-8', errors='replace')
            return limited(text) if text.strip() else '【未读取：扫描PDF没有文字层】'
        return '【未读取：暂不支持此格式；图片、宏和嵌入对象未执行或识别】'
    except Exception:
        return '【未读取：附件缺失、损坏、加密或解析失败】'

def api_config():
    config = json.loads((BASE / 'settings.json').read_text())
    if config.get('ai_provider') == 'deepseek_harness':
        return config, ''
    address = endpoint(config.get('api_base', ''))
    result = subprocess.run(['/usr/bin/security', 'find-generic-password', '-s', 'BensonMail-AI-API', '-a', address, '-w'],
                            capture_output=True, text=True, timeout=30)
    if result.returncode or not result.stdout.strip():
        raise RuntimeError('未找到此基础地址的 API Key，请在设置中保存。')
    return config, result.stdout.strip()

def analyze_api(message, folder):
    config, key = api_config()
    content = dict(message)
    content['attachments'] = [dict(filename=a.get('filename', ''), type=a.get('type', ''),
        text=attachment_text(a.get('path', ''), folder)) for a in message.get('attachments', [])]
    transport = complete
    if config.get('ai_provider') == 'deepseek_harness':
        from deepseek_harness_ai import complete as transport
    options = {'cli_path': config.get('harness_path', '')} if config.get('ai_provider') == 'deepseek_harness' else {}
    return transport(config.get('api_base', ''), config.get('api_model', ''), key,
                    [{'role': 'system', 'content': analysis_prompt(config.get('ui_language'))},
                     {'role': 'user', 'content': json.dumps(content, ensure_ascii=False)}], **options)

if __name__ == '__main__':
    try:
        config, key = api_config()
        transport = complete
        if config.get('ai_provider') == 'deepseek_harness':
            from deepseek_harness_ai import complete as transport
        options = {'cli_path': config.get('harness_path', '')} if config.get('ai_provider') == 'deepseek_harness' else {}
        transport(config.get('api_base', ''), config.get('api_model', ''), key,
                 [{'role': 'user', 'content': 'Reply OK.'}], **options)
        print('AI 连接正常。')
    except Exception as error:
        # Never print server response bodies, keys or request contents.
        print(str(error) if isinstance(error, (RuntimeError, ValueError)) else 'AI 连接测试失败，请检查配置。')
        sys.exit(1)

"""Download data-only language packs from the official, TLS-verified release manifest."""
import hashlib
import json
import os
from pathlib import Path
import re
import ssl
import sys
import tempfile
import urllib.parse
import urllib.request

CODES = ('zh', 'en', 'es')
PLATFORMS = ('windows', 'macos')
MANIFEST_URL = 'https://raw.githubusercontent.com/Benson-YiYan/benson-mail-assistant/main/distribution/manifest.json'
API_URL = 'https://api.github.com/repos/Benson-YiYan/benson-mail-assistant/contents/distribution/manifest.json?ref=main'
MAX_BYTES = 2 * 1024 * 1024

class LanguagePackError(RuntimeError):
    pass

def safe_url(url):
    if not isinstance(url, str): raise LanguagePackError('Invalid language-pack URL')
    try:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username is not None or parsed.password is not None or parsed.fragment:
            raise ValueError()
        if parsed.port not in (None,443): raise ValueError()
    except ValueError:
        raise LanguagePackError('Language downloads require HTTPS without credentials or fragments') from None
    return url

def fetch_bytes(url, limit=MAX_BYTES):
    safe_url(url)
    import certifi
    import truststore
    context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.load_verify_locations(certifi.where())
    request = urllib.request.Request(url, headers={
        'User-Agent':'BensonMail-LanguagePacks/1', 'Cache-Control':'no-cache',
        'Accept':'application/vnd.github.raw+json' if 'api.github.com' == urllib.parse.urlsplit(url).hostname else 'application/json'})
    try:
        with urllib.request.urlopen(request,context=context,timeout=25) as response:
            safe_url(response.geturl())
            if response.status != 200: raise LanguagePackError('Language download returned HTTP ' + str(response.status))
            length=response.headers.get('Content-Length')
            if length and (not length.isdigit() or int(length)>limit): raise LanguagePackError('Language pack exceeds size limit')
            data=response.read(limit+1)
            if len(data)>limit: raise LanguagePackError('Language pack exceeds size limit')
            if length and len(data)!=int(length): raise LanguagePackError('Language download was incomplete')
            return data
    except LanguagePackError: raise
    except Exception as error:
        # Never echo a URL, proxy credential, response body or untrusted exception text.
        raise LanguagePackError('Language download failed ('+type(error).__name__+'); check the network and retry') from None

def validate_pack(data, code, platform):
    if code not in CODES or platform not in PLATFORMS: raise LanguagePackError('Unsupported language or platform')
    if len(data)>MAX_BYTES: raise LanguagePackError('Language pack exceeds size limit')
    try:
        value=json.loads(data)
        assert isinstance(value,dict) and value.get('schema_version')==1
        assert value.get('language')==code and value.get('platform')==platform
        exact=value['exact']; templates=value['templates']; guides=value['guides']
        assert isinstance(exact,dict) and all(isinstance(k,str) and isinstance(v,str) for k,v in exact.items())
        assert code=='zh' or len(exact)>0
        assert isinstance(templates,list) and len(templates)<=1000
        for row in templates:
            assert isinstance(row,dict) and isinstance(row.get('pattern'),str) and isinstance(row.get('en'),str)
            assert len(row['pattern'])<=4096
            re.compile(row['pattern'])
        assert isinstance(guides,dict) and all(isinstance(guides.get(k),str) and guides[k] for k in ('mail_account','quick_start'))
        return value
    except (ValueError,TypeError,KeyError,AssertionError,re.error):
        raise LanguagePackError('Invalid or incompatible language pack') from None

def pack_paths(root, platform, installed=None):
    roots=[Path(root)/'languages']
    if installed:
        roots.append(Path(installed)/'languages')
    elif getattr(sys,'frozen',False):
        base=Path(sys.executable).parent
        roots.append((base.parent if platform=='macos' else base)/'languages')
    result={}
    for code in CODES:
        for directory in roots:
            path=directory/(code+'.json')
            try:
                if path.is_symlink() or path.stat().st_size>MAX_BYTES: continue
                validate_pack(path.read_bytes(),code,platform)
                result[code]=str(path)
                break
            except (OSError,LanguagePackError): pass
    return result

def status(root,platform,installed=None):
    paths=pack_paths(root,platform,installed)
    return {'ok':True,'available':list(paths),'paths':paths}

def load_manifest(fetch=None):
    fetch=fetch or fetch_bytes
    for url in (MANIFEST_URL,API_URL):
        try:
            value=json.loads(fetch(url))
            if isinstance(value,dict) and value.get('schema_version')==1 and isinstance(value.get('language_packs'),dict): return value
        except (ValueError,LanguagePackError): pass
    raise LanguagePackError('Could not retrieve language-pack metadata; check the network and retry')

def download(root,code,platform,manifest=None,fetch=None):
    if code not in CODES or platform not in PLATFORMS: raise LanguagePackError('Unsupported language or platform')
    fetch=fetch or fetch_bytes
    manifest=manifest if manifest is not None else load_manifest(fetch)
    try:
        entry=manifest['language_packs'][platform+'-'+code]
        digest=entry['sha256']; size=entry['size']
        assert isinstance(digest,str) and re.fullmatch('[0-9a-f]{64}',digest)
        assert isinstance(size,int) and not isinstance(size,bool) and 0<size<=MAX_BYTES
        urls=[entry['url'],*entry.get('mirrors',[])]
        assert len(urls)<=8
        for url in urls: safe_url(url)
    except (KeyError,TypeError,AssertionError):
        raise LanguagePackError('Language pack is not available in the official manifest') from None
    directory=Path(root)/'languages'; directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    target=directory/(code+'.json')
    if directory.is_symlink() or target.is_symlink(): raise LanguagePackError('Language pack path must not be a symbolic link')
    last=None
    for url in dict.fromkeys(urls):
        try:
            data=fetch(url)
            if len(data)!=size or hashlib.sha256(data).hexdigest()!=digest: raise LanguagePackError('Language pack failed integrity verification')
            validate_pack(data,code,platform)
            descriptor,name=tempfile.mkstemp(prefix='.'+code+'-',suffix='.part',dir=directory)
            try:
                with os.fdopen(descriptor,'wb') as stream: stream.write(data); stream.flush(); os.fsync(stream.fileno())
                os.replace(name,target)
            finally:
                Path(name).unlink(missing_ok=True)
            return {'ok':True,'code':code,'path':str(target)}
        except (LanguagePackError,OSError) as error: last=error
    if isinstance(last,LanguagePackError): raise last
    raise LanguagePackError('Language pack could not be saved; check file permissions and retry')

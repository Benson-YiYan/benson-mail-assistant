"""Windows-only secrets, known folders and desktop integration."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

APP_NAME='BensonMail'

def require_windows():
    if sys.platform!='win32': raise RuntimeError('此功能仅支持 Windows；不保存明文授权码')

def app_dir():
    require_windows(); path=Path(os.environ['LOCALAPPDATA'])/APP_NAME; path.mkdir(parents=True,exist_ok=True); return path

def documents_dir():
    require_windows()
    class GUID(ctypes.Structure): _fields_=[('Data1',wintypes.DWORD),('Data2',wintypes.WORD),('Data3',wintypes.WORD),('Data4',ctypes.c_ubyte*8)]
    identifier=GUID.from_buffer_copy(uuid.UUID('FDD39AD0-238F-46AF-ADB4-6C85480369C7').bytes_le)
    pointer=ctypes.c_wchar_p()
    result=ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(identifier),0,None,ctypes.byref(pointer))
    if result: raise OSError('无法定位 Windows 文档文件夹')
    try: return Path(pointer.value)
    finally: ctypes.windll.ole32.CoTaskMemFree(pointer)

class Blob(ctypes.Structure): _fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]

def crypt(data,account,decrypt=False):
    require_windows(); source=ctypes.create_string_buffer(data); entropy=ctypes.create_string_buffer(account.lower().encode())
    incoming=Blob(len(data),ctypes.cast(source,ctypes.POINTER(ctypes.c_ubyte))); salt=Blob(len(entropy.raw)-1,ctypes.cast(entropy,ctypes.POINTER(ctypes.c_ubyte))); output=Blob()
    if decrypt: ok=ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(incoming),None,ctypes.byref(salt),None,None,1,ctypes.byref(output))
    else: ok=ctypes.windll.crypt32.CryptProtectData(ctypes.byref(incoming),'BensonMail',ctypes.byref(salt),None,None,1,ctypes.byref(output))
    if not ok: raise OSError('无法解密授权码，请在当前 Windows 用户下重新填写')
    try: return ctypes.string_at(output.data,output.size)
    finally: ctypes.windll.kernel32.LocalFree(output.data)

def save_secret(path,account,secret):
    data=crypt(secret.encode(),account); temporary=path.with_suffix('.tmp'); temporary.write_bytes(data); os.replace(temporary,path)

def load_secret(path,account): return crypt(path.read_bytes(),account,True).decode()

def startup_command():
    return subprocess.list2cmdline([sys.executable]+([] if getattr(sys,'frozen',False) else [str(Path(__file__).resolve().parent.parent/'main.py')])+['--background'])

def set_autostart(enabled,name=APP_NAME):
    require_windows(); import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Run') as key:
        if enabled: winreg.SetValueEx(key,name,0,winreg.REG_SZ,startup_command())
        else:
            try: winreg.DeleteValue(key,name)
            except FileNotFoundError: pass

def has_autostart(name=APP_NAME):
    require_windows(); import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Run') as key:
        try: return bool(winreg.QueryValueEx(key,name)[0])
        except FileNotFoundError: return False

def resolve_cli(path):
    path=Path(path)
    if path.suffix.lower() in ('.cmd','.bat'):
        # npm launchers point to the packaged native binary or the JS entrypoint.
        package=path.parent/'node_modules'/'@openai'/'codex'
        for candidate in package.glob('vendor/**/codex.exe'):
            if 'x86_64' in str(candidate): return [str(candidate)]
        for candidate in package.glob('node_modules/**/codex.exe'):
            if 'x64' in str(candidate) or 'x86_64' in str(candidate): return [str(candidate)]
        for package_name in ('codex-win32-x64','codex-win32-x64-msvc'):
            for candidate in (package.parent/package_name).glob('vendor/**/codex.exe'):
                return [str(candidate)]
        node=shutil.which('node.exe') or shutil.which('node')
        if node and (package/'bin'/'codex.js').exists(): return [node,str(package/'bin'/'codex.js')]
        return None
    if path.suffix.lower() not in ('.exe','') or not path.is_file(): return None
    return [str(path)]

def verify_codex(command,timeout=12):
    if not command: return False
    try:
        result=subprocess.run(list(command)+['exec','--help'],capture_output=True,timeout=timeout,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        text=(result.stdout+result.stderr).decode('utf-8',errors='replace').lower()
        return result.returncode==0 and '--ephemeral' in text and '--sandbox' in text
    except (OSError,subprocess.TimeoutExpired): return False

def discover_codex():
    candidates=[]
    for name in ('codex.exe','codex.cmd','codex'):
        found=shutil.which(name)
        if found: candidates.append(Path(found))
    roots=[Path(os.environ.get('LOCALAPPDATA',''))/'Programs',Path(os.environ.get('LOCALAPPDATA',''))/'Microsoft'/'WindowsApps',Path(os.environ.get('ProgramFiles','C:/Program Files'))/'WindowsApps',Path(os.environ.get('ProgramFiles','C:/Program Files'))/'Codex']
    for root in roots:
        if not root.exists(): continue
        try:
            for pattern in ('**/resources/codex.exe','**/resources/bin/codex.exe','**/resources/app.asar.unpacked/**/codex.exe','OpenAI.Codex*/**/codex.exe','**/vendor/*/codex/codex.exe'):
                candidates.extend(root.glob(pattern))
        except OSError: continue
    seen=set()
    for candidate in candidates:
        if str(candidate).lower() in seen: continue
        seen.add(str(candidate).lower()); command=resolve_cli(candidate)
        if verify_codex(command): return command
    return []

class SingleInstance:
    def __init__(self):
        require_windows(); kernel=ctypes.windll.kernel32; kernel.CreateMutexW.restype=wintypes.HANDLE
        kernel.CloseHandle.argtypes=[wintypes.HANDLE]
        kernel.CreateMutexW.argtypes=[ctypes.c_void_p,wintypes.BOOL,wintypes.LPCWSTR]
        self.handle=kernel.CreateMutexW(None,False,'Local\\BensonMail-'+os.environ.get('USERNAME','user'))
        self.already_running=kernel.GetLastError()==183
    def close(self):
        if self.handle: ctypes.windll.kernel32.CloseHandle(self.handle); self.handle=None

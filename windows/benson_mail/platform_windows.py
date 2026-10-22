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

def startup_command(launcher=None):
    if launcher: return subprocess.list2cmdline([str(launcher),'--background'])
    return subprocess.list2cmdline([sys.executable]+([] if getattr(sys,'frozen',False) else [str(Path(__file__).resolve().parent.parent/'main.py')])+['--background'])

def create_shortcut(launcher, label, destination_folder, previous=None):
    """Create or update our target without overwriting another application link."""
    require_windows()
    import pythoncom
    from win32com.shell import shell, shellcon
    launcher = Path(launcher).resolve()
    if not launcher.is_file():
        raise FileNotFoundError('找不到邮件小秘书主程序')
    pythoncom.CoInitialize()
    try:
        desktop = Path(destination_folder)
        desktop.mkdir(parents=True, exist_ok=True)
        number = 1
        while True:
            candidate = label if number == 1 else f'{label} ({number})'
            destination = desktop / (candidate + '.lnk')
            link = pythoncom.CoCreateInstance(shell.CLSID_ShellLink, None, pythoncom.CLSCTX_INPROC_SERVER,
                                             shell.IID_IShellLink)
            if destination.exists():
                try:
                    link.QueryInterface(pythoncom.IID_IPersistFile).Load(str(destination))
                    existing = Path(link.GetPath(shell.SLGP_RAWPATH)[0]).resolve()
                    if existing not in {launcher, Path(previous).resolve() if previous else launcher}:
                        number += 1
                        continue
                except pythoncom.com_error:
                    number += 1
                    continue
            link.SetPath(str(launcher))
            link.SetArguments('')
            link.SetWorkingDirectory(str(launcher.parent))
            link.SetDescription(label)
            link.SetIconLocation(str(launcher), 0)
            link.QueryInterface(pythoncom.IID_IPersistFile).Save(str(destination), 1)
            return destination
    finally:
        pythoncom.CoUninitialize()

def create_desktop_shortcut(launcher, previous=None, desktop=None):
    require_windows()
    from win32com.shell import shell, shellcon
    desktop = desktop or shell.SHGetFolderPath(0, shellcon.CSIDL_DESKTOPDIRECTORY, None, 0)
    return create_shortcut(launcher, '邮件小秘书', desktop, previous)


def matching_uninstaller(launcher):
    """Never pair a versioned app with an uninstaller from a different release."""
    import re
    launcher = Path(launcher).resolve()
    match = re.fullmatch(r'BensonMail-(\d{12})\.exe', launcher.name, re.IGNORECASE)
    name = 'Uninstall-BensonMail-' + match.group(1) + '.exe' if match else 'Uninstall.exe'
    target = launcher.parent / name
    if not target.is_file():
        raise FileNotFoundError('找不到此版本的邮件小秘书卸载程序')
    return target


def ensure_portable_shortcuts(launcher, marker, desktop=None, programs=None):
    """Migrate legacy portable installs once. Installed editions use installer choices."""
    launcher = Path(launcher).resolve()
    if (launcher.parent / '.benson-installed.json').is_file():
        return False
    marker = Path(marker)
    try:
        recorded = json.loads(marker.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        recorded = {}
    if recorded.get('schema') == 2 and recorded.get('launcher') == str(launcher):
        return False  # A user deleting a shortcut must not cause it to reappear.
    require_windows()
    from win32com.shell import shell, shellcon
    desktop = Path(desktop or shell.SHGetFolderPath(0, shellcon.CSIDL_DESKTOPDIRECTORY, None, 0))
    programs = Path(programs or shell.SHGetFolderPath(0, shellcon.CSIDL_PROGRAMS, None, 0))
    previous = recorded.get('launcher')
    old_uninstaller = None
    if previous:
        import re
        match = re.fullmatch(r'BensonMail-(\d{12})\.exe', Path(previous).name, re.IGNORECASE)
        old_uninstaller = Path(previous).parent / ('Uninstall-BensonMail-' + match.group(1) + '.exe' if match else 'Uninstall.exe')
    uninstaller = matching_uninstaller(launcher)
    created = []
    for place in (desktop, programs):
        created.append(str(create_shortcut(launcher, '邮件小秘书', place, previous)))
        created.append(str(create_shortcut(uninstaller, '卸载邮件小秘书', place, old_uninstaller)))
    from .core import save_json
    save_json(marker, {'schema': 2, 'launcher': str(launcher), 'links': created})
    return True


def remove_uninstall_registration(folder, name='BensonMail'):
    """An old release must never remove a newer release's Installed Apps entry."""
    require_windows()
    import winreg
    key_path = r'Software\Microsoft\Windows\CurrentVersion\Uninstall' + '\\' + name
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            location = winreg.QueryValueEx(key, 'InstallLocation')[0]
    except FileNotFoundError:
        return
    if Path(location).resolve() == Path(folder).resolve():
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key_path)


def set_autostart(enabled,name=APP_NAME,launcher=None):
    require_windows(); import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Run') as key:
        if enabled: winreg.SetValueEx(key,name,0,winreg.REG_SZ,startup_command(launcher))
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
    # App execution aliases can launch the desktop GUI; use the package location instead.
    if path.parent.name.lower() == 'windowsapps': return None
    # Selecting an installation folder or its Electron launcher resolves to the CLI.
    if path.is_dir() or (path.parent/'resources'/'app.asar').exists():
        root = path if path.is_dir() else path.parent
        for pattern in ('resources/codex.exe', 'resources/bin/codex.exe', 'app/resources/codex.exe', 'resources/app.asar.unpacked/**/codex.exe', 'resources/**/codex.exe'):
            for candidate in root.glob(pattern):
                if candidate.is_file(): return [str(candidate)]
        return None
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

def codex_selection_path(command):
    """Return a path the settings editor can resolve again on Save."""
    if len(command) == 1: return command[0]
    if len(command) == 2:
        script=Path(command[1])
        if script.name == 'codex.js' and len(script.parents) > 4:
            shim=script.parents[4]/'codex.cmd'
            if shim.is_file(): return str(shim)
    raise ValueError('未找到可用的 Codex 命令行程序，请选择 resources 下的 codex.exe。')


def verify_codex(command,timeout=12):
    if not command: return False
    if len(command) == 1 and (Path(command[0]).parent/'resources'/'app.asar').exists(): return False
    try:
        result=subprocess.run(list(command)+['exec','--help'],capture_output=True,timeout=timeout,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        text=(result.stdout+result.stderr).decode('utf-8',errors='replace').lower()
        return result.returncode==0 and '--ephemeral' in text and '--sandbox' in text
    except (OSError,subprocess.TimeoutExpired): return False

def codex_store_locations():
    """Ask the package registry; WindowsApps itself is often not enumerable."""
    if sys.platform != 'win32': return []
    try:
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
            "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); Get-AppxPackage *Codex* | Select-Object -ExpandProperty InstallLocation | ConvertTo-Json -Compress"],
            capture_output=True, text=True, encoding='utf-8', timeout=12,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        value = json.loads(result.stdout) if result.returncode == 0 and result.stdout.strip() else []
        return [Path(p) for p in ([value] if isinstance(value, str) else value) if isinstance(p, str) and p]
    except (OSError, ValueError, subprocess.TimeoutExpired): return []


def codex_registered_locations():
    """Read per-user/machine uninstall metadata, including custom installation drives."""
    if sys.platform != 'win32': return []
    import winreg
    roots=[]
    key_path=r'Software\Microsoft\Windows\CurrentVersion\Uninstall'
    for hive in (winreg.HKEY_CURRENT_USER,winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_64KEY,winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(hive,key_path,0,winreg.KEY_READ|view) as parent:
                    for index in range(winreg.QueryInfoKey(parent)[0]):
                        try:
                            with winreg.OpenKey(parent,winreg.EnumKey(parent,index)) as key:
                                name=str(winreg.QueryValueEx(key,'DisplayName')[0])
                                if 'codex' not in name.lower(): continue
                                for field in ('InstallLocation','DisplayIcon'):
                                    try: value=str(winreg.QueryValueEx(key,field)[0]).strip()
                                    except OSError: continue
                                    if not value: continue
                                    if field == 'DisplayIcon':
                                        value=value.rsplit(',',1)[0].strip().strip('"')
                                        roots.append(Path(os.path.expandvars(value)).parent)
                                    else: roots.append(Path(os.path.expandvars(value.strip('"'))))
                        except OSError: continue
            except OSError: continue
    return list(dict.fromkeys(roots))


def discover_codex():
    candidates=[]
    for name in ('codex.exe','codex.cmd','codex'):
        found=shutil.which(name)
        if found: candidates.append(Path(found))
    local=Path(os.environ.get('LOCALAPPDATA', str(Path.home()/'AppData/Local')))
    roaming=Path(os.environ.get('APPDATA', str(Path.home()/'AppData/Roaming')))
    candidates.extend([roaming/'npm/codex.cmd', local/'Microsoft/WindowsApps/codex.exe'])
    roots=codex_store_locations()+codex_registered_locations()+[local/'Programs/Codex',local/'Codex',Path(os.environ.get('ProgramFiles','C:/Program Files'))/'Codex']
    # Squirrel and Store layouts differ; inspect only Codex installation roots.
    programs=local/'Programs'
    try:
        if programs.is_dir(): roots.extend(p for p in programs.iterdir() if 'codex' in p.name.lower())
    except OSError: pass
    for root in roots:
        if not root.exists(): continue
        try:
            for pattern in ('resources/codex.exe','resources/bin/codex.exe','app/resources/codex.exe',
                            'app-*/resources/codex.exe','resources/app.asar.unpacked/**/codex.exe',
                            'app/resources/app.asar.unpacked/**/codex.exe','resources/**/codex.exe','app/resources/**/codex.exe'):
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


def work_area():
    """Usable primary desktop excluding the taskbar."""
    require_windows()
    rectangle=wintypes.RECT()
    if not ctypes.windll.user32.SystemParametersInfoW(48,0,ctypes.byref(rectangle),0):
        raise OSError('无法读取 Windows 桌面工作区域')
    return rectangle.left,rectangle.top,rectangle.right,rectangle.bottom

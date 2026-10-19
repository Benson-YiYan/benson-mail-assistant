"""Stage an independent native Python helper before deleting an installation."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import uuid


def installation(path):
    folder = Path(path).resolve()
    installed = False
    try:
        installed = json.loads((folder / '.benson-installed.json').read_text(encoding='utf-8')).get('installed') is True
    except (OSError, ValueError, AttributeError):
        pass
    if not (folder / '_internal').is_dir() or not (installed or re.fullmatch(r'BensonMail(?:-\d{12})?', folder.name)):
        raise ValueError('程序目录名称或结构不符，请手动删除当前解压文件夹。')
    return folder


def report_files(directory):
    root = Path(directory).resolve()
    found = []
    if not root.is_dir():
        return found
    for day in root.iterdir():
        if day.is_symlink() or (hasattr(day, 'is_junction') and day.is_junction()) or not day.is_dir() or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', day.name):
            continue
        for metadata in day.glob('*.mail.json'):
            if metadata.is_symlink():
                continue
            try:
                value = json.loads(metadata.read_text(encoding='utf-8'))
                if not isinstance(value, dict) or not all(k in value for k in ('subject', 'sender', 'received')):
                    continue
            except (ValueError, OSError):
                continue
            for suffix in ('.txt', '.md'):
                text = metadata.with_name(metadata.name[:-10] + suffix)
                if text.is_file() and not text.is_symlink():
                    found.append(text)
            found.append(metadata)
    return found


def remove_reports(directory):
    files = report_files(directory)
    for path in files:
        path.unlink(missing_ok=True)
    root = Path(directory).resolve()
    folders = {p.parent for p in files}
    if root.is_dir():
        folders.update(day for day in root.iterdir() if re.fullmatch(r'\d{4}-\d{2}-\d{2}', day.name)
                       and not day.is_symlink() and not (hasattr(day, 'is_junction') and day.is_junction()))
    for folder in folders:
        try:
            folder.rmdir()
        except OSError:
            pass
    # The user may have selected Documents itself; keep the chosen root folder.
    return len(files)


def copy_runtime(folder, executable):
    source = installation(folder)
    temporary = Path(tempfile.mkdtemp(prefix='BensonMail-uninstall-'))
    try:
        shutil.copytree(source / '_internal', temporary / '_internal')
        shutil.copy2(source / executable, temporary / executable)
        (temporary / '.benson-uninstall-helper').write_text('temporary runtime', encoding='utf-8')
        return temporary / executable
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def wait_for_parent(pid):
    if pid <= 0:
        return
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x00100000, False, pid)
    if not handle:
        if ctypes.get_last_error() == 87:  # The process has already exited.
            return
        raise OSError('无法确认原卸载程序已退出，请关闭后重试。')
    try:
        if kernel.WaitForSingleObject(handle, 120000) != 0:
            raise OSError('等待原卸载程序退出超时，尚未删除程序目录。')
    finally:
        kernel.CloseHandle(handle)


def remove_shortcuts(folder, places=None):
    """Resolve .lnk targets through native COM, without launching PowerShell."""
    import pythoncom
    from win32com.shell import shell, shellcon
    pythoncom.CoInitialize()
    try:
        if places is None:
            places = [shell.SHGetFolderPath(0, value, None, 0) for value in (
                shellcon.CSIDL_DESKTOPDIRECTORY, shellcon.CSIDL_STARTMENU, shellcon.CSIDL_STARTUP)]
            places.append(str(Path(os.environ['APPDATA']) / 'Microsoft/Internet Explorer/Quick Launch/User Pinned/TaskBar'))
        for place in set(map(str, places)):
            root = Path(place)
            if not place or not root.is_dir():
                continue
            removed_parents = set()
            for link in root.rglob('*.lnk'):
                if link.is_symlink():
                    continue
                try:
                    shortcut = pythoncom.CoCreateInstance(shell.CLSID_ShellLink, None, pythoncom.CLSCTX_INPROC_SERVER,
                                                          shell.IID_IShellLink)
                    shortcut.QueryInterface(pythoncom.IID_IPersistFile).Load(str(link))
                    target = shortcut.GetPath(shell.SLGP_RAWPATH)[0]
                except (pythoncom.com_error, OSError):
                    continue  # An unrelated broken link must not prevent uninstall.
                if (target and Path(target).resolve().parent == Path(folder).resolve()
                        and re.fullmatch(r'(?:BensonMail(?:-\d{12})?|Uninstall(?:-BensonMail-\d{12})?)\.exe',
                                         Path(target).name, re.IGNORECASE)):
                    link.unlink()
                    removed_parents.add(link.parent)
            for parent in sorted(removed_parents, key=lambda p: len(p.parts), reverse=True):
                if parent != root and parent.name in ('邮件小秘书', 'BensonMail', 'Mail Secretary'):
                    try:
                        parent.rmdir()
                    except OSError:
                        pass
    finally:
        pythoncom.CoUninitialize()


def clear_user_data(data, keep_configuration=False):
    """Retain only settings and encrypted credentials, never cached email bodies."""
    data = Path(data)
    if data.is_symlink():
        data.unlink()
        return
    if not data.exists():
        return
    keep = {'config.json', 'secret.bin', 'mail-secrets', 'api-keys'} if keep_configuration else set()
    for path in data.iterdir():
        junction = hasattr(path, 'is_junction') and path.is_junction()
        if path.name in keep and not path.is_symlink() and not junction:
            if path.is_file() or path.name in ('mail-secrets', 'api-keys'):
                if path.is_dir():
                    for child in path.iterdir():
                        if hasattr(child, 'is_junction') and child.is_junction():
                            child.rmdir()
                            continue
                        if child.is_file() and not child.is_symlink() and child.suffix == '.bin':
                            continue
                        if child.is_dir() and not child.is_symlink():
                            shutil.rmtree(child)
                        else:
                            child.unlink()
                    try:
                        path.rmdir()
                    except OSError:
                        pass
                continue
        if path.is_dir() and not path.is_symlink() and not junction:
            shutil.rmtree(path)
        elif junction:
            path.rmdir()
        else:
            path.unlink()
    if not keep_configuration:
        data.rmdir()
    else:
        try:
            data.rmdir()  # No retained configuration means no reason to leave an empty root.
        except OSError:
            pass


def cleanup_installation(folder, data, delete_saved_reports, progress, registry_name='BensonMail', shortcut_places=None,
                         keep_configuration=False):
    from . import platform_windows as platform
    folder = installation(folder)
    if Path(sys.executable).resolve().is_relative_to(folder):
        raise RuntimeError('独立卸载进程仍在程序目录中，已停止删除。')
    data = Path(data)
    try:
        config = json.loads((data / 'config.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        config = {}
    if delete_saved_reports and config.get('output_dir'):
        progress('正在删除选中的邮件报告…')
        remove_reports(config['output_dir'])
        report_root = Path(config['output_dir']).resolve()
        if report_root == (platform.documents_dir() / '邮件').resolve():
            try:
                report_root.rmdir()
            except OSError:
                pass
    elif config.get('output_dir'):
        report_root = Path(config['output_dir']).resolve()
        if report_root.is_relative_to(folder) or report_root.is_relative_to(data.resolve()):
            files = report_files(report_root)
            if files:
                preserved = platform.documents_dir() / ('邮件-卸载保留-' + uuid.uuid4().hex[:8])
                if preserved.resolve().is_relative_to(folder) or preserved.resolve().is_relative_to(data.resolve()):
                    raise OSError('报告保留位置仍位于待卸载目录中，请先修改报告保存位置。')
                preserved.mkdir(parents=True)
                for source in files:
                    target = preserved / source.relative_to(report_root)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(source), str(target))
                config['output_dir'] = str(preserved)
                (data / 'config.json').write_text(json.dumps(config, ensure_ascii=False), encoding='utf-8')
                progress('已将程序或数据目录中的报告保留到：' + str(preserved))
    progress('正在清理自启动注册表项…')
    platform.set_autostart(False, registry_name)
    platform.remove_uninstall_registration(folder, registry_name)
    progress('正在清理指向本次安装的快捷方式…')
    remove_shortcuts(folder, shortcut_places)
    progress('正在保留邮箱及 AI 配置、清理缓存…' if keep_configuration else '正在清理配置、加密密钥和缓存…')
    clear_user_data(data, keep_configuration)
    progress('正在删除程序目录…')
    shutil.rmtree(folder)
    remove_empty_archive_wrapper(folder)
    if folder.exists() or (data.exists() and not keep_configuration):
        raise OSError('部分目录仍然存在，请关闭占用它们的程序后重试。')


def remove_empty_archive_wrapper(folder):
    """Explorer Extract All adds this known same-version wrapper around old ZIPs."""
    folder = Path(folder)
    match = re.fullmatch(r'BensonMail-(\d{12})', folder.name)
    if not match or folder.parent.name != 'BensonMail-Windows-x64-' + match.group(1):
        return False
    try:
        folder.parent.rmdir()  # Never remove siblings, user files, or arbitrary ancestors.
        return True
    except OSError:
        return False


def schedule_helper_removal():
    """cmd only removes our temporary runtime after this Python process exits."""
    folder = Path(sys.executable).resolve().parent
    if (folder.parent != Path(tempfile.gettempdir()).resolve()
            or not folder.name.startswith('BensonMail-uninstall-')
            or not (folder / '.benson-uninstall-helper').is_file()):
        return
    environment = os.environ.copy()
    environment['BENSON_MAIL_REMOVE_TEMP'] = str(folder)
    handle, filename = tempfile.mkstemp(prefix='BensonMail-cleanup-', suffix='.cmd')
    with os.fdopen(handle, 'w', encoding='ascii', newline='') as stream:
        stream.write(
            '@echo off\r\n'
            'for /L %%i in (1,1,30) do (\r\n'
            'rmdir /s /q "%BENSON_MAIL_REMOVE_TEMP%" 2>nul\r\n'
            'if not exist "%BENSON_MAIL_REMOVE_TEMP%" goto done\r\n'
            'ping -n 2 127.0.0.1 >nul\r\n'
            ')\r\n:done\r\ndel "%~f0" >nul 2>nul\r\n')
    cmd = str(Path(os.environ['SystemRoot']) / 'System32/cmd.exe')
    subprocess.Popen(
        f'"{cmd}" /d /s /v:off /c ""{filename}""', executable=cmd,
        env=environment, cwd=tempfile.gettempdir(), creationflags=subprocess.CREATE_NO_WINDOW,
        close_fds=True,
    )


def fixture_data(folder):
    parent = folder.parent.resolve()
    if (parent.parent != Path(tempfile.gettempdir()).resolve()
            or not parent.name.startswith('BensonMail-uninstall-fixture-')
            or not (parent / '.benson-uninstall-fixture').is_file()):
        raise ValueError('测试模式只允许专用临时夹具目录。')
    return parent / 'user-data'


def main(test_result=None, worker_folder=None, parent_pid=0, delete_saved_reports=False, fixture_result=None,
         keep_configuration=False):
    import tkinter as tk
    from tkinter import ttk, messagebox
    from . import platform_windows as platform

    folder = Path(worker_folder or Path(sys.executable).parent).resolve()
    data = fixture_data(folder) if fixture_result else Path(os.environ['LOCALAPPDATA']) / 'BensonMail'
    try:
        config = {} if test_result else json.loads((data / 'config.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        config = {}
    reports = config.get('output_dir', '')
    root = tk.Tk()
    from .app_icon import apply_window_icon
    apply_window_icon(root)
    root.title('卸载邮件小秘书')
    root.geometry('720x580')
    root.resizable(False, False)
    root.configure(background='#f3f3f3')
    style = ttk.Style(root)
    style.theme_use('clam')
    root.option_add('*Font', '{Microsoft YaHei UI} 10')
    style.configure('.', background='#f3f3f3', foreground='#202020', font=('Microsoft YaHei UI', 10))
    style.configure('TButton', background='#ffffff', padding=(18, 8), borderwidth=1)
    style.map('TButton', background=[('active', '#e9e9e9')])
    style.configure('Accent.TButton', background='#0067c0', foreground='#ffffff')
    style.map('Accent.TButton', background=[('active', '#005aab'), ('disabled', '#c5c5c5')])
    style.configure('TCheckbutton', padding=(0, 8))
    style.configure('TProgressbar', background='#0067c0', troughcolor='#e5e5e5')
    frame = ttk.Frame(root, padding=28)
    frame.pack(fill='both', expand=True)
    ttk.Label(frame, text='卸载邮件小秘书', font=('Microsoft YaHei UI', 18)).pack(anchor='w')
    ttk.Label(frame, text='请先从右下角托盘退出邮件小秘书。\n删除程序、缓存、自启动项及快捷方式；您可以选择保留配置，方便下次安装。',
              wraplength=610).pack(anchor='w', pady=12)
    ttk.Label(frame, text=f'程序目录：{folder}\n数据目录：{data}', wraplength=610).pack(anchor='w', pady=8)
    delete_reports = tk.BooleanVar(value=delete_saved_reports)
    keep_config = tk.BooleanVar(value=keep_configuration)
    preserve_checkbox = ttk.Checkbutton(frame, text='保留邮箱及 AI 配置，下次重装不用再配置', variable=keep_config)
    preserve_checkbox.pack(anchor='w')
    ttk.Label(frame, text='配置和加密密钥仅供本机同一 Windows 用户使用。缓存会清除，重装后重新记录收信起点。',
              wraplength=650).pack(anchor='w')
    checkbox = ttk.Checkbutton(frame, text='同时删除当前保存目录中的邮件报告及邮件索引', variable=delete_reports)
    checkbox.pack(anchor='w')
    ttk.Label(frame, text=f'报告目录：{reports or "未配置"}\n只删除可识别的报告和索引，保留其他文件及自选根目录。',
              wraplength=610).pack(anchor='w', pady=8)
    status = tk.StringVar(value='卸载操作会在独立临时目录中执行。')
    ttk.Label(frame, textvariable=status, wraplength=610).pack(anchor='w', pady=8)
    bar = ttk.Progressbar(frame, mode='indeterminate')
    bar.pack(fill='x')
    controls = ttk.Frame(frame)
    controls.pack(side='bottom', fill='x', pady=12)
    cancel = ttk.Button(controls, text='取消', command=root.destroy)
    cancel.pack(side='right', padx=10)
    action = ttk.Button(controls, text='卸载', style='Accent.TButton')
    action.pack(side='right')
    events = queue.Queue()
    active = False
    instance = None

    def write_fixture(ok, detail=None):
        if fixture_result:
            Path(fixture_result).write_text(json.dumps({
                'ok': ok, 'detail': detail, 'helper': str(Path(sys.executable).parent),
                'target': str(folder), 'data': str(data),
                'checks': ['independent helper outside program directory',
                           'responsive native GUI', 'full installation and user data cleanup']
            }, ensure_ascii=False), encoding='utf-8')

    def set_busy():
        nonlocal active
        active = True
        checkbox.configure(state='disabled')
        preserve_checkbox.configure(state='disabled')
        action.configure(state='disabled')
        cancel.configure(state='disabled')
        bar.start(12)

    def cleanup():
        local_instance = None
        try:
            events.put(('progress', '正在等待原卸载程序退出…'))
            wait_for_parent(parent_pid)
            local_instance = platform.SingleInstance()
            if local_instance.already_running:
                raise RuntimeError('邮件小秘书仍在运行，请先从托盘退出后重试。')
            cleanup_installation(folder, data, delete_saved_reports,
                                 lambda text: events.put(('progress', text)),
                                 registry_name='BensonMail-UninstallFixture' if fixture_result else 'BensonMail',
                                 shortcut_places=[folder.parent / 'shortcuts'] if fixture_result else None,
                                 keep_configuration=keep_configuration)
            events.put(('done', None))
        except Exception as error:
            events.put(('error', f'{type(error).__name__}：{error}'))
        finally:
            if local_instance:
                local_instance.close()

    def start():
        nonlocal instance
        try:
            installation(folder)
            instance = platform.SingleInstance()
            if instance.already_running:
                instance.close()
                instance = None
                messagebox.showwarning('请先退出', '请从邮件小秘书的托盘菜单选择“退出”，然后再点击卸载。', parent=root)
                return
            if not fixture_result and not messagebox.askyesno('确认卸载', '确定卸载并删除以上数据吗？此操作无法撤销。',
                                                             parent=root, default='no'):
                instance.close()
                instance = None
                return
            set_busy()
            status.set('正在准备独立卸载进程，窗口可正常响应…')

            def prepare():
                try:
                    helper = copy_runtime(folder, Path(sys.executable).name)
                    events.put(('ready', helper))
                except Exception as error:
                    events.put(('error', f'准备卸载程序失败：{error}'))
            threading.Thread(target=prepare, daemon=True).start()
        except Exception as error:
            messagebox.showerror('无法开始卸载', str(error), parent=root)

    def poll():
        nonlocal active, instance
        while True:
            try:
                event, value = events.get_nowait()
            except queue.Empty:
                break
            if event == 'progress':
                status.set(value)
            elif event == 'ready':
                args = [str(value), '--uninstall-worker', str(folder), '--parent-pid', str(os.getpid())]
                if delete_reports.get():
                    args.append('--delete-reports')
                if keep_config.get():
                    args.append('--keep-configuration')
                if fixture_result:
                    args += ['--fixture-result', str(fixture_result)]
                try:
                    subprocess.Popen(args, cwd=tempfile.gettempdir(), close_fds=True,
                                     creationflags=subprocess.CREATE_NO_WINDOW)
                    root.destroy()
                    return
                except OSError as error:
                    shutil.rmtree(value.parent, ignore_errors=True)
                    events.put(('error', f'无法启动独立卸载进程：{error}'))
            elif event in ('done', 'error'):
                active = False
                bar.stop()
                if instance:
                    instance.close()
                    instance = None
                success = event == 'done'
                status.set(('卸载完成：已保留邮箱及 AI 配置，缓存和程序已清理。' if keep_configuration else
                            '卸载完成：程序目录、配置、密钥、缓存和自启动项已清理。') if success else '卸载未完成：' + value)
                root.title('卸载完成' if success else '卸载未完成')
                action.configure(text='完成' if success else '关闭', command=root.destroy, state='normal')
                cancel.pack_forget()
                write_fixture(success, value)
                if fixture_result:
                    root.after(200, root.destroy)
        root.after(100, poll)

    action.configure(command=start)
    root.protocol('WM_DELETE_WINDOW', lambda: None if active else root.destroy())
    root.after(100, poll)
    def windows_corners():
        try:
            from ctypes import wintypes
            ctypes.windll.user32.GetParent.restype = wintypes.HWND
            hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
            preference = ctypes.c_int(2)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(wintypes.HWND(hwnd), 33, ctypes.byref(preference), 4)
        except (OSError, AttributeError):
            pass
    root.after(50, windows_corners)
    if test_result:
        def verify_ui():
            root.update_idletasks()
            assert root.winfo_viewable() and not delete_reports.get() and not keep_config.get()
            assert preserve_checkbox.winfo_viewable()
            from PIL import ImageGrab
            x, y = root.winfo_rootx(), root.winfo_rooty()
            ImageGrab.grab(bbox=(x, y, x + root.winfo_width(), y + root.winfo_height())).save(
                str(Path(test_result).with_suffix('.png')))
            Path(test_result).write_text(json.dumps({'ok': True, 'checks': [
                'packaged uninstaller GUI visible', 'report deletion opt-in',
                'optional mailbox and AI configuration preservation visible',
                'light Windows style and accent action rendered', 'test performs no deletion'
            ]}), encoding='utf-8')
            root.destroy()
        root.after(200, verify_ui)
    elif worker_folder:
        set_busy()
        threading.Thread(target=cleanup, daemon=True).start()
    elif fixture_result:
        root.after(200, start)
    try:
        root.mainloop()
    finally:
        if instance:
            instance.close()
        if worker_folder:
            schedule_helper_removal()
    return 0


def cli():
    parser = argparse.ArgumentParser()
    parser.add_argument('--uninstall-ui-test')
    parser.add_argument('--uninstall-worker')
    parser.add_argument('--parent-pid', type=int, default=0)
    parser.add_argument('--delete-reports', action='store_true')
    parser.add_argument('--keep-configuration', action='store_true')
    parser.add_argument('--e2e-test')
    parser.add_argument('--fixture-result')
    args = parser.parse_args()
    return main(test_result=args.uninstall_ui_test, worker_folder=args.uninstall_worker,
                parent_pid=args.parent_pid, delete_saved_reports=args.delete_reports,
                fixture_result=args.fixture_result or args.e2e_test, keep_configuration=args.keep_configuration)


def native_cli():
    """Native WinUI owns the window; this redirected worker only stages or cleans."""
    from . import platform_windows as platform
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser()
    parser.add_argument('--uninstall-native', choices=['info', 'prepare', 'cleanup', 'remove-helper'], required=True)
    parser.add_argument('--target')
    parser.add_argument('--executable')
    parser.add_argument('--parent-pid', type=int, default=0)
    parser.add_argument('--fixture-result')
    parser.add_argument('--delete-reports', action='store_true')
    parser.add_argument('--keep-configuration', action='store_true')
    args = parser.parse_args()
    def emit(kind, value):
        print(json.dumps({kind: value}, ensure_ascii=False), flush=True)
    instance = None
    try:
        if args.uninstall_native == 'remove-helper':
            schedule_helper_removal()
            return 0
        folder = installation(args.target)
        data = fixture_data(folder) if args.fixture_result else Path(os.environ['LOCALAPPDATA']) / 'BensonMail'
        if args.uninstall_native == 'info':
            try:
                config = json.loads((data / 'config.json').read_text(encoding='utf-8'))
            except (ValueError, OSError):
                config = {}
            emit('result', {'data': str(data), 'reports': config.get('output_dir', ''), 'target': str(folder)})
            return 0
        if args.uninstall_native == 'cleanup':
            emit('progress', '正在准备…')
            wait_for_parent(args.parent_pid)
        # Preparation is non-destructive and precedes the visible confirmation
        # window, which asks permission to close a running application later.
        if args.uninstall_native == 'cleanup':
            instance = platform.SingleInstance()
            if instance.already_running:
                raise RuntimeError('邮件小秘书仍在运行，请先从右下角托盘退出，再重新卸载。')
        if args.uninstall_native == 'prepare':
            name = Path(args.executable or '').name
            if not re.fullmatch(r'Uninstall-BensonMail-\d{12}\.exe', name):
                raise ValueError('卸载程序文件名不符合版本命名。')
            emit('progress', '正在准备独立卸载组件，请稍候…')
            temporary = Path(tempfile.mkdtemp(prefix='BensonMail-uninstall-'))
            try:
                shutil.copytree(folder, temporary, dirs_exist_ok=True)
                (temporary / '.benson-uninstall-helper').write_text('temporary runtime', encoding='utf-8')
                emit('result', {'helper': str(temporary / name)})
            except Exception:
                shutil.rmtree(temporary, ignore_errors=True)
                raise
        else:
            cleanup_installation(folder, data, args.delete_reports, lambda text: emit('progress', text),
                                 registry_name='BensonMail-UninstallFixture' if args.fixture_result else 'BensonMail',
                                 shortcut_places=[folder.parent / 'shortcuts'] if args.fixture_result else None,
                                 keep_configuration=args.keep_configuration)
            emit('result', {'ok': True})
        return 0
    except Exception as error:
        emit('error', f'{type(error).__name__}：{error}')
        return 1
    finally:
        if instance:
            instance.close()

"""Remove this portable installation and current-user application data."""
import base64
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


def report_files(directory):
    """Only recognized report/metadata pairs, never an entire custom folder."""
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
            text = metadata.with_name(metadata.name[:-10] + '.txt')
            if text.is_symlink():
                continue
            if text.is_file():
                found.append(text)
            found.append(metadata)
    return found


def remove_reports(directory):
    files = report_files(directory)
    for path in files:
        path.unlink(missing_ok=True)
    for folder in {p.parent for p in files}:
        try:
            folder.rmdir()
        except OSError:
            pass  # The date folder may contain unrelated user files.
    try:
        Path(directory).rmdir()
    except OSError:
        pass
    return len(files)


def delete_command(folder, pid, notify=True):
    folder = Path(folder).resolve()
    if not re.fullmatch(r'BensonMail(?:-\d{12})?', folder.name) or not (folder / '_internal').is_dir():
        raise ValueError('程序目录名称或结构不符，已停止自动删除。请手动删除当前解压文件夹。')
    literal = str(folder).replace("'", "''")
    success = (
        "Add-Type -AssemblyName System.Windows.Forms;"
        "[System.Windows.Forms.MessageBox]::Show('邮件小秘书已卸载。','卸载完成')|Out-Null"
    ) if notify else ""
    failure = (
        "Add-Type -AssemblyName System.Windows.Forms;"
        "[System.Windows.Forms.MessageBox]::Show(('程序目录未能完全删除，请手动清理：'+$_.Exception.Message),'卸载未完成')|Out-Null;"
    ) if notify else ""
    return (
        "$ErrorActionPreference='Stop';"
        f"$deadline=(Get-Date).AddSeconds(120);while(Get-Process -Id {int(pid)} -ErrorAction SilentlyContinue)"
        "{if((Get-Date) -gt $deadline){exit 1};Start-Sleep -Milliseconds 300};"
        "Start-Sleep -Milliseconds 500;"
        f"try{{Remove-Item -LiteralPath '{literal}' -Recurse -Force;"
        + success + "}catch{" + failure + "exit 1}"
    )


def remove_shortcuts(folder):
    """Delete shortcuts only when their resolved targets are in this installation."""
    literal = str(Path(folder).resolve()).replace("'", "''")
    script = (
        "$ErrorActionPreference='Stop';$shell=New-Object -ComObject WScript.Shell;"
        f"$install='{literal}';"
        "$places=@([Environment]::GetFolderPath('Desktop'),"
        "[Environment]::GetFolderPath('StartMenu'),"
        "[Environment]::GetFolderPath('Startup'));"
        "foreach($place in $places){if(Test-Path -LiteralPath $place){"
        "Get-ChildItem -LiteralPath $place -Filter *.lnk -Recurse | ForEach-Object {"
        "$target=$shell.CreateShortcut($_.FullName).TargetPath;"
        "if($target -and [IO.Path]::GetDirectoryName($target) -eq $install)"
        "{Remove-Item -LiteralPath $_.FullName -Force}}}}"
    )
    encoded = base64.b64encode(script.encode('utf-16le')).decode('ascii')
    subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded],
                   check=True, capture_output=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)


def main(test_result=None):
    import tkinter as tk
    from tkinter import ttk, messagebox
    from . import platform_windows as platform
    root = tk.Tk()
    root.title('卸载邮件小秘书')
    root.geometry('620x410')
    root.resizable(False, False)
    folder = Path(sys.executable).resolve().parent
    data = Path(os.environ['LOCALAPPDATA']) / 'BensonMail'
    try:
        config = json.loads((data / 'config.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        config = {}
    reports = config.get('output_dir', '')
    frame = ttk.Frame(root, padding=22)
    frame.pack(fill='both', expand=True)
    ttk.Label(frame, text='卸载邮件小秘书', font=('Microsoft YaHei UI', 18)).pack(anchor='w')
    ttk.Label(frame, text='请先从右下角托盘退出邮件小秘书。\n将删除本次程序目录、设置、加密密钥、缓存、自启动项及指向此目录的快捷方式。',
              wraplength=570).pack(anchor='w', pady=12)
    ttk.Label(frame, text=f'程序目录：{folder}\n数据目录：{data}', wraplength=570).pack(anchor='w', pady=8)
    delete_reports = tk.BooleanVar(value=False)
    ttk.Checkbutton(frame, text='同时删除当前保存目录中的邮件报告及邮件索引', variable=delete_reports).pack(anchor='w')
    ttk.Label(frame, text=f'报告目录：{reports or "未配置"}\n只删除可识别的报告和索引；目录中的其他文件会保留。',
              wraplength=570).pack(anchor='w', pady=8)

    def uninstall():
        instance = platform.SingleInstance()
        try:
            if instance.already_running:
                messagebox.showwarning('请先退出', '请从邮件小秘书的托盘菜单选择“退出”，然后再点击卸载。', parent=root)
                return
            command = delete_command(folder, os.getpid())
            if not messagebox.askyesno('确认卸载', '确定卸载并删除以上数据吗？此操作无法撤销。', parent=root, default='no'):
                return
            if delete_reports.get() and reports:
                remove_reports(reports)
            platform.set_autostart(False)
            remove_shortcuts(folder)
            if data.exists():
                if data.is_symlink():
                    data.unlink()
                else:
                    shutil.rmtree(data)
            encoded = base64.b64encode(command.encode('utf-16le')).decode('ascii')
            subprocess.Popen(['powershell.exe', '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded],
                             cwd=os.environ['TEMP'], creationflags=subprocess.CREATE_NO_WINDOW,
                             close_fds=True)
            root.destroy()
        except Exception as error:
            messagebox.showerror('卸载未完成', f'部分内容可能已清理，可排除原因后重试。\n{error}', parent=root)
        finally:
            instance.close()

    ttk.Button(frame, text='卸载并清理', command=uninstall).pack(side='right', pady=12)
    ttk.Button(frame, text='取消', command=root.destroy).pack(side='right', padx=10, pady=12)
    if test_result:
        def verify_ui():
            root.update_idletasks()
            assert root.winfo_viewable()
            assert not delete_reports.get()
            Path(test_result).write_text(json.dumps({'ok': True, 'checks': [
                'packaged uninstaller GUI visible', 'report deletion opt-in',
                'test does not run deletion or load any secret'
            ]}), encoding='utf-8')
            root.destroy()
        root.after(200, verify_ui)
    root.mainloop()
    return 0

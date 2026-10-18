"""Delete only the verified downloaded installer after Setup has exited."""
import argparse
import ctypes
from ctypes import wintypes
import hashlib
import os
from pathlib import Path
import re
import sys
import time


def verified_installer(path, digest):
    path = Path(os.path.abspath(path))
    if path.suffix.lower() != '.exe':
        raise ValueError('Not a Mail Secretary installer')
    if not re.fullmatch(r'[a-fA-F0-9]{64}', digest):
        raise ValueError('Invalid installer fingerprint')
    if path.is_symlink() or path.resolve().is_relative_to(Path(sys.executable).resolve().parent):
        raise ValueError('The installer must not be an installed application file')
    if not path.is_file():
        raise ValueError('Installer is missing')
    with path.open('rb') as stream:
        if stream.read(2) != b'MZ':
            raise ValueError('Not a Windows executable')
        stream.seek(0)
        if hashlib.file_digest(stream, 'sha256').hexdigest() != digest.lower():
            raise ValueError('Installer contents changed')
    return path


def remove_after_exit(path, digest, pid):
    if sys.platform != 'win32' or pid <= 0:
        return False
    try:
        source = verified_installer(path, digest)
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x00100000, False, pid)
        if handle:
            try:
                if kernel.WaitForSingleObject(handle, 120000) != 0:
                    return False
            finally:
                kernel.CloseHandle(handle)
        elif ctypes.get_last_error() != 87:  # The process has already exited.
            return False
        for _ in range(60):
            try:
                verified_installer(source, digest).unlink()
                return True
            except PermissionError:
                time.sleep(.5)
        return False
    except (OSError, ValueError):
        return False


def cli():
    parser = argparse.ArgumentParser()
    parser.add_argument('--delete-installer', required=True)
    parser.add_argument('--installer-sha256', required=True)
    parser.add_argument('--setup-pid', required=True, type=int)
    args = parser.parse_args()
    # Cleanup failure is deliberately independent of installation success.
    remove_after_exit(args.delete_installer, args.installer_sha256, args.setup_pid)
    return 0

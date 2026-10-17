# Configure only the disposable CI desktop, never the user's Windows settings.
$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force evidence | Out-Null
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class TestDesktopTypography {
    [DllImport("user32.dll", SetLastError=true)]
    public static extern bool SystemParametersInfo(uint action, uint parameter, IntPtr value, uint flags);
    public static int Read(uint action) {
        var pointer = Marshal.AllocHGlobal(4);
        try {
            if (!SystemParametersInfo(action, 0, pointer, 0))
                throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
            return Marshal.ReadInt32(pointer);
        } finally { Marshal.FreeHGlobal(pointer); }
    }
}
'@
$before = @{
    enabled = [TestDesktopTypography]::Read(0x004A)
    type = [TestDesktopTypography]::Read(0x200A)
}
if (![TestDesktopTypography]::SystemParametersInfo(0x004B, 1, [IntPtr]::Zero, 3)) { throw 'Could not enable font smoothing' }
if (![TestDesktopTypography]::SystemParametersInfo(0x200B, 0, [IntPtr]2, 3)) { throw 'Could not enable ClearType' }
$after = @{
    enabled = [TestDesktopTypography]::Read(0x004A)
    type = [TestDesktopTypography]::Read(0x200A)
}
if ($after.enabled -ne 1 -or $after.type -ne 2) { throw 'Font smoothing settings were not applied' }
@{
    scope = 'Disposable Windows CI desktop only'
    before = $before
    after = $after
    fonts = @(Get-ChildItem "$env:WINDIR/Fonts" | Where-Object { $_.Name -match '^(segoe|segui|msyh|msjh|sim)' } | Select-Object -ExpandProperty Name)
} | ConvertTo-Json -Depth 4 | Set-Content -Encoding utf8 evidence/desktop-typography.json

param(
    [ValidateSet('Detect','Install','Library')][string]$Mode = 'Detect',
    [string]$ResultFile,
    [string]$Components = '',
    [string]$MinimumDotnet = '8.0.32',
    [string]$MinimumWinUI = '8000.994.2142.0'
)
$ErrorActionPreference = 'Stop'

# Pinned Microsoft releases. No discovery endpoint or download is contacted by Detect.
$script:Prerequisites = @{
    dotnet = @{
        Label = '.NET 8 runtime (x64)'
        Url = 'https://builds.dotnet.microsoft.com/dotnet/Runtime/8.0.32/dotnet-runtime-8.0.32-win-x64.exe'
        Algorithm = 'SHA512'
        Hash = '47e999865bec424da9d75b90f479204305be5e7857f9ec27e1fb33f399819007e0791505096ace36be3f26ee4d66e260434250509597dfafe7caaeee87acf0e1'
        Arguments = '/install /quiet /norestart'
        Elevate = $true
    }
    winui = @{
        Label = 'WinUI 3 / Windows App Runtime 1.8 (x64)'
        Url = 'https://download.microsoft.com/download/8eb5473d-5663-4337-a1ca-aa5030b9b194/WindowsAppRuntimeInstall-x64.exe'
        Algorithm = 'SHA256'
        Hash = '7c092e85fc1e3e7cb2bd7d549aaab03caf924131f15d9b20b1855457a98205aa'
        Arguments = '--quiet'
        Elevate = $false
    }
}

function Get-PrerequisiteState {
    $dotnet = $false
    # .NET registers all architectures in the 32-bit registry view. This
    # helper requires 64-bit PowerShell; the final x64 key is runtime architecture.
    $location = 'HKLM:\SOFTWARE\WOW6432Node\dotnet\Setup\InstalledVersions\x64'
    $root = (Get-ItemProperty -LiteralPath $location -Name InstallLocation -ErrorAction SilentlyContinue).InstallLocation
    if ($root) {
        $shared = Join-Path $root 'shared\Microsoft.NETCore.App'
        foreach ($folder in @(Get-ChildItem -LiteralPath $shared -Directory -ErrorAction SilentlyContinue)) {
            if ($folder.Name -match '^8\.0\.\d+$' -and [version]$folder.Name -ge [version]$MinimumDotnet -and
                (Test-Path -LiteralPath (Join-Path $folder.FullName 'coreclr.dll')) -and
                (Test-Path -LiteralPath (Join-Path $folder.FullName 'System.Private.CoreLib.dll'))) { $dotnet = $true; break }
        }
    }
    # Microsoft requires Framework + Main + Singleton + DDLM, not just the framework.
    # Main/Singleton match native OS architecture, including x64 emulation on ARM64.
    $nativeArchitecture = $env:PROCESSOR_ARCHITEW6432
    if (!$nativeArchitecture) { $nativeArchitecture = $env:PROCESSOR_ARCHITECTURE }
    $nativeArchitecture = if ($nativeArchitecture -eq 'ARM64') { 'ARM64' } else { 'X64' }
    $architectures = @('X86','X64')
    if ($nativeArchitecture -eq 'ARM64') { $architectures += 'ARM64' }
    $packages = @(Get-AppxPackage -ErrorAction SilentlyContinue | Where-Object {
        $_.Status -eq 'Ok' -and [version]$_.Version -ge [version]$MinimumWinUI
    })
    $winui = $true
    foreach ($architecture in $architectures) {
        $framework = @($packages | Where-Object {
            $_.Architecture -eq $architecture -and $_.IsFramework -and
            $_.PackageFamilyName -eq 'Microsoft.WindowsAppRuntime.1.8_8wekyb3d8bbwe'
        })
        $ddlm = @($packages | Where-Object {
            $_.Architecture -eq $architecture -and !$_.IsFramework -and
            $_.PackageFamilyName -like 'Microsoft.WinAppRuntime.DDLM.8000.*_8wekyb3d8bbwe' -and
            [string]$_.Version -in @($framework | ForEach-Object { [string]$_.Version })
        })
        if (!$framework.Count -or !$ddlm.Count) { $winui = $false }
    }
    foreach ($family in @('MicrosoftCorporationII.WinAppRuntime.Main.1.8_8wekyb3d8bbwe',
                          'MicrosoftCorporationII.WinAppRuntime.Singleton_8wekyb3d8bbwe')) {
        if (!@($packages | Where-Object {
            $_.Architecture -eq $nativeArchitecture -and !$_.IsFramework -and $_.PackageFamilyName -eq $family
        }).Count) { $winui = $false }
    }
    return @{ dotnet = $dotnet; winui = $winui }
}

function Assert-MicrosoftPayload([string]$Path, [hashtable]$Definition) {
    if ((Get-FileHash -LiteralPath $Path -Algorithm $Definition.Algorithm).Hash -ine $Definition.Hash) {
        throw 'Microsoft runtime download checksum did not match. The file was discarded.'
    }
    $signature = Get-AuthenticodeSignature -LiteralPath $Path
    if ($signature.Status -ne 'Valid' -or !$signature.SignerCertificate -or
        $signature.SignerCertificate.Subject -notmatch '(?:^|,\s*)O=Microsoft Corporation(?:,|$)') {
        throw 'Microsoft runtime signature could not be verified. No downloaded program was run.'
    }
}

function Get-MicrosoftPayload([hashtable]$Definition, [string]$Path) {
    Add-Type -AssemblyName System.Net.Http
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $handler = New-Object Net.Http.HttpClientHandler
    $handler.AllowAutoRedirect = $false
    $client = New-Object Net.Http.HttpClient($handler)
    $client.Timeout = [TimeSpan]::FromSeconds(180)
    $partial = $Path + '.part'
    try {
        $uri = [uri]$Definition.Url
        for ($redirect = 0; $redirect -lt 6; $redirect++) {
            if ($uri.Scheme -ne 'https' -or $uri.UserInfo -or
                $uri.Host -notin @('builds.dotnet.microsoft.com','download.microsoft.com')) {
                throw 'Runtime download redirect was not an approved Microsoft HTTPS endpoint.'
            }
            $response = $client.GetAsync($uri, [Net.Http.HttpCompletionOption]::ResponseHeadersRead).GetAwaiter().GetResult()
            if ([int]$response.StatusCode -ge 300 -and [int]$response.StatusCode -lt 400) {
                if (!$response.Headers.Location) { $response.Dispose(); throw 'Runtime download redirect had no destination.' }
                $uri = New-Object uri($uri, $response.Headers.Location)
                $response.Dispose()
                continue
            }
            try {
                $response.EnsureSuccessStatusCode() | Out-Null
                if ($response.Content.Headers.ContentLength -gt 209715200) { throw 'Runtime download exceeded its allowed size.' }
                $source = $response.Content.ReadAsStreamAsync().GetAwaiter().GetResult()
                $output = [IO.File]::Open($partial, [IO.FileMode]::CreateNew)
                try {
                    $buffer = New-Object byte[] 131072
                    $counted = 0L
                    $timeout = New-Object Threading.CancellationTokenSource
                    try {
                        while ($true) {
                            $timeout.CancelAfter(45000)
                            $count = $source.ReadAsync($buffer, 0, $buffer.Length, $timeout.Token).GetAwaiter().GetResult()
                            if (!$count) { break }
                            $counted += $count
                            if ($counted -gt 209715200) { throw 'Runtime download exceeded its allowed size.' }
                            $output.Write($buffer, 0, $count)
                        }
                    } finally { $timeout.Dispose() }
                } finally { $output.Dispose(); $source.Dispose() }
                if (!$counted) { throw 'Microsoft returned an empty runtime download.' }
            } finally { $response.Dispose() }
            Assert-MicrosoftPayload $partial $Definition
            Move-Item -LiteralPath $partial -Destination $Path
            return
        }
        throw 'Too many Microsoft runtime download redirects.'
    } finally {
        $client.Dispose(); $handler.Dispose()
        Remove-Item -LiteralPath $partial -Force -ErrorAction SilentlyContinue
    }
}

# Resolve junctions (including redirected profile/temp folders) before passing paths
# to Microsoft's deployment service. A path through an untrusted mount point may
# be rejected with ERROR_UNTRUSTED_MOUNT_POINT, even when the file itself is signed.
function Get-PhysicalInstallerPath([string]$Path) {
    if (-not ('BensonMail.InstallerPath' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Text;
using Microsoft.Win32.SafeHandles;
namespace BensonMail {
    public static class InstallerPath {
        [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
        static extern SafeFileHandle CreateFile(string path, uint access, uint share,
            IntPtr security, uint creation, uint flags, IntPtr template);
        [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
        static extern uint GetFinalPathNameByHandle(SafeFileHandle handle,
            StringBuilder path, uint length, uint flags);
        public static string Resolve(string path) {
            using (var handle = CreateFile(path, 0, 7, IntPtr.Zero, 3, 0x02000000, IntPtr.Zero)) {
                if (handle.IsInvalid) throw new Win32Exception(Marshal.GetLastWin32Error());
                var result = new StringBuilder(32768);
                uint length = GetFinalPathNameByHandle(handle, result, (uint)result.Capacity, 0);
                if (length == 0) throw new Win32Exception(Marshal.GetLastWin32Error());
                if (length >= result.Capacity) throw new InvalidOperationException("Resolved runtime path is too long.");
                string value = result.ToString();
                if (value.StartsWith(@"\\?\UNC\")) return @"\\" + value.Substring(8);
                return value.StartsWith(@"\\?\") ? value.Substring(4) : value;
            }
        }
    }
}
'@
    }
    return [BensonMail.InstallerPath]::Resolve([IO.Path]::GetFullPath($Path))
}

function Get-RuntimeExitDetails([int]$Code) {
    $unsigned = [uint32]([int64]$Code -band 4294967295L)
    $hex = '0x{0:X8}' -f $unsigned
    $nativeCode = if (($unsigned -band 4294901760L) -eq 2147942400L) { [int]($unsigned -band 65535) } else { $Code }
    $message = (New-Object ComponentModel.Win32Exception($nativeCode)).Message
    $reason = if ($hex -eq '0x800701C0') { 'untrusted_mount_point' } else { 'runtime_exit' }
    return @{ Reason=$reason; ExitCode=$Code; HResult=$hex; NativeMessage=$message }
}

function Write-InstallerLog([string]$Text) {
    if ($script:RuntimeLogPath) {
        [IO.File]::AppendAllText($script:RuntimeLogPath, $Text + [Environment]::NewLine, [Text.Encoding]::UTF8)
    }
}

function Write-AppxDeploymentDiagnostics {
    try {
        $events = @(Get-WinEvent -FilterHashtable @{
            LogName='Microsoft-Windows-AppXDeploymentServer/Operational'
            StartTime=(Get-Date).AddMinutes(-5)
            Level=2
        } -MaxEvents 20 -ErrorAction Stop)
        Write-InstallerLog 'Recent local AppX deployment errors (last five minutes, at most 20; may include another installation):'
        foreach ($event in $events) {
            Write-InstallerLog ('[' + $event.TimeCreated.ToString('o') + '] Event ' + $event.Id + ': ' + $event.Message)
        }
    } catch {
        # Missing/disabled/restricted event channels must never replace the real failure.
        Write-InstallerLog ('AppX event diagnostics unavailable: ' + $_.Exception.Message)
    }
}

function Invoke-MicrosoftInstaller([hashtable]$Definition, [string]$Path) {
    # Recheck immediately before execution. Existing shared runtimes are never uninstalled.
    Assert-MicrosoftPayload $Path $Definition
    $physicalPayload = Get-PhysicalInstallerPath $Path
    $logRoot = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'BensonMail\InstallerLogs'
    [IO.Directory]::CreateDirectory($logRoot) | Out-Null
    $runName = (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N')
    $script:RuntimeLogPath = Join-Path $logRoot ($runName + '.log')
    $workspace = Join-Path $logRoot ($runName + '-temp')
    $process = $null
    $started = $false
    $finished = $false
    Write-InstallerLog ('Component: ' + $Definition.Label)
    Write-InstallerLog ('Windows: ' + [Environment]::OSVersion.VersionString)
    Write-InstallerLog ('Source payload: ' + $physicalPayload)
    try {
        [IO.Directory]::CreateDirectory($workspace) | Out-Null
        $physicalWorkspace = Get-PhysicalInstallerPath $workspace
        Write-InstallerLog ('Runtime workspace: ' + $physicalWorkspace)
        # Stage both EXE and its extraction TEMP at resolved paths. Only this child
        # receives TEMP/TMP; the user's global environment remains unchanged.
        $stagedPayload = Join-Path $physicalWorkspace 'MicrosoftRuntimeSetup.exe'
        Copy-Item -LiteralPath $physicalPayload -Destination $stagedPayload
        Assert-MicrosoftPayload $stagedPayload $Definition
        if ($Definition.Elevate) {
            # ShellExecute is required for UAC. .NET writes its own installer log.
            $arguments = $Definition.Arguments + ' /log "' + $script:RuntimeLogPath + '.dotnet.log"'
            $process = Start-Process -FilePath $stagedPayload -ArgumentList $arguments -Verb RunAs -PassThru
        } else {
            $start = New-Object Diagnostics.ProcessStartInfo
            $start.FileName = $stagedPayload
            $start.Arguments = $Definition.Arguments
            $start.WorkingDirectory = $physicalWorkspace
            $start.UseShellExecute = $false
            $start.CreateNoWindow = $true
            $start.RedirectStandardOutput = $true
            $start.RedirectStandardError = $true
            $start.EnvironmentVariables['TEMP'] = $physicalWorkspace
            $start.EnvironmentVariables['TMP'] = $physicalWorkspace
            $process = New-Object Diagnostics.Process
            $process.StartInfo = $start
            if (!$process.Start()) { throw 'Microsoft runtime installer could not be started.' }
            # Drain both streams concurrently; waiting first can deadlock a full pipe.
            $stdout = $process.StandardOutput.ReadToEndAsync()
            $stderr = $process.StandardError.ReadToEndAsync()
        }
        $started = $true
        if (!$process.WaitForExit(900000)) {
            Write-InstallerLog 'Installer is still running after 15 minutes. Its workspace was retained.'
            throw 'Microsoft runtime installation is still running. Wait for it to finish, then retry Setup.'
        }
        $finished = $true
        $process.Refresh()
        if (!$Definition.Elevate) {
            Write-InstallerLog ('Standard output:' + [Environment]::NewLine + $stdout.GetAwaiter().GetResult())
            Write-InstallerLog ('Standard error:' + [Environment]::NewLine + $stderr.GetAwaiter().GetResult())
        }
        Write-InstallerLog ('Exit code: ' + $process.ExitCode + ' (' + (Get-RuntimeExitDetails $process.ExitCode).HResult + ')')
        if ($process.ExitCode -ne 0) { Write-AppxDeploymentDiagnostics }
        return $process.ExitCode
    } catch {
        Write-InstallerLog ('Failure: ' + $_.Exception.Message)
        Write-AppxDeploymentDiagnostics
        throw
    } finally {
        if ($process) { $process.Dispose() }
        # Never remove the executable/workspace from a runtime still installing.
        if ($finished -or !$started) { Remove-Item -LiteralPath $workspace -Recurse -Force -ErrorAction SilentlyContinue }
    }
}

function Invoke-PrerequisiteInstall([string[]]$Requested, [string]$WorkingDirectory) {
    $script:RuntimeLogPath = $null
    $script:RuntimeFailure = @{}
    if (!$Requested.Count) { throw 'No explicitly approved runtime components were supplied.' }
    foreach ($component in $Requested) {
        if ($component -notin @('dotnet','winui')) { throw 'Unknown runtime component.' }
    }
    $state = Get-PrerequisiteState
    foreach ($component in $Requested) {
        if ($state[$component]) { continue } # Another installer may have provided it since consent.
        $script:RuntimeLogPath = $null
        $script:RuntimeFailure = @{}
        $definition = $script:Prerequisites[$component]
        $file = Join-Path $WorkingDirectory ($component + '-' + [guid]::NewGuid().ToString('N') + '.exe')
        try {
            Get-MicrosoftPayload $definition $file
            $code = Invoke-MicrosoftInstaller $definition $file
            if ($code -in @(3010,1641)) { return 'reboot' }
            if ($code -ne 0) {
                $script:RuntimeFailure = Get-RuntimeExitDetails $code
                $detail = $definition.Label + ' installer returned exit code ' + $code + ' (' + $script:RuntimeFailure.HResult + '). ' + $script:RuntimeFailure.NativeMessage
                if ($script:RuntimeFailure.Reason -eq 'untrusted_mount_point') {
                    $detail += ' Windows rejected a path through an untrusted mount point. Check redirected profile/temp folders and Windows AppX deployment events; the failing path is not yet known.'
                }
                throw ($detail + ' No application files were changed.')
            }
            $state = Get-PrerequisiteState
            if (!$state[$component]) { throw ($definition.Label + ' is still unavailable for this Windows user after installation. Reopen Setup after checking Windows updates and runtime installation.') }
        } finally { Remove-Item -LiteralPath $file -Force -ErrorAction SilentlyContinue }
    }
    return 'ready'
}

function Write-PrerequisiteResult([string]$Path, [hashtable]$Values) {
    $lines = @('[Prerequisites]') + @($Values.Keys | Sort-Object | ForEach-Object {
        $_ + '=' + ([string]$Values[$_]).Replace("`r",' ').Replace("`n",' | ')
    })
    [IO.File]::WriteAllLines($Path, $lines, [Text.Encoding]::Unicode)
}

if ($Mode -eq 'Library') { return }
try {
    if (![Environment]::Is64BitProcess) { throw 'This installer requires 64-bit Windows PowerShell.' }
    if (!$ResultFile) { throw 'Runtime result file was not supplied.' }
    if ($Mode -eq 'Detect') {
        $state = Get-PrerequisiteState
        Write-PrerequisiteResult $ResultFile @{ Status='detected'; DotNet=[int]$state.dotnet; WinUI=[int]$state.winui }
    } else {
        $status = Invoke-PrerequisiteInstall @($Components.Split(',') | Where-Object { $_ }) (Split-Path -Parent $ResultFile)
        Write-PrerequisiteResult $ResultFile @{ Status=$status }
    }
    exit 0
} catch {
    if ($ResultFile) {
        $failure = @{ Status='failed'; Error=$_.Exception.Message; Reason='installation_failed' }
        if ($script:RuntimeFailure) { foreach ($key in $script:RuntimeFailure.Keys) { $failure[$key] = $script:RuntimeFailure[$key] } }
        if ($script:RuntimeLogPath) { $failure.LogPath = $script:RuntimeLogPath }
        Write-PrerequisiteResult $ResultFile $failure
    }
    exit 1
}

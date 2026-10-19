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

function Invoke-MicrosoftInstaller([hashtable]$Definition, [string]$Path) {
    # Recheck immediately before execution. Existing shared runtimes are never uninstalled.
    Assert-MicrosoftPayload $Path $Definition
    $parameters = @{ FilePath = $Path; ArgumentList = $Definition.Arguments; PassThru = $true }
    if ($Definition.Elevate) { $parameters.Verb = 'RunAs' }
    $process = Start-Process @parameters
    try {
        if (!$process.WaitForExit(900000)) { throw 'Microsoft runtime installation is still running. Wait for it to finish, then retry Setup.' }
        $process.Refresh()
        return $process.ExitCode
    } finally { $process.Dispose() }
}

function Invoke-PrerequisiteInstall([string[]]$Requested, [string]$WorkingDirectory) {
    if (!$Requested.Count) { throw 'No explicitly approved runtime components were supplied.' }
    foreach ($component in $Requested) {
        if ($component -notin @('dotnet','winui')) { throw 'Unknown runtime component.' }
    }
    $state = Get-PrerequisiteState
    foreach ($component in $Requested) {
        if ($state[$component]) { continue } # Another installer may have provided it since consent.
        $definition = $script:Prerequisites[$component]
        $file = Join-Path $WorkingDirectory ($component + '-' + [guid]::NewGuid().ToString('N') + '.exe')
        try {
            Get-MicrosoftPayload $definition $file
            $code = Invoke-MicrosoftInstaller $definition $file
            if ($code -in @(3010,1641)) { return 'reboot' }
            if ($code -ne 0) { throw ($definition.Label + ' installer returned exit code ' + $code + '. No application files were changed.') }
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
    if ($ResultFile) { Write-PrerequisiteResult $ResultFile @{ Status='failed'; Error=$_.Exception.Message } }
    exit 1
}

param(
    [string]$Evidence = 'evidence',
    [string]$Setup,
    [switch]$ProvisionSharedRuntimes
)
$ErrorActionPreference = 'Stop'
$helper = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../installer/prerequisites.ps1'))
$Evidence = [IO.Path]::GetFullPath($Evidence)
New-Item -ItemType Directory -Path $Evidence -Force | Out-Null
$fixture = Join-Path ([IO.Path]::GetTempPath()) ('BensonMail-prerequisites-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $fixture | Out-Null
$checks = New-Object 'Collections.Generic.List[string]'
$originalArchitecture = $env:PROCESSOR_ARCHITECTURE
$originalArchitecture6432 = $env:PROCESSOR_ARCHITEW6432
function Check([bool]$Condition, [string]$Name) {
    if (!$Condition) { throw "Prerequisite check failed: $Name" }
    $checks.Add($Name)
}
function Expect-Failure([scriptblock]$Action, [string]$Pattern, [string]$Name) {
    $failure = $null
    try { & $Action | Out-Null } catch { $failure = $_.Exception.Message }
    Check ([bool]$failure -and $failure -match $Pattern) $Name
}

try {
    . $helper -Mode Library
    $actualBefore = Get-PrerequisiteState
    # This fixture is deliberately outside all user data, installed app and registry paths.
    $sentinels = @('BensonMail.exe', 'config.json', 'reports\synthetic.txt')
    foreach ($relative in $sentinels) {
        $path = Join-Path $fixture $relative
        New-Item -ItemType Directory -Path (Split-Path $path) -Force | Out-Null
        [IO.File]::WriteAllText($path, 'SYNTHETIC-UNCHANGED-' + $relative)
    }
    $before = @{}
    foreach ($relative in $sentinels) { $before[$relative] = (Get-FileHash (Join-Path $fixture $relative)).Hash }

    # Exercise the production detector with synthetic registry and AppX responses.
    $env:PROCESSOR_ARCHITECTURE = 'AMD64'
    $env:PROCESSOR_ARCHITEW6432 = ''
    $script:fakeDotnetRoot = Join-Path $fixture 'runtime'
    $script:registryPaths = New-Object 'Collections.Generic.List[string]'
    function Get-ItemProperty {
        param($LiteralPath,$Name,$ErrorAction)
        $script:registryPaths.Add($LiteralPath)
        return @{InstallLocation=$script:fakeDotnetRoot}
    }
    $script:fakePackages = @()
    function Get-AppxPackage { param($Name,$ErrorAction); return $script:fakePackages }
    $runtimeFolder = Join-Path $script:fakeDotnetRoot 'shared\Microsoft.NETCore.App\8.0.31'
    New-Item -ItemType Directory -Path $runtimeFolder -Force | Out-Null
    foreach ($name in @('coreclr.dll','System.Private.CoreLib.dll')) { [IO.File]::WriteAllText((Join-Path $runtimeFolder $name),'fixture') }
    $state = Get-PrerequisiteState
    Check (!$state.dotnet -and !$state.winui) 'old .NET and missing WinUI are rejected without a network call'
    Rename-Item -LiteralPath $runtimeFolder -NewName '8.0.32'
    Check (Get-PrerequisiteState).dotnet '.NET 8.0.32 x64 registry installation is accepted'
    Check (@($script:registryPaths | Where-Object { $_ -ne 'HKLM:\SOFTWARE\WOW6432Node\dotnet\Setup\InstalledVersions\x64' }).Count -eq 0) 'x64 runtime registration is read from the official 32-bit registry view'
    $runtimeFolder = Join-Path $script:fakeDotnetRoot 'shared\Microsoft.NETCore.App\8.0.32'
    foreach ($name in @('coreclr.dll','System.Private.CoreLib.dll')) {
        $runtimeFile = Join-Path $runtimeFolder $name
        Remove-Item -LiteralPath $runtimeFile
        Check (!(Get-PrerequisiteState).dotnet) "incomplete .NET missing $name is rejected"
        [IO.File]::WriteAllText($runtimeFile,'fixture')
    }
    $registeredRoot = $script:fakeDotnetRoot
    $script:fakeDotnetRoot = $null
    Check (!(Get-PrerequisiteState).dotnet) 'missing x64 registry registration is rejected even when runtime files exist'
    $script:fakeDotnetRoot = $registeredRoot
    $package = [pscustomobject]@{Architecture='X86';Status='Ok';IsFramework=$true;PackageFamilyName='Microsoft.WindowsAppRuntime.1.8_8wekyb3d8bbwe';Version='8000.994.2142.0'}
    $script:fakePackages = @($package)
    Check (!(Get-PrerequisiteState).winui) 'x86 WinUI does not satisfy x64 runtime'
    $package.Architecture = 'X64'; $package.Version = '8000.1.0.0'
    Check (!(Get-PrerequisiteState).winui) 'old WinUI is rejected'
    $package.Version = '8000.994.2142.0'; $package.PackageFamilyName = 'Untrusted_8wekyb3d8bbwe'
    Check (!(Get-PrerequisiteState).winui) 'different AppX family is rejected'
    $package.PackageFamilyName = 'Microsoft.WindowsAppRuntime.1.8_8wekyb3d8bbwe'
    Check (!(Get-PrerequisiteState).winui) 'framework alone cannot satisfy complete Windows App Runtime'
    $script:fakePackages = @()
    foreach ($architecture in @('X86','X64','ARM64')) {
        foreach ($family in @('Microsoft.WindowsAppRuntime.1.8_8wekyb3d8bbwe',
                             'Microsoft.WinAppRuntime.DDLM.8000.994.2142.0-x6_8wekyb3d8bbwe',
                             'MicrosoftCorporationII.WinAppRuntime.Main.1.8_8wekyb3d8bbwe',
                             'MicrosoftCorporationII.WinAppRuntime.Singleton_8wekyb3d8bbwe')) {
            $script:fakePackages += [pscustomobject]@{Architecture=$architecture;Status='Ok';IsFramework=($family -eq 'Microsoft.WindowsAppRuntime.1.8_8wekyb3d8bbwe');PackageFamilyName=$family;Version='8000.994.2142.0'}
        }
    }
    Check (Get-PrerequisiteState).winui 'complete Microsoft framework Main Singleton DDLM runtime is accepted'
    $healthyPackages = @($script:fakePackages)
    $script:fakePackages = @($healthyPackages | ForEach-Object {
        $copy = $_.PSObject.Copy()
        if ($copy.PackageFamilyName -like '*DDLM*') {
            $copy.PackageFamilyName = $copy.PackageFamilyName.Replace('8000.', '9000.')
            $copy.Version = '9000.994.2142.0'
        }
        $copy
    })
    Check (!(Get-PrerequisiteState).winui) 'a DDLM from another runtime version cannot satisfy the installed 1.8 framework'
    foreach ($familyPattern in @('*WindowsAppRuntime.1.8_*','*DDLM*','*Main.1.8_*','*Singleton*')) {
        $script:fakePackages = @($healthyPackages | Where-Object { $_.PackageFamilyName -notlike $familyPattern })
        Check (!(Get-PrerequisiteState).winui) "missing required WinUI package family $familyPattern forces repair"
    }
    foreach ($architecture in @('X86','X64')) {
        $script:fakePackages = @($healthyPackages | Where-Object { $_.Architecture -ne $architecture })
        Check (!(Get-PrerequisiteState).winui) "missing required $architecture runtime packages forces repair"
    }
    foreach ($mutation in @('old','publisher','health')) {
        $script:fakePackages = @($healthyPackages | ForEach-Object {
            $copy = $_.PSObject.Copy()
            if ($mutation -eq 'old') { $copy.Version = '8000.1.0.0' }
            if ($mutation -eq 'publisher') { $copy.PackageFamilyName = $copy.PackageFamilyName.Replace('8wekyb3d8bbwe','untrusted') }
            if ($mutation -eq 'health') { $copy.Status = 'Modified' }
            $copy
        })
        Check (!(Get-PrerequisiteState).winui) "complete but $mutation WinUI package set is rejected"
    }
    $env:PROCESSOR_ARCHITECTURE = 'ARM64'
    $script:fakePackages = @($healthyPackages | Where-Object { $_.Architecture -ne 'ARM64' })
    Check (!(Get-PrerequisiteState).winui) 'ARM64 Windows additionally requires native ARM64 runtime packages'
    $script:fakePackages = $healthyPackages
    Check (Get-PrerequisiteState).winui 'complete ARM64 plus emulated x64 and x86 runtime set is accepted'
    $env:PROCESSOR_ARCHITECTURE = $originalArchitecture
    $env:PROCESSOR_ARCHITEW6432 = $originalArchitecture6432
    Remove-Item Function:\Get-ItemProperty, Function:\Get-AppxPackage

    # Reproduce the reported signed HRESULT, not a generic MSI error.
    $reportedFailure = Get-RuntimeExitDetails -2147024448
    Check ($reportedFailure.HResult -eq '0x800701C0' -and $reportedFailure.Reason -eq 'untrusted_mount_point') 'reported WinUI signed exit code maps to untrusted mount point'
    Check ((Get-RuntimeExitDetails 1603).Reason -eq 'runtime_exit') 'unrelated runtime errors are not diagnosed as mount-point failures'

    # Exercise the real console process and concurrent output capture without
    # downloading or installing a runtime. Only publisher validation is mocked.
    function Get-AuthenticodeSignature { param($LiteralPath); return @{Status='Valid';SignerCertificate=@{Subject='CN=Microsoft, O=Microsoft Corporation, C=US'}} }
    $console = Join-Path $env:WINDIR 'System32\cmd.exe'
    $consoleDefinition = @{Label='Synthetic console fixture'; Algorithm='SHA256';Hash=(Get-FileHash $console).Hash;Elevate=$false;Arguments='/d /c "echo synthetic-output & echo synthetic-error 1>&2 & echo CHILD_TEMP=%TEMP% & exit /b 448"'}
    $junction = Join-Path $fixture 'runtime-junction'
    $physicalTarget = Join-Path $fixture 'runtime-physical'
    New-Item -ItemType Directory -Path $physicalTarget | Out-Null
    New-Item -ItemType Junction -Path $junction -Target $physicalTarget | Out-Null
    Check ((Get-PhysicalInstallerPath $junction).TrimEnd('\') -eq $physicalTarget.TrimEnd('\')) 'junction paths resolve to their physical directory before runtime execution'
    $originalTemp = $env:TEMP
    $consoleExit = Invoke-MicrosoftInstaller $consoleDefinition $console
    $consoleLog = Get-Content -LiteralPath $script:RuntimeLogPath -Raw
    Check ($consoleExit -eq 448 -and $consoleLog.Contains('synthetic-output') -and $consoleLog.Contains('synthetic-error')) 'hidden console runtime preserves exit code and both output streams'
    Check ($consoleLog -match 'Runtime workspace: ([^\r\n]+)' -and $consoleLog.Contains('CHILD_TEMP=' + $Matches[1].Trim())) 'child extraction TEMP uses the resolved runtime workspace'
    Check ($env:TEMP -eq $originalTemp) 'runtime TEMP override does not modify parent environment'
    Check (@(Get-ChildItem (Split-Path $script:RuntimeLogPath) -Filter '*-temp' | Where-Object Name -eq (([IO.Path]::GetFileNameWithoutExtension($script:RuntimeLogPath)) + '-temp')).Count -eq 0) 'finished console workspace is removed but diagnostic log remains'
    Remove-Item -LiteralPath $script:RuntimeLogPath -Force
    # Remove the junction itself, never recurse through its target.
    [IO.Directory]::Delete($junction)
    Remove-Item Function:\Get-AuthenticodeSignature

    # Exercise the real install orchestrator. Only OS/network boundaries are mocked.
    $script:fakeState = @{dotnet=$true;winui=$true}
    $script:downloads = New-Object 'Collections.Generic.List[string]'
    $script:executions = 0
    $script:downloadFailure = $false
    $script:installCode = 0
    $script:makeAvailable = $true
    function Get-PrerequisiteState { return $script:fakeState.Clone() }
    function Get-MicrosoftPayload {
        param($Definition,$Path)
        $script:downloads.Add($Definition.Label)
        if ($script:downloadFailure) { throw 'Synthetic download failure' }
        [IO.File]::WriteAllText($Path,'synthetic payload')
    }
    function Invoke-MicrosoftInstaller {
        param($Definition,$Path)
        $script:executions++
        if ($script:makeAvailable -and $script:installCode -eq 0) {
            if ($Definition.Label -like '.NET*') { $script:fakeState.dotnet=$true } else { $script:fakeState.winui=$true }
        }
        return $script:installCode
    }
    Check ((Invoke-PrerequisiteInstall @('dotnet','winui') $fixture) -eq 'ready' -and $script:downloads.Count -eq 0 -and $script:executions -eq 0) 'installed components cause zero download and zero installer execution'
    $script:fakeState.winui = $false
    Expect-Failure { Invoke-PrerequisiteInstall @() $fixture } 'explicitly approved' 'no approved components means zero network and no installation'
    Check ($script:downloads.Count -eq 0) 'declined consent boundary never downloads'
    Check ((Invoke-PrerequisiteInstall @('dotnet') $fixture) -eq 'ready' -and $script:downloads.Count -eq 0 -and !$script:fakeState.winui) 'unapproved missing WinUI is never downloaded or installed'
    Check ((Invoke-PrerequisiteInstall @('dotnet','winui') $fixture) -eq 'ready' -and $script:downloads.Count -eq 1 -and $script:downloads[0] -like 'WinUI*') 'only the missing WinUI component is fetched'
    $script:fakeState.dotnet = $false; $script:downloadFailure = $true
    $executionsBefore = $script:executions
    Expect-Failure { Invoke-PrerequisiteInstall @('dotnet') $fixture } 'Synthetic download failure' 'download failure stops installation'
    Check ($script:executions -eq $executionsBefore) 'failed download never executes a payload'
    $script:downloadFailure = $false; $script:installCode = 1603
    Expect-Failure { Invoke-PrerequisiteInstall @('dotnet') $fixture } 'exit code 1603' 'Microsoft installer failure is reported'
    $script:installCode = -2147024448
    Expect-Failure { Invoke-PrerequisiteInstall @('dotnet') $fixture } '0x800701C0' 'reported WinUI HRESULT is preserved in installation failure text'
    Check ($script:RuntimeFailure.Reason -eq 'untrusted_mount_point') 'reported failure exposes a stable reason for localized Setup guidance'
    $script:installCode = 0; $script:makeAvailable = $false
    Expect-Failure { Invoke-PrerequisiteInstall @('dotnet') $fixture } 'still unavailable' 'success exit code alone cannot bypass runtime detection'
    foreach ($rebootCode in @(3010,1641)) {
        $script:installCode = $rebootCode
        $script:fakeState = @{dotnet=$false;winui=$false}
        $downloadsBefore = $script:downloads.Count
        $executionsBefore = $script:executions
        Check ((Invoke-PrerequisiteInstall @('dotnet','winui') $fixture) -eq 'reboot') "reboot-required exit $rebootCode is preserved"
        Check ($script:downloads.Count -eq ($downloadsBefore + 1) -and $script:executions -eq ($executionsBefore + 1) -and !$script:fakeState.winui) "exit $rebootCode stops before the next component or application installation"
    }
    $script:installCode = 0; $script:makeAvailable = $true
    Check ((Invoke-PrerequisiteInstall @('dotnet','winui') $fixture) -eq 'ready' -and $script:fakeState.dotnet -and $script:fakeState.winui) 'both approved missing components succeed only after a fresh detection confirms availability'
    Check (@(Get-ChildItem $fixture -Filter '*.exe' | Where-Object Name -ne 'BensonMail.exe').Count -eq 0) 'downloaded payloads are cleaned up after success or failure'
    foreach ($relative in $sentinels) { Check ((Get-FileHash (Join-Path $fixture $relative)).Hash -eq $before[$relative]) "fixture bytes preserved: $relative" }

    # Re-load production security checks, mock only the Authenticode OS response.
    . $helper -Mode Library
    $payload = Join-Path $fixture 'payload.bin'
    [IO.File]::WriteAllText($payload,'synthetic payload')
    $definition = @{Algorithm='SHA256';Hash='incorrect'}
    Expect-Failure { Assert-MicrosoftPayload $payload $definition } 'checksum' 'wrong hash cannot execute'
    $script:processStarts = 0
    function Start-Process { param($FilePath,$ArgumentList,$PassThru,$Verb); $script:processStarts++; throw 'Unexpected process launch in offline fixture' }
    $definition.Arguments = '/synthetic'; $definition.Elevate = $false
    Expect-Failure { Invoke-MicrosoftInstaller $definition $payload } 'checksum' 'production execution boundary rejects a modified payload'
    $definition.Hash = (Get-FileHash $payload).Hash
    function Get-AuthenticodeSignature { param($LiteralPath); return @{Status='Valid';SignerCertificate=@{Subject='CN=Other, O=Other Corporation, C=US'}} }
    Expect-Failure { Assert-MicrosoftPayload $payload $definition } 'signature' 'valid non-Microsoft signature cannot execute'
    Expect-Failure { Invoke-MicrosoftInstaller $definition $payload } 'signature' 'production execution boundary rejects another publisher'
    function Get-AuthenticodeSignature { param($LiteralPath); return @{Status='HashMismatch';SignerCertificate=@{Subject='CN=Microsoft, O=Microsoft Corporation, C=US'}} }
    Expect-Failure { Invoke-MicrosoftInstaller $definition $payload } 'signature' 'invalid Microsoft signature cannot execute'
    function Get-AuthenticodeSignature { param($LiteralPath); return @{Status='Valid';SignerCertificate=$null} }
    Expect-Failure { Invoke-MicrosoftInstaller $definition $payload } 'signature' 'missing signing certificate cannot execute'
    Check ($script:processStarts -eq 0) 'failed hash and signature validation launch zero processes'
    function Get-AuthenticodeSignature { param($LiteralPath); return @{Status='Valid';SignerCertificate=@{Subject='CN=Microsoft, O=Microsoft Corporation, C=US'}} }
    Assert-MicrosoftPayload $payload $definition
    Check $true 'matching bytes with valid Microsoft publisher pass production validation'
    Remove-Item Function:\Start-Process
    Remove-Item Function:\Get-AuthenticodeSignature
    . $helper -Mode Library
    $installerSource = Get-Content (Join-Path $PSScriptRoot '../installer/BensonMail.iss') -Raw
    Check ($installerSource.Contains("ExpandConstant('{param:INSTALLDEPENDENCIES|0}') = '1'") -and $installerSource -match 'MB_YESNO or MB_DEFBUTTON2, IDNO') 'suppressed consent defaults No unless INSTALLDEPENDENCIES=1 is explicit'
    Check ($installerSource.IndexOf("RunPrerequisiteHelper('Install'") -gt $installerSource.IndexOf('if not Approved or UpdateCancelled')) 'installer consent/cancellation gate precedes download helper'

    $setupDecline = 'not requested'
    if ($Setup) {
        $Setup = (Resolve-Path -LiteralPath $Setup).Path
        if (!$actualBefore.dotnet -or !$actualBefore.winui) {
            $declinedTarget = Join-Path $fixture 'declined\BensonMail'
            $log = Join-Path $Evidence 'prerequisites-declined-setup.log'
            $process = Start-Process -FilePath $Setup -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/SP-',"/DIR=`"$declinedTarget`"","/LOG=`"$log`"") -PassThru
            if (!$process.WaitForExit(90000)) { $process.Kill(); throw 'Suppressed prerequisite decline did not finish within 90 seconds' }
            $process.Refresh()
            Check ($process.ExitCode -ne 0) 'actual Setup with suppressed prompts refuses missing runtimes'
            Check (!(Test-Path -LiteralPath $declinedTarget)) 'actual declined Setup creates no application directory or payload'
            $setupDecline = 'passed on missing-runtime Windows host'
            $process.Dispose()
        } else {
            $setupDecline = 'not applicable: all runtimes already installed; no runtime removed for testing'
        }
    }
    if ($ProvisionSharedRuntimes) {
        # Explicit CI opt-in. Production helper re-detects and installs only missing components.
        $result = Join-Path $Evidence 'prerequisites-install.ini'
        & "$env:WINDIR\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $helper -Mode Install -Components 'dotnet,winui' -ResultFile $result
        $installExitCode = $LASTEXITCODE
        @{
            registry = Get-ItemProperty 'HKLM:\SOFTWARE\WOW6432Node\dotnet\Setup\InstalledVersions\x64' -ErrorAction SilentlyContinue
            runtimes = @(& dotnet --list-runtimes)
            state = Get-PrerequisiteState
        } | ConvertTo-Json -Depth 6 | Set-Content (Join-Path $Evidence 'prerequisites-dotnet.json') -Encoding UTF8
        Get-AppxPackage | Where-Object { $_.Name -match 'WinApp|WindowsAppRuntime' } |
            Select-Object Name,Version,Architecture,PackageFamilyName,IsFramework,Status |
            ConvertTo-Json -Depth 4 | Set-Content (Join-Path $Evidence 'prerequisites-appx.json') -Encoding UTF8
        if (Test-Path -LiteralPath $result) { Write-Host (Get-Content -LiteralPath $result -Raw) }
        Check ($installExitCode -eq 0) 'official shared runtime installation succeeded'
        Check ((Get-Content $result -Raw) -match '(?m)^Status=ready') 'official runtime installation requires no outstanding reboot'
        $actualAfter = Get-PrerequisiteState
        Check ($actualAfter.dotnet -and $actualAfter.winui) 'real Windows shared runtimes meet published minimums'
    } else { $actualAfter = Get-PrerequisiteState }
    @{ok=$true;checks=@($checks.ToArray());before=$actualBefore;after=$actualAfter;setupDecline=$setupDecline;provisionRequested=[bool]$ProvisionSharedRuntimes} |
        ConvertTo-Json -Depth 5 | Set-Content (Join-Path $Evidence 'prerequisites-result.json') -Encoding UTF8
} finally {
    $env:PROCESSOR_ARCHITECTURE = $originalArchitecture
    $env:PROCESSOR_ARCHITEW6432 = $originalArchitecture6432
    Remove-Item -LiteralPath $fixture -Recurse -Force -ErrorAction SilentlyContinue
}

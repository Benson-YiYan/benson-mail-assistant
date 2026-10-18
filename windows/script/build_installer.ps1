param([Parameter(Mandatory=$true)][string]$PackageDir, [Parameter(Mandatory=$true)][string]$Version)
$ErrorActionPreference = 'Stop'
if ($Version -notmatch '^\d{12}$') { throw 'Installer version must be a yyyyMMddHHmm build timestamp' }
$PackageDir = (Resolve-Path -LiteralPath $PackageDir).Path
foreach ($required in @("BensonMail-$Version.exe", "Uninstall-BensonMail-$Version.exe", 'MailWorker.exe', '_internal')) {
    if (!(Test-Path -LiteralPath (Join-Path $PackageDir $required))) { throw "Incomplete or mismatched installer payload: $required" }
}
$temporary = if ($env:RUNNER_TEMP) { $env:RUNNER_TEMP } else { [IO.Path]::GetTempPath() }
$toolRoot = Join-Path $temporary 'BensonMail-Inno-7.1.0'
$compiler = Join-Path $toolRoot 'ISCC.exe'
if (!(Test-Path $compiler)) {
    $download = Join-Path $temporary 'BensonMail-innosetup-7.1.0.exe'
    Invoke-WebRequest 'https://github.com/jrsoftware/issrc/releases/download/is-7_1_0/innosetup-7.1.0-x64.exe' -OutFile $download
    $expected = '0362a383ed217d4c4239b5933866dd96d3eb2102737da92f80f6057a4b40df2f'
    if ((Get-FileHash $download -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) { throw 'Installer compiler checksum failed' }
    $installation = Start-Process $download -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-', "/DIR=`"$toolRoot`"") -Wait -PassThru
    if ($installation.ExitCode -ne 0 -or !(Test-Path $compiler)) { throw 'Installer compiler setup failed' }
}
& $compiler "/DAppVersion=$Version" "/DPackageDir=$PackageDir" (Join-Path $PSScriptRoot '../installer/BensonMail.iss')
if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed' }

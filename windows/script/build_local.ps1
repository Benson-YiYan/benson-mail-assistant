# Builds and tests only on this Windows computer. Does not publish or contact GitHub APIs.
$ErrorActionPreference = 'Stop'
$sourceRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Set-Location (Join-Path $sourceRoot 'windows')
New-Item -ItemType Directory -Force evidence | Out-Null
$log = Join-Path $PWD 'evidence/local-build.log'
Start-Transcript -Path $log -Force
try {
    if ($env:OS -ne 'Windows_NT') { throw 'Run this script inside Windows.' }
    if (!(Get-Command dotnet -ErrorAction SilentlyContinue)) { throw 'Install the official .NET 8 SDK, then run this script again. The SDK is required only for building.' }
    if (!(dotnet --list-sdks | Select-String '^8\.')) { throw 'The .NET 8 SDK is required to build this version.' }
    if (!(Get-Command python -ErrorAction SilentlyContinue)) { throw 'Install Python 3.11 or 3.12 for Windows x64 and enable Add Python to PATH, then retry.' }
    $pythonPlatform = python -c 'import sysconfig; print(sysconfig.get_platform())'
    if ($pythonPlatform.Trim() -ne 'win-amd64') { throw 'Use the Windows x64 Python installer (also inside an ARM Windows VM). This creates an x64 worker for the distributed x64 app.' }
    python -m venv .local-build-venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the isolated Python build environment.' }
    $env:PATH = (Join-Path $PWD '.local-build-venv/Scripts') + ';' + $env:PATH
    python -m pip install -r requirements.txt trustme
    if ($LASTEXITCODE -ne 0) { throw 'Build dependency download failed. Check the network and retry.' }
    python ../script/test_language_catalogs.py
    if ($LASTEXITCODE -ne 0) { throw 'Language catalog validation failed.' }
    python -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) { throw 'Backend tests failed; no installer was built.' }
    & ./build.ps1
    if ($LASTEXITCODE -ne 0) { throw 'Windows build failed.' }
    $setup = Get-ChildItem dist -Filter 'BensonMail-Windows-x64-Setup-*.exe' | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (!$setup) { throw 'Build produced no installer.' }
    $package = Get-ChildItem dist -Directory | Where-Object Name -Match '^BensonMail-\d{12}$' | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (!$package) { throw 'Build produced no application payload.' }
    # Runtime provisioning changes shared components, so leave that to the signed
    # official prerequisite installers reached through the normal consent screen.
    $output = Join-Path $sourceRoot 'Output'
    New-Item -ItemType Directory -Force $output | Out-Null
    Copy-Item $setup.FullName $output -Force
    Get-FileHash (Join-Path $output $setup.Name) -Algorithm SHA256 | Format-List
    Write-Host ('Installer ready: ' + (Join-Path $output $setup.Name))
    Write-Host 'Not published. Install and test the interface locally before release.'
} finally { Stop-Transcript }

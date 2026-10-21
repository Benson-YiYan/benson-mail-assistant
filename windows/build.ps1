$ErrorActionPreference = 'Stop'
if (!(Test-Path 'evidence/legacy-payload-manifest.json') -or
    !(Test-Path 'evidence/self-contained-payload-manifest.json')) {
    & "$PSScriptRoot/script/prepare_legacy_baseline.ps1"
    if ($LASTEXITCODE -ne 0) { throw 'Legacy migration baseline preparation failed' }
}
python script/make_icon.py
if ($LASTEXITCODE -ne 0) { throw 'Icon generation failed' }
# Start clean: publish does not remove the former self-contained runtime files.
foreach ($output in @('dist/native', 'dist/BensonMail')) {
    if (Test-Path $output) { Remove-Item -LiteralPath $output -Recurse -Force }
}
dotnet publish native/BensonMail.csproj -c Release -r win-x64 --self-contained false -o dist/native -p:Platform=x64 -p:WindowsAppSDKSelfContained=false
if ($LASTEXITCODE -ne 0) { throw 'WinUI publish failed' }
python -m PyInstaller --noconfirm --clean --onedir --console --hide-console hide-early --name MailWorker --icon assets/mail.ico --hidden-import win32timezone --hidden-import benson_mail.assistant_tools --hidden-import benson_mail.upstream_billing --hidden-import benson_mail.attachment_reader --hidden-import benson_mail.notification_policy --collect-all pypdf --collect-all certifi --collect-all truststore --exclude-module tkinter --exclude-module _tkinter --exclude-module PIL --exclude-module pystray --exclude-module benson_mail.ui --exclude-module benson_mail.app_icon worker.py
if ($LASTEXITCODE -ne 0) { throw 'Headless worker build failed' }
New-Item -ItemType Directory -Force dist/BensonMail | Out-Null
Copy-Item dist/MailWorker/* dist/BensonMail/ -Recurse -Force
Copy-Item dist/native/* dist/BensonMail/ -Recurse -Force
# Debug symbols are for developers; the shipped app never loads them.
Get-ChildItem dist/BensonMail -Recurse -Filter *.pdb | Remove-Item -Force
Copy-Item dist/BensonMail/BensonMail.exe dist/BensonMail/Uninstall.exe -Force
Copy-Item README.md dist/BensonMail/使用说明.md
Copy-Item README.en.md "dist/BensonMail/Read me - English.md"
Copy-Item docs/Mail-account-setup-*.txt dist/BensonMail/
Copy-Item docs/Quick-start-*.txt dist/BensonMail/
Copy-Item docs/Markdig-LICENSE.txt dist/BensonMail/
Copy-Item docs/Get-Outlook-Token.bat, docs/Get-Outlook-Token.ps1 dist/BensonMail/
New-Item -ItemType Directory -Force dist/BensonMail/assets | Out-Null
Copy-Item assets/mail.ico dist/BensonMail/assets/mail.ico -Force
$chinaZone = [TimeZoneInfo]::FindSystemTimeZoneById('China Standard Time')
$version = [TimeZoneInfo]::ConvertTimeFromUtc([DateTime]::UtcNow, $chinaZone).ToString('yyyyMMddHHmm')
Set-Content -LiteralPath dist/BensonMail/build-version.txt -Value $version -Encoding ascii
Rename-Item dist/BensonMail/BensonMail.exe "BensonMail-$version.exe"
Rename-Item "dist/BensonMail/Uninstall.exe" "Uninstall-BensonMail-$version.exe"
Rename-Item dist/BensonMail "BensonMail-$version"
python script/payload_manifest.py migration "dist/BensonMail-$version" evidence/legacy-payload-manifest.json
if ($LASTEXITCODE -ne 0) { throw 'Payload migration manifest generation failed' }
& "$PSScriptRoot/script/build_installer.ps1" -PackageDir (Resolve-Path "dist/BensonMail-$version").Path -Version $version
if ($LASTEXITCODE -ne 0) { throw 'Installer build failed' }

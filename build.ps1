$ErrorActionPreference = 'Stop'
python script/make_icon.py
if ($LASTEXITCODE -ne 0) { throw 'Icon generation failed' }
dotnet publish native/BensonMail.csproj -c Release -r win-x64 -o dist/native -p:Platform=x64
if ($LASTEXITCODE -ne 0) { throw 'WinUI publish failed' }
python -m PyInstaller --noconfirm --clean --onedir --windowed --name BensonMail --icon assets/mail.ico --add-data "assets;assets" --hidden-import win32timezone --collect-all pystray --collect-all pypdf --collect-all certifi --collect-all truststore main.py
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed' }
Copy-Item README.md dist/BensonMail/使用说明.md
Copy-Item README.en.md "dist/BensonMail/Read me - English.md"
Copy-Item docs/Mail-account-setup-*.txt dist/BensonMail/
Copy-Item docs/Markdig-LICENSE.txt dist/BensonMail/
Copy-Item docs/Get-Outlook-Token.bat, docs/Get-Outlook-Token.ps1 dist/BensonMail/
python -m PyInstaller --noconfirm --clean --onedir --console --hide-console hide-early --name MailWorker --icon assets/mail.ico --add-data "assets;assets" --hidden-import win32timezone --collect-all pypdf --collect-all certifi --collect-all truststore main.py
if ($LASTEXITCODE -ne 0) { throw 'Worker build failed' }
$legacyExe = 'dist/BensonMail/BensonMail.exe'
$uninstaller = 'dist/BensonMail/Uninstall.exe'
Move-Item $legacyExe $uninstaller -Force
Copy-Item dist/MailWorker/* dist/BensonMail/ -Recurse -Force
Copy-Item dist/native/* dist/BensonMail/ -Recurse -Force
Copy-Item dist/BensonMail/BensonMail.exe dist/BensonMail/Uninstall.exe -Force
New-Item -ItemType Directory -Force dist/BensonMail/assets | Out-Null
Copy-Item assets/mail.ico dist/BensonMail/assets/mail.ico -Force
$chinaZone = [TimeZoneInfo]::FindSystemTimeZoneById('China Standard Time')
$version = [TimeZoneInfo]::ConvertTimeFromUtc([DateTime]::UtcNow, $chinaZone).ToString('yyyyMMddHHmm')
Set-Content -LiteralPath dist/BensonMail/build-version.txt -Value $version -Encoding ascii
Rename-Item dist/BensonMail/BensonMail.exe "BensonMail-$version.exe"
Rename-Item "dist/BensonMail/Uninstall.exe" "Uninstall-BensonMail-$version.exe"
Rename-Item dist/BensonMail "BensonMail-$version"
& "$PSScriptRoot/script/build_installer.ps1" -PackageDir (Resolve-Path "dist/BensonMail-$version").Path -Version $version
if ($LASTEXITCODE -ne 0) { throw 'Installer build failed' }

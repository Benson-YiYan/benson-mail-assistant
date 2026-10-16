$ErrorActionPreference = 'Stop'
python script/make_icon.py
if ($LASTEXITCODE -ne 0) { throw 'Icon generation failed' }
dotnet publish native/BensonMail.csproj -c Release -r win-x64 -o dist/native -p:Platform=x64
if ($LASTEXITCODE -ne 0) { throw 'WinUI publish failed' }
python -m PyInstaller --noconfirm --clean --onedir --windowed --name BensonMail --icon assets/mail.ico --add-data "assets;assets" --hidden-import win32timezone --collect-all pystray --collect-all pypdf --collect-all certifi --collect-all truststore main.py
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed' }
Copy-Item README.md dist/BensonMail/使用说明.md
python -m PyInstaller --noconfirm --clean --onedir --console --name MailWorker --icon assets/mail.ico --add-data "assets;assets" --hidden-import win32timezone --collect-all pypdf --collect-all certifi --collect-all truststore main.py
if ($LASTEXITCODE -ne 0) { throw 'Worker build failed' }
$legacyExe = 'dist/BensonMail/BensonMail.exe'
$uninstaller = 'dist/BensonMail/Uninstall.exe'
Move-Item $legacyExe $uninstaller -Force
Copy-Item dist/MailWorker/* dist/BensonMail/ -Recurse -Force
Copy-Item dist/native/* dist/BensonMail/ -Recurse -Force
New-Item -ItemType Directory -Force dist/BensonMail/assets | Out-Null
Copy-Item assets/mail.ico dist/BensonMail/assets/mail.ico -Force
$chinaZone = [TimeZoneInfo]::FindSystemTimeZoneById('China Standard Time')
$version = [TimeZoneInfo]::ConvertTimeFromUtc([DateTime]::UtcNow, $chinaZone).ToString('yyyyMMddHHmm')
Rename-Item dist/BensonMail/BensonMail.exe "BensonMail-$version.exe"
Rename-Item "dist/BensonMail/Uninstall.exe" "Uninstall-BensonMail-$version.exe"
Rename-Item dist/BensonMail "BensonMail-$version"
Compress-Archive -Path "dist/BensonMail-$version" -DestinationPath "dist/BensonMail-Windows-x64-$version.zip" -Force

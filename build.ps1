$ErrorActionPreference = 'Stop'
python -m PyInstaller --noconfirm --clean --onedir --windowed --name BensonMail --collect-all pystray --collect-all pypdf main.py
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed' }
Copy-Item README.md dist/BensonMail/使用说明.md
$version = '202610161600'
Rename-Item dist/BensonMail/BensonMail.exe "BensonMail-$version.exe"
Rename-Item dist/BensonMail "BensonMail-$version"
Compress-Archive -Path "dist/BensonMail-$version" -DestinationPath "dist/BensonMail-Windows-x64-$version.zip" -Force

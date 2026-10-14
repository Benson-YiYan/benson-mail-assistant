$ErrorActionPreference = 'Stop'
python -m PyInstaller --noconfirm --clean --onedir --windowed --name BensonMail --collect-all pystray --collect-all pypdf main.py
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed' }
Copy-Item README.md dist/BensonMail/使用说明.md
Compress-Archive -Path dist/BensonMail -DestinationPath dist/BensonMail-Windows-x64.zip -Force

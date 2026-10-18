# Windows development

Use the `build/windows-app` branch for the current WinUI application.

## Requirements

Windows x64, Python 3.12, .NET 8 SDK and Inno Setup supporting the Windows 11 wizard style in `installer/BensonMail.iss`.

## Test and build

```powershell
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
./build.ps1
```

Some Windows platform tests are skipped on other operating systems. The build produces the versioned Setup EXE in `dist`, using the actual build time in Asia/Shanghai.

`README.md` and `README.en.md` are shipped as Chinese and English user guides. Keep them consistent with the installed UI.

## CI evidence

GitHub Actions runs synthetic backend tests, the source and packaged WinUI UI tests, Markdown rendering, bilingual controls, search, filters, verified downloads, installation handoff, shortcut preservation and uninstall cleanup.
The package artifact is `BensonMail-Windows-x64`; evidence is `Windows-test-evidence`.
Tests do not authenticate to real mailboxes or AI accounts. A passing build does not establish that a user's credentials, provider policy or network will work.

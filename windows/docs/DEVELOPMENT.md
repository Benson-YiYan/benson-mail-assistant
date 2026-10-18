# Windows development

Use the `main` branch. Run the commands below from the `windows/` directory (`cd windows` after cloning).

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

## Legacy migration baseline

Public builds load the recorded legacy file fingerprints and size baseline from `packaging/`; no private repository or historical Git commit is required. Read [packaging notes](../packaging/README.md) for the distinction between the original real-binary migration verification and replay in public CI.

# Windows development

Use the `main` branch. Run the commands below from the `windows/` directory (`cd windows` after cloning).

## Requirements

Windows x64, Python 3.12, .NET 8 SDK and Inno Setup supporting the Windows 11 wizard style in `installer/BensonMail.iss`.

## Test and build

```powershell
python -m pip install -r requirements.txt
python -m pip install "trustme>=1.2,<2" "pywinauto>=0.6.9,<0.7" "tzdata>=2025"
python -m unittest discover -s tests -v
./build.ps1
```

Some Windows platform tests are skipped on other operating systems. The build produces the versioned Setup EXE in `dist`, using the actual build time in Asia/Shanghai.

The Chinese, English and Spanish READMEs and guides must stay consistent with the UI. Language packs are data-only JSON assets, generated from reviewed catalogs and guides:

```powershell
python ../script/build_language_packs.py --output evidence/test-language-packs
$env:BENSON_MAIL_TEST_LANGUAGE_PACKS = (Resolve-Path evidence/test-language-packs/windows).Path
```

Only explicit synthetic UI test entry points accept that environment variable. A normal launch uses verified downloaded packs. The CI workflow shows the complete native test commands; do not point fixtures at a real user's application data.

## CI evidence

GitHub Actions runs synthetic backend tests, source and packaged UI tests, Markdown rendering, three-language controls, report regeneration, per-email chat with files, context compression, search, filters, verified downloads, installation handoff, shortcut preservation and uninstall cleanup.
The package artifact is `BensonMail-Windows-x64`; evidence is `Windows-test-evidence`.
Tests do not authenticate to real mailboxes or AI accounts. A passing build does not establish that a user's credentials, provider policy or network will work.

## Legacy migration baseline

Public builds load the recorded legacy file fingerprints and size baseline from `packaging/`; no private repository or historical Git commit is required. Read [packaging notes](../packaging/README.md) for the distinction between the original real-binary migration verification and replay in public CI.

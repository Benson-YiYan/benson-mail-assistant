# Shared runtime prerequisites

The published application requires .NET `Microsoft.NETCore.App` x64 >= 8.0.32
(8.0 patch releases only) and Windows App Runtime 1.8 >= 8000.994.2142.0.
`build_installer.ps1` reads the actual .NET minimum from the published
runtimeconfig and refuses a package newer than the pinned download.

`prerequisites.ps1 -Mode Detect` performs local detection only. It checks the
x64 .NET registry installation and runtime files, and the Microsoft AppX
Framework, Main, Singleton and DDLM packages. Main/Singleton use the native
OS architecture. An incomplete runtime installation requires repair.

Setup asks separately before downloading only missing components. Suppressed
dialogs default to No; unattended provisioning requires the explicit
`/INSTALLDEPENDENCIES=1` switch. Existing shared runtimes are never uninstalled.
During an application update, Setup acknowledges the old application's handoff
and waits for its exit before this prerequisite confirmation. No application
payload is replaced until prerequisite preparation succeeds.

Pinned official sources:

- .NET release metadata:
  https://builds.dotnet.microsoft.com/dotnet/release-metadata/8.0/releases.json
- Windows App SDK release archive:
  https://learn.microsoft.com/en-us/windows/apps/windows-app-sdk/downloads-archive
- Required Framework/Main/Singleton/DDLM components:
  https://learn.microsoft.com/en-us/windows/apps/windows-app-sdk/deploy-unpackaged-apps

Payload URLs and checksums are pinned in `prerequisites.ps1`. Before execution,
Setup checks both the full file hash and a valid Microsoft Corporation
Authenticode signature. Redirects are restricted to approved Microsoft HTTPS
hosts. Failure or reboot-required status stops application installation.

Windows CI:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File script/check_prerequisites.ps1 `
  -Evidence evidence -Setup path\to\BensonMail-Setup.exe -ProvisionSharedRuntimes
```

Offline fixture checks run first. The optional actual Setup decline case runs
only when a runtime is missing; it never removes installed shared components.
The explicit provisioning flag then installs missing official components and
verifies local runtime detection. The CI application launch test must follow.

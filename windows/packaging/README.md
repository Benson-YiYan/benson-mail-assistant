# Recorded legacy upgrade metadata

These files make the public source build independent of the earlier repository's Git history. They contain filenames, SHA256 fingerprints, measured byte counts and test outcomes, never mailbox or AI configuration.

- `legacy-payload-manifest.json`: exact fingerprints of the pre-slimming release payload. The build compares these paths with the current payload. Setup removes only absent files whose installed bytes still match the recorded legacy SHA256. Modified files and unrelated files are preserved.
- `package-size-baseline.json`: recorded unpacked payload measurement, 378,459,840 bytes. Public CI compares against this fixed measurement; it does not claim to rebuild the historical release in the same run.
- `update-handoff-result.json`: recorded successful Windows integration replay for release 202610181547, including actual legacy WinForms/WPF/Tcl/Tk/Pillow removal, cancellation, configuration/report preservation and new executable relaunch.

The public CI still runs the real installer/uninstaller and production update handoff, cancellation, relaunch, rejected-target and preservation tests. It explicitly reports that actual legacy-binary removal replay is not run when the historical binary fixture directory is absent. Those binaries are deliberately not duplicated in the source tree. Manifest generation and traversal rejection tests run on every build.

For local builds from this source tree, run `./build.ps1` from `windows/`. It loads the checked-in metadata automatically; the Windows app uses shared .NET 8 and Windows App Runtime 1.8 components, detected by Setup before installation. CI captures the pinned 202610181752 self-contained release fingerprints and exercises removal of actual obsolete runtime files. Shared system runtimes are never removed.

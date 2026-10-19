# Load the recorded legacy release fingerprints; no private repository history is needed.
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$evidence = Join-Path $root 'evidence'
New-Item -ItemType Directory -Force $evidence | Out-Null
foreach ($name in @('legacy-payload-manifest.json', 'package-size-baseline.json')) {
    Copy-Item -LiteralPath (Join-Path $root "packaging/$name") -Destination (Join-Path $evidence $name) -Force
}
if ($env:GITHUB_ACTIONS -eq 'true') {
    python (Join-Path $root 'script/prepare_shared_migration.py')
    if ($LASTEXITCODE -ne 0) { throw 'Self-contained runtime migration baseline capture failed' }
} elseif (Test-Path (Join-Path $root 'packaging/self-contained-payload-manifest.json')) {
    Copy-Item (Join-Path $root 'packaging/self-contained-payload-manifest.json') (Join-Path $evidence 'self-contained-payload-manifest.json') -Force
}

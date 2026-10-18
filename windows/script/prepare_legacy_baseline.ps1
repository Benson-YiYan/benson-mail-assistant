# Load the recorded legacy release fingerprints; no private repository history is needed.
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$evidence = Join-Path $root 'evidence'
New-Item -ItemType Directory -Force $evidence | Out-Null
foreach ($name in @('legacy-payload-manifest.json', 'package-size-baseline.json')) {
    Copy-Item -LiteralPath (Join-Path $root "packaging/$name") -Destination (Join-Path $evidence $name) -Force
}

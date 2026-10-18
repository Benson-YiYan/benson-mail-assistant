# Rebuild the last unoptimized release in isolation for an exact installed-byte comparison.
# Only build products are measured. The baseline app/installer is never run or shipped.
$ErrorActionPreference = 'Stop'
$baselineCommit = 'a7230fd5e5e174b10fa27bd2fe2d99a98d4a8847'
$baselineRoot = Join-Path $env:RUNNER_TEMP ('BensonMail-size-baseline-' + [Guid]::NewGuid().ToString('N'))
$archive = $baselineRoot + '.zip'
$measure = Join-Path $PSScriptRoot 'measure_package.py'
$result = Join-Path $PWD 'evidence/package-size-baseline.json'
try {
    git archive --format=zip "--output=$archive" $baselineCommit
    if ($LASTEXITCODE -ne 0) { throw 'Baseline source archive failed' }
    Expand-Archive -LiteralPath $archive -DestinationPath $baselineRoot
    $source = Get-Content (Join-Path $baselineRoot 'build.ps1') -Raw
    $setupOffset = $source.IndexOf('& "$PSScriptRoot/script/build_installer.ps1"')
    if ($setupOffset -lt 0) { throw 'Unexpected baseline build structure' }
    $build = Join-Path $baselineRoot 'build-size-only.ps1'
    Set-Content -LiteralPath $build -Value $source.Substring(0, $setupOffset) -Encoding utf8
    Push-Location $baselineRoot
    try {
        & $build
        if ($LASTEXITCODE -ne 0) { throw 'Baseline build failed' }
        $package = Get-ChildItem dist -Directory | Where-Object Name -Match '^BensonMail-\d{12}$' | Select-Object -First 1
        if (!$package) { throw 'Missing baseline package' }
        python $measure $package.FullName $result --baseline-commit $baselineCommit
        if ($LASTEXITCODE -ne 0) { throw 'Baseline measurement failed' }
    } finally { Pop-Location }
} finally {
    Remove-Item -LiteralPath $archive -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $baselineRoot -Recurse -Force -ErrorAction SilentlyContinue
}

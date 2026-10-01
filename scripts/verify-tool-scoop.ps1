# Real Scoop installs of published artifacts; no mocks or substituted tools.
# PRs exercise a generated local bucket. Dispatch exercises the public bucket.
# Checks all shipped Windows architectures, exact installed payload bytes,
# executable versions and io-mon's real file capture and child exit status.
param(
    [ValidateSet('64bit', 'arm64')][string]$Architecture,
    [switch]$Live
)
$ErrorActionPreference = 'Stop'
$native = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString()
$expectedNative = if ($Architecture -eq 'arm64') { 'Arm64' } else { 'X64' }
if ($native -ne $expectedNative) { throw "Expected native $expectedNative, found $native" }
$products = if ($Architecture -eq 'arm64') { @('gosti', 'runquota') } else { @('gosti', 'io-mon', 'runquota') }
$work = Join-Path $env:RUNNER_TEMP "tool-scoop-$Architecture"
New-Item -ItemType Directory -Force $work | Out-Null
$bucket = Join-Path $work 'bucket-repo'
if (-not $Live) {
    git init -q $bucket
    if ($LASTEXITCODE) { throw 'git init failed' }
    foreach ($app in $products) {
        $release = Join-Path $work $app
        gh release download v0.1.0 -R "metacraft-labs/$app" -D $release -p '*-windows-*.zip' -p SHA256SUMS
        if ($LASTEXITCODE) { throw "$app release download failed" }
        python scripts/scoop-manifest.py --config "scoop/$app.json" --tag v0.1.0 --release-dir $release --bucket "$bucket/bucket"
        if ($LASTEXITCODE) { throw "$app manifest generation failed" }
    }
    git -C $bucket add bucket
    git -C $bucket -c user.name=ci -c user.email=ci@example.invalid commit -q -m 'Verified tool manifests'
    if ($LASTEXITCODE) { throw 'bucket commit failed' }
    $bucketUrl = $bucket -replace '\\', '/'
} else {
    $bucketUrl = 'https://github.com/metacraft-labs/metacraft-desktop-packages'
}
scoop bucket add metacraft $bucketUrl
if ($LASTEXITCODE) { throw 'bucket registration failed' }
foreach ($app in $products) {
    $manifestPath = "$env:USERPROFILE/scoop/buckets/metacraft/bucket/$app.json"
    $manifest = Get-Content $manifestPath -Raw | ConvertFrom-Json
    $version = $manifest.version
    $release = Join-Path $work $app
    if ($Live) {
        gh release download "v$version" -R "metacraft-labs/$app" -D $release -p '*-windows-*.zip' -p SHA256SUMS
        if ($LASTEXITCODE) { throw "$app release download failed" }
        python scripts/scoop-manifest.py --config "scoop/$app.json" --tag "v$version" --release-dir $release --bucket "$work/expected"
        if ($LASTEXITCODE) { throw "$app release verification failed" }
        $expected = Get-Content "$work/expected/$app.json" -Raw | ConvertFrom-Json
        if ($manifest.architecture.$Architecture.hash -ne $expected.architecture.$Architecture.hash) {
            throw "$app bucket hash differs from its verified release"
        }
    }
    scoop install "metacraft/$app" --arch $Architecture
    if ($LASTEXITCODE) { throw "$app Scoop installation failed" }
    $installed = (scoop prefix $app | Out-String).Trim()
    if ($LASTEXITCODE) { throw "$app install root unavailable" }
    $entry = $manifest.architecture.$Architecture
    $asset = [System.IO.Path]::GetFileName(([Uri]$entry.url).AbsolutePath)
    python scripts/verify-installed-archive.py --archive "$release/$asset" --extract-dir $entry.extract_dir --installed-root $installed --architecture $Architecture
    if ($LASTEXITCODE) { throw "$app installed payload differs from its release" }
    if ($app -eq 'io-mon') {
        $env:IO_MON_CLI = "$env:USERPROFILE/scoop/shims/io-mon.exe"
        python scripts/verify-io-mon-install.py
        if ($LASTEXITCODE) { throw 'installed io-mon capture failed' }
    } else {
        $commands = if ($app -eq 'gosti') { @('gosti', 'vm-harness') } else { @('runquota', 'runquotad') }
        foreach ($command in $commands) {
            $output = & "$env:USERPROFILE/scoop/shims/$command.exe" --version
            if ($LASTEXITCODE -or "$output" -notmatch "(^|\s)$([regex]::Escape($version))(\s|$)") {
                throw "$command version check failed: $output"
            }
            Write-Host $output
        }
    }
    Write-Host "PASS: $app $version installed from $bucketUrl as $Architecture"
}
scoop status
if ($LASTEXITCODE) { throw 'Scoop update-source check failed' }

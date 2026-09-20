param([switch]$Baseline)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$appDir = Join-Path $repo '.tools/redux'
$disc = Join-Path $repo '.tools/redux-analysis/disc1/disc.cue'
$bios = Join-Path $appDir 'scph5500.bin'
$observer = Join-Path $PSScriptRoot 'observe.lua'
foreach ($file in @((Join-Path $appDir 'pcsx-redux.exe'), $disc, $bios, $observer)) {
    if (-not (Test-Path -LiteralPath $file)) { throw "Missing file: $file" }
    if ($file -match '[^\x00-\x7F]') { throw "Use an ASCII path for this PCSX-Redux build: $file" }
}
if ((Get-FileHash -LiteralPath $bios -Algorithm MD5).Hash -ne '8DD7D5296A650FAC7319BCE665A6A53C') {
    throw 'Unexpected BIOS: this test profile requires SCPH-5500 v3.0 JP.'
}
if (Get-NetTCPConnection -LocalPort 18080 -State Listen -ErrorAction SilentlyContinue) {
    throw 'Port 18080 is in use. Close the previous analysis session before launching another.'
}
$mode = if ($Baseline) { 'baseline' } else { 'observed' }
$log = Join-Path $repo ".tools/redux-analysis/$mode.log"
$archive = Join-Path $repo ('.tools/redux-analysis/archive/' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
foreach ($previous in @($log, (Join-Path $appDir 'bios-calls.csv'), (Join-Path $appDir 'memory-watch.csv'))) {
    if (Test-Path -LiteralPath $previous) {
        New-Item -ItemType Directory -Force $archive | Out-Null
        Copy-Item -LiteralPath $previous -Destination $archive
    }
}
$arguments = @('-portable', '-run', '-interpreter', '-no-fastboot', '-softgpu',
    '-webserver', '-webserver-port', '18080', '-bios', ('"' + $bios + '"'),
    '-iso', ('"' + $disc + '"'), '-logfile', ('"' + $log + '"'))
if ($Baseline) { $arguments += '-no-debugger' }
else { $arguments += @('-debugger', '-dofile', ('"' + $observer + '"')) }
$process = Start-Process -FilePath (Join-Path $appDir 'pcsx-redux.exe') -ArgumentList $arguments `
    -WorkingDirectory $appDir -WindowStyle Normal -PassThru
$process.Id | Set-Content (Join-Path $repo '.tools/redux-analysis/process.pid')
Write-Output "Started $mode session (wrapper PID $($process.Id)). API: http://127.0.0.1:18080"

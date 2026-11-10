#Requires -Version 7.2
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$PythonExe,
    [Parameter(Mandatory)][string]$NodeExe,
    [ValidatePattern('^[a-f0-9]{32}$')][string]$Nonce = [guid]::NewGuid().ToString('N')
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$local = Join-Path $repo '.local'
$runs = Join-Path $local 'rpf-112'
$root = Join-Path $local 'rpf-100-product'
$run = Join-Path $runs $Nonce
$owner = Join-Path $root "competition-rpf112-$Nonce"

function Get-Binary([string]$Path, [string]$Name) {
    if (![IO.Path]::IsPathFullyQualified($Path)) { throw "Supply an absolute $Name path." }
    $file = Get-Item -LiteralPath $Path
    if ($file.PSIsContainer -or $file.Name -ne $Name -or
        ($file.Attributes -band [IO.FileAttributes]::ReparsePoint) -or $file.FullName -match 'WindowsApps|PyManager') {
        throw "Unverified executable $Name."
    }
    $file.FullName
}

function New-Service([string]$Exe, [string[]]$Arguments) {
    $info = [Diagnostics.ProcessStartInfo]::new($Exe)
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.WorkingDirectory = $repo
    $info.Environment.Clear()
    foreach ($name in @('SystemRoot', 'WINDIR', 'SystemDrive', 'ComSpec')) {
        $value = [Environment]::GetEnvironmentVariable($name, 'Process')
        if ($value) { $info.Environment[$name] = $value }
    }
    $info.Environment['TEMP'] = $run
    $info.Environment['TMP'] = $run
    $info.Environment['RPF100_GATEWAY_TOKEN'] = $token
    $info.Environment['RPF100_PRODUCT_ENABLED'] = '1'
    $info.Environment['VITE_CONTROL_PLANE_DATA_SOURCE'] = 'fixture'
    foreach ($argument in $Arguments) { $info.ArgumentList.Add($argument) }
    [Diagnostics.Process]::Start($info)
}

$PythonExe = Get-Binary $PythonExe 'python.exe'
$NodeExe = Get-Binary $NodeExe 'node.exe'
& $PythonExe -I -B -c 'import sqlite3, sys; assert sys.version_info >= (3, 11)'
if ($LASTEXITCODE) { throw 'CPython/SQLite check failed.' }
$vite = Join-Path $repo 'node_modules/vite/bin/vite.js'
if (!(Test-Path -LiteralPath $vite -PathType Leaf)) { throw 'Existing Vite dependencies required.' }
if (Get-NetTCPConnection -State Listen -LocalPort 4187,8780 -ErrorAction SilentlyContinue) {
    throw 'Competition port occupied.'
}
foreach ($dir in @($repo, $local, $runs, $root, $run, $owner)) {
    $item = Get-Item -LiteralPath $dir -Force -ErrorAction SilentlyContinue
    if ($item -and (!$item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint))) {
        throw 'Unsafe competition directory.'
    }
}
if ((Test-Path -LiteralPath $run) -or (Test-Path -LiteralPath $owner)) { throw 'Fresh nonce required.' }
New-Item -ItemType Directory -Path $run | Out-Null
$config = Join-Path $run 'vite.config.mts'
@'
import { fileURLToPath } from 'node:url';
import base from '../../../vite.config.ts';

export default {
  ...base,
  cacheDir: fileURLToPath(new URL('./vite-cache', import.meta.url)),
  envDir: fileURLToPath(new URL('./', import.meta.url)),
  server: { ...base.server, watch: null, hmr: false },
};
'@ | Set-Content -LiteralPath $config -Encoding utf8
$token = [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32)).ToLowerInvariant()
$receipt = Join-Path $run 'processes.json'
$claim = [IO.File]::Open($receipt, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
$processes = @()
try {
    $processes += New-Service $PythonExe @('-E', '-B', '-m',
        'runtime.runproof_runtime.effectwitness.rpf112_competition_gateway', '--nonce', $Nonce)
    $processes += New-Service $NodeExe @($vite, '--config', $config, '--configLoader', 'runner', '--port', '4187')
} finally {
    try {
        $records = @($processes | ForEach-Object {
            @{ pid = $_.Id; exe = $_.Path; started = $_.StartTime.ToUniversalTime().Ticks.ToString() }
        })
        $bytes = [Text.Encoding]::UTF8.GetBytes((ConvertTo-Json -InputObject @{ nonce = $Nonce; records = $records } -Compress))
        $claim.Write($bytes, 0, $bytes.Length)
        $claim.Flush($true)
    } finally { $claim.Dispose() }
}
$deadline = [DateTime]::UtcNow.AddSeconds(25)
do {
    foreach ($process in $processes) {
        if ($process.HasExited) { throw "Competition service exited ($($process.ExitCode)). Stop using nonce $Nonce." }
    }
    $gateway = Get-NetTCPConnection -State Listen -LocalAddress 127.0.0.1 -LocalPort 8780 -ErrorAction SilentlyContinue
    $web = Get-NetTCPConnection -State Listen -LocalAddress 127.0.0.1 -LocalPort 4187 -ErrorAction SilentlyContinue
    if ($gateway.OwningProcess -eq $processes[0].Id -and $web.OwningProcess -eq $processes[1].Id) {
        Write-Output "http://127.0.0.1:4187/effectwitness/live-local"
        Write-Output "Nonce=$Nonce"
        return
    }
    Start-Sleep -Milliseconds 250
} while ([DateTime]::UtcNow -lt $deadline)
throw "Readiness unconfirmed. Stop using nonce $Nonce."

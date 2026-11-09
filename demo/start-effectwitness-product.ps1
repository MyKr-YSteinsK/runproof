[CmdletBinding()]
param([Parameter(Mandatory)][string]$PythonExe, [Parameter(Mandatory)][string]$NodeExe)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$root = Join-Path $repo '.local/rpf-100-product'
$owner = Join-Path $root 'live'

function Get-Binary([string]$Value, [string]$Name) {
    if (![IO.Path]::IsPathRooted($Value)) { throw "Supply an absolute $Name path." }
    $file = Get-Item -LiteralPath $Value
    if ($file.Name -ne $Name -or $file.PSIsContainer -or
        ($file.Attributes -band [IO.FileAttributes]::ReparsePoint) -or $file.FullName -match 'WindowsApps|PyManager') {
        throw "Unverified executable $Name."
    }
    return $file.FullName
}

function Confirm-Directory([string]$Path) {
    if (Test-Path -LiteralPath $Path) {
        $item = Get-Item -LiteralPath $Path
        if (!$item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw 'Directory ownership cannot be verified.'
        }
    }
}

$PythonExe = Get-Binary $PythonExe 'python.exe'
$NodeExe = Get-Binary $NodeExe 'node.exe'
& $PythonExe -I -B -c 'import sqlite3; import sys; assert sys.version_info >= (3, 11)'
if ($LASTEXITCODE) { throw 'CPython/SQLite check failed.' }
& $NodeExe --version
if ($LASTEXITCODE) { throw 'Node check failed.' }
$vite = Join-Path $repo 'node_modules/vite/bin/vite.js'
if (!(Test-Path -LiteralPath $vite -PathType Leaf)) { throw 'Existing Vite dependencies required.' }
foreach ($name in @('.env','.env.local','.env.development','.env.development.local')) {
    if (Test-Path -LiteralPath (Join-Path $repo $name)) { throw 'Use a checkout without Vite environment files.' }
}
if (Get-NetTCPConnection -State Listen -LocalPort 4187,8780 -ErrorAction SilentlyContinue) { throw 'Product port occupied.' }
foreach ($dir in @($repo,(Join-Path $repo '.local'),$root,$owner)) { Confirm-Directory $dir }
if (!(Test-Path -LiteralPath $root)) { New-Item -ItemType Directory -Path $root | Out-Null }
if (!(Test-Path -LiteralPath $owner)) {
    New-Item -ItemType Directory -Path $owner | Out-Null
    New-Item -ItemType File -Path (Join-Path $owner 'rpf100-owner-v1') | Out-Null
} else {
    $marker = Get-Item -LiteralPath (Join-Path $owner 'rpf100-owner-v1')
    if ($marker.PSIsContainer -or ($marker.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'Owner marker must be a regular file.'
    }
}
$activePath = Join-Path $owner 'active.json'
$claim = [IO.File]::Open($activePath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
$run = Join-Path $owner ([guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $run | Out-Null
$names = @('RPF100_GATEWAY_TOKEN','RPF100_PRODUCT_ENABLED','RPF_EW_LAB_ENABLED','RPF_EW_LAB_TASK_OUTPUT',
    'VITE_CONTROL_PLANE_DATA_SOURCE','VITE_RPF_RECORDED_DELIVERY','PYTHONDONTWRITEBYTECODE')
$saved = @{}
foreach ($name in $names) { $saved[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }
$processes = @()
try {
    $random = New-Object byte[] 32
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($random) } finally { $rng.Dispose() }
    $env:RPF100_GATEWAY_TOKEN = [BitConverter]::ToString($random).Replace('-', '').ToLowerInvariant()
    $env:RPF100_PRODUCT_ENABLED = '1'
    $env:RPF_EW_LAB_ENABLED = '0'
    $env:RPF_EW_LAB_TASK_OUTPUT = '0'
    $env:VITE_CONTROL_PLANE_DATA_SOURCE = 'fixture'
    $env:VITE_RPF_RECORDED_DELIVERY = '0'
    $env:PYTHONDONTWRITEBYTECODE = '1'
    $processes += Start-Process -FilePath $PythonExe -ArgumentList @('-B','-m',
        'runtime.runproof_runtime.effectwitness.product_local_gateway','--owner',('"' + $owner + '"')) -WorkingDirectory $repo -PassThru -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $run 'gateway.stdout') -RedirectStandardError (Join-Path $run 'gateway.stderr')
    $processes += Start-Process -FilePath $NodeExe -ArgumentList @(('"' + $vite + '"'),'--configLoader','runner','--port','4187') -WorkingDirectory $repo -PassThru -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $run 'vite.stdout') -RedirectStandardError (Join-Path $run 'vite.stderr')
} finally {
    foreach ($name in $names) { [Environment]::SetEnvironmentVariable($name, $saved[$name], 'Process') }
    try {
        $records = @($processes | ForEach-Object {
            @{ pid = $_.Id; exe = $_.Path; started = $_.StartTime.ToUniversalTime().Ticks.ToString() }
        })
        $json = ConvertTo-Json -InputObject $records -Compress
        $bytes = [Text.Encoding]::UTF8.GetBytes($json)
        $claim.Write($bytes,0,$bytes.Length)
        $claim.Flush($true)
    } finally { $claim.Dispose() }
}
$deadline = [DateTime]::UtcNow.AddSeconds(20)
do {
    foreach ($process in $processes) { if ($process.HasExited) { throw "Startup failed. Inspect this run's logs: $run" } }
    $gateway = Get-NetTCPConnection -State Listen -LocalAddress 127.0.0.1 -LocalPort 8780 -ErrorAction SilentlyContinue
    $web = Get-NetTCPConnection -State Listen -LocalAddress 127.0.0.1 -LocalPort 4187 -ErrorAction SilentlyContinue
    if ($gateway.OwningProcess -eq $processes[0].Id -and $web.OwningProcess -eq $processes[1].Id) {
        Write-Output "http://127.0.0.1:4187/effectwitness/live-local"
        Write-Output "Run=$run"
        return
    }
    Start-Sleep -Milliseconds 300
} while ([DateTime]::UtcNow -lt $deadline)
throw 'Startup readiness not established. Use the identity-checked stop script.'

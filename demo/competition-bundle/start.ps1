#Requires -Version 7.2
[CmdletBinding()]
param([Parameter(Mandatory)][string]$PythonExe, [Parameter(Mandatory)][string]$NodeExe,
      [ValidatePattern('^[a-f0-9]{32}$')][string]$Reopen)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$local = Join-Path $root '.local'

function Confirm-Path([string]$Path) {
    for ($item = Get-Item -LiteralPath $Path -Force; $item; ) {
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Linked path.' }
        $parent = Split-Path -Parent $item.FullName
        $item = if ($parent) { Get-Item -LiteralPath $parent -Force }
    }
}

function Get-Binary([string]$Path, [string]$Name) {
    if (![IO.Path]::IsPathFullyQualified($Path)) { throw "Supply an absolute $Name path." }
    $file = Get-Item -LiteralPath $Path
    Confirm-Path $file.FullName
    if ($file.PSIsContainer -or $file.Name -ne $Name -or $file.FullName -match 'WindowsApps|PyManager') {
        throw "Unverified executable $Name."
    }
    $file.FullName
}

function Start-ServiceProcess([string]$Exe, [string[]]$Arguments) {
    $info = [Diagnostics.ProcessStartInfo]::new($Exe)
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.WorkingDirectory = $root
    $info.Environment.Clear()
    foreach ($name in 'SystemRoot','WINDIR','SystemDrive','ComSpec') {
        $value = [Environment]::GetEnvironmentVariable($name, 'Process')
        if ($value) { $info.Environment[$name] = $value }
    }
    $info.Environment['TMP'] = $run
    $info.Environment['TEMP'] = $run
    $info.Environment['RPF100_GATEWAY_TOKEN'] = $token
    if ($checkout) {
        $info.Environment['VITE_CONTROL_PLANE_DATA_SOURCE'] = 'fixture'
    }
    foreach ($argument in $Arguments) { $info.ArgumentList.Add($argument) }
    [Diagnostics.Process]::Start($info)
}

Confirm-Path $root
$manifestPath = Join-Path $root 'bundle-manifest.json'
$checkout = !(Test-Path -LiteralPath $manifestPath) -and (Test-Path -LiteralPath (Join-Path $root 'build-bundle.mjs'))
if ($checkout) {
    $root = (Get-Item -LiteralPath (Join-Path $root '../..')).FullName
    $local = Join-Path $root '.local/rpf-115'
    $agent = $true
    $vite = Join-Path $root 'node_modules/vite/bin/vite.js'
    Confirm-Path $vite
    foreach ($name in '.env','.env.local','.env.development','.env.development.local') {
        if (Test-Path -LiteralPath (Join-Path $root $name)) { throw 'Use a checkout without Vite environment files.' }
    }
} else {
    Confirm-Path $manifestPath
    $manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
    $agent = $manifest.schema -eq 'runproof-competition-complete/v1'
}
$gatewayModule = if ($agent) { 'competition_agent_gateway' } else { 'rpf112_competition_gateway' }
$page = if ($agent) { 'agent' } else { 'live-local' }
$PythonExe = Get-Binary $PythonExe 'python.exe'
$NodeExe = Get-Binary $NodeExe 'node.exe'
& $PythonExe -I -B -c 'import sys, sqlite3; assert sys.version_info >= (3,11)'
if ($LASTEXITCODE) { throw 'CPython 3.11+ with SQLite required.' }
& $NodeExe -e 'if (+process.versions.node.split(".")[0] < 22) process.exit(1)'
if ($LASTEXITCODE) { throw 'Node 22+ required.' }
if (Get-NetTCPConnection -State Listen -LocalPort 4187,8780 -ErrorAction SilentlyContinue) { throw 'Demo port occupied.' }
if ($Reopen -and !$agent) { throw 'Read-only investigation requires the reference Agent.' }
$nonce = if ($Reopen) { $Reopen } else { [guid]::NewGuid().ToString('N') }
if (!$agent -and (Test-Path -LiteralPath $local)) { throw 'This extraction already has local state.' }
if (!(Test-Path -LiteralPath $local)) { $null = New-Item -ItemType Directory -Path $local -Force }
Confirm-Path $local
$launch = Join-Path $local "launch/$nonce"
if (!(Test-Path -LiteralPath $launch)) { $null = New-Item -ItemType Directory -Path $launch -Force }
Confirm-Path $launch
$run = Join-Path $launch ([guid]::NewGuid().ToString('N'))
$null = New-Item -ItemType Directory -Path $run
$gatewayArgs = @('-E','-B','-m',("runtime.runproof_runtime.effectwitness." + $gatewayModule),'--nonce',$nonce)
if ($Reopen) { $gatewayArgs += '--readonly' }
$webArgs = if ($checkout) { @(Join-Path $PSScriptRoot 'checkout-server.mjs') }
           else { @(Join-Path $root 'competition-server.cjs') }
$token = [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32)).ToLowerInvariant()
$claim = [IO.File]::Open((Join-Path $run 'processes.json'), 'CreateNew', 'Write', 'None')
$processes = @()
$records = @()
try {
    foreach ($service in @(
        @{ exe = $PythonExe; args = $gatewayArgs },
        @{ exe = $NodeExe; args = @($webArgs) }
    )) {
        $process = Start-ServiceProcess $service.exe $service.args
        $processes += $process
        $records += @{ pid = $process.Id; exe = $service.exe; started = $process.StartTime.ToUniversalTime().Ticks.ToString() }
    }
} finally {
    try {
        $bytes = [Text.Encoding]::UTF8.GetBytes((ConvertTo-Json -InputObject @{ nonce = $nonce; records = $records } -Compress))
        $claim.Write($bytes, 0, $bytes.Length)
        $claim.Flush($true)
    } finally { $claim.Dispose() }
}
$deadline = [DateTime]::UtcNow.AddSeconds(50)
do {
    foreach ($process in $processes) {
        if ($process.HasExited) { throw "Service exited. Run stop.ps1 -Nonce $nonce." }
    }
    $gateway = Get-NetTCPConnection -State Listen -LocalAddress 127.0.0.1 -LocalPort 8780 -ErrorAction SilentlyContinue
    $web = Get-NetTCPConnection -State Listen -LocalAddress 127.0.0.1 -LocalPort 4187 -ErrorAction SilentlyContinue
    if ($gateway.OwningProcess -eq $processes[0].Id -and $web.OwningProcess -eq $processes[1].Id) {
        Write-Output "http://127.0.0.1:4187/effectwitness/$page"
        Write-Output "Nonce=$nonce"
        return
    }
    Start-Sleep -Milliseconds 250
} while ([DateTime]::UtcNow -lt $deadline)
throw "Readiness unconfirmed. Run stop.ps1 -Nonce $nonce."

[CmdletBinding()]
param(
    [switch]$RemoveData
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$LocalRoot = Join-Path $Root ".local\rpf-19\demo"
$StatePath = Join-Path $LocalRoot "demo-state.json"
$SecretPath = Join-Path $LocalRoot "demo-credentials.json"
$ArtifactRoot = Join-Path $LocalRoot "artifacts"

function Test-LocalProcessAlive {
    param([object]$ProcessId)
    if ($null -eq $ProcessId) { return $false }
    try {
        $process = Get-Process -Id ([int]$ProcessId) -ErrorAction Stop
        return -not $process.HasExited
    } catch {
        return $false
    }
}

if (-not (Test-Path -LiteralPath $StatePath)) {
    Write-Output "Golden Demo is already stopped; local credentials/artifacts are preserved."
    exit 0
}

$state = Get-Content -Raw -LiteralPath $StatePath | ConvertFrom-Json
foreach ($processId in @($state.web_pid, $state.control_plane_pid)) {
    if (Test-LocalProcessAlive $processId) {
        & taskkill.exe /PID ([int]$processId) /T /F 1>$null 2>$null
    }
}

$container = [string]$state.postgres_container
if ($container -and (Get-Command docker -ErrorAction SilentlyContinue)) {
    $containers = @(& docker ps -a --format "{{.Names}}" 2>$null)
    if ($containers -contains $container) { & docker stop $container 1>$null 2>$null }
}

Remove-Item -LiteralPath $StatePath -Force

if ($RemoveData) {
    $volume = [string]$state.postgres_volume
    if ($container -and (Get-Command docker -ErrorAction SilentlyContinue)) {
        & docker rm -f $container 1>$null 2>$null
    }
    if ($volume -and (Get-Command docker -ErrorAction SilentlyContinue)) {
        & docker volume rm $volume 1>$null 2>$null
    }
    if (Test-Path -LiteralPath $ArtifactRoot) { Remove-Item -LiteralPath $ArtifactRoot -Recurse -Force }
    if (Test-Path -LiteralPath $SecretPath) { Remove-Item -LiteralPath $SecretPath -Force }
    Write-Output "Golden Demo stopped and its exact demo container, volume, artifact store, and local credentials were removed."
} else {
    Write-Output "Golden Demo stopped. Named PostgreSQL volume, reviewed artifact copies, and local credentials were preserved for restart."
}

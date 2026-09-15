[CmdletBinding()]
param(
    [switch]$NoWeb
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$LocalRoot = Join-Path $Root ".local\rpf-19\demo"
$StatePath = Join-Path $LocalRoot "demo-state.json"
$SecretPath = Join-Path $LocalRoot "demo-credentials.json"
$ArtifactRoot = Join-Path $LocalRoot "artifacts"
$PgContainer = "rpf19-demo-postgres"
$PgVolume = "rpf19-demo-postgres-volume"
$PgPort = 55432
$ControlPlanePort = 8081
$WebPort = 4173

New-Item -ItemType Directory -Force -Path $LocalRoot, $ArtifactRoot | Out-Null

function Invoke-Checked {
    param([string]$File, [string[]]$ArgumentList)
    & $File @ArgumentList
    if ($LASTEXITCODE -ne 0) {
        throw "$File failed with exit code $LASTEXITCODE"
    }
}

function Test-ProcessAlive {
    param([object]$ProcessId)
    if ($null -eq $ProcessId) { return $false }
    try {
        $process = Get-Process -Id ([int]$ProcessId) -ErrorAction Stop
        return -not $process.HasExited
    } catch {
        return $false
    }
}

function Test-HttpReady {
    param([string]$Url)
    try {
        $response = Invoke-RestMethod -Uri $Url -TimeoutSec 3
        return $response.ready -eq $true -and $response.readiness -eq "READY"
    } catch {
        return $false
    }
}

function Test-WebReady {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$WebPort/" -TimeoutSec 3
        return $response.StatusCode -eq 200 -and $response.Content -match "RunProof"
    } catch {
        return $false
    }
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw "Docker CLI is required. Start Docker Desktop and retry." }
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw "Python is required." }
if (-not (Get-Command java -ErrorAction SilentlyContinue)) { throw "Java 17+ is required." }
if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) { throw "Node.js/npm is required." }

try {
    & docker info *> $null
    if ($LASTEXITCODE -ne 0) { throw "Docker daemon is unavailable. Start Docker Desktop and retry." }
} catch {
    throw "Docker daemon is unavailable. Start Docker Desktop and retry."
}

$localImages = @(& docker image ls --format "{{.Repository}}:{{.Tag}}" 2>$null)
if ($LASTEXITCODE -ne 0 -or $localImages -notcontains "postgres:16-alpine") {
    throw "postgres:16-alpine is not available locally. Pull/load the existing image, then retry; the demo does not create cloud resources."
}

if (Test-Path -LiteralPath $SecretPath) {
    $credentials = Get-Content -Raw -LiteralPath $SecretPath | ConvertFrom-Json
} else {
    $credentials = [ordered]@{
        db_password = [guid]::NewGuid().ToString("N")
        read = [guid]::NewGuid().ToString("N")
        evidence = [guid]::NewGuid().ToString("N")
        decision = [guid]::NewGuid().ToString("N")
        agent = [guid]::NewGuid().ToString("N")
        ci = [guid]::NewGuid().ToString("N")
        worker = [guid]::NewGuid().ToString("N")
    }
    $credentials | ConvertTo-Json | Set-Content -LiteralPath $SecretPath -Encoding utf8
}

$localVolumes = @(& docker volume ls --format "{{.Name}}" 2>$null)
if ($LASTEXITCODE -ne 0) { throw "Docker volume listing failed." }
if ($localVolumes -notcontains $PgVolume) {
    Invoke-Checked "docker" @("volume", "create", $PgVolume)
}

$localContainers = @(& docker ps -a --format "{{.Names}}" 2>$null)
if ($LASTEXITCODE -ne 0) { throw "Docker container listing failed." }
$containerExists = $localContainers -contains $PgContainer
if (-not $containerExists) {
    Invoke-Checked "docker" @(
        "run", "-d", "--name", $PgContainer,
        "-e", "POSTGRES_USER=runproof",
        "-e", ("POSTGRES_PASSWORD=" + $credentials.db_password),
        "-e", "POSTGRES_DB=runproof",
        "-p", ("127.0.0.1:{0}:5432" -f $PgPort),
        "--mount", ("type=volume,source={0},target=/var/lib/postgresql/data" -f $PgVolume),
        "postgres:16-alpine"
    ) | Out-Null
} else {
    $running = (& docker inspect -f "{{.State.Running}}" $PgContainer 2>$null).Trim()
    if ($running -ne "true") { Invoke-Checked "docker" @("start", $PgContainer) | Out-Null }
}

$pgDeadline = (Get-Date).AddSeconds(45)
do {
    $ready = (& docker exec $PgContainer pg_isready -U runproof -d runproof 2>$null)
    if ($LASTEXITCODE -eq 0) { break }
    Start-Sleep -Milliseconds 250
} while ((Get-Date) -lt $pgDeadline)
if ($LASTEXITCODE -ne 0) { throw "PostgreSQL did not become ready before the deadline." }

$jarPath = Join-Path $Root "control-plane\target\runproof-control-plane-0.1.0-SNAPSHOT.jar"
if (-not (Test-Path -LiteralPath $jarPath)) {
    Push-Location $Root
    try { Invoke-Checked "mvn.cmd" @("-q", "test", "package", "-f", "control-plane/pom.xml") } finally { Pop-Location }
}

$env:RPF_CONTROL_PLANE_ADDRESS = "127.0.0.1"
$env:RPF_CONTROL_PLANE_PORT = "$ControlPlanePort"
$env:RPF_JDBC_URL = "jdbc:postgresql://127.0.0.1:$PgPort/runproof"
$env:RPF_DB_USER = "runproof"
$env:RPF_DB_PASSWORD = "$($credentials.db_password)"
$env:RPF_ARTIFACT_STORE_ROOT = $ArtifactRoot
$env:RPF_PROBE_ENABLED = "true"
$env:RPF_AUTH_READ_TOKEN = "$($credentials.read)"
$env:RPF_AUTH_EVIDENCE_TOKEN = "$($credentials.evidence)"
$env:RPF_AUTH_DECISION_TOKEN = "$($credentials.decision)"
$env:RPF_AUTH_AGENT_TOKEN = "$($credentials.agent)"
$env:RPF_AUTH_CI_TOKEN = "$($credentials.ci)"
$env:RPF_AUTH_WORKER_TOKEN = "$($credentials.worker)"

$controlPlanePid = $null
$existingState = if (Test-Path -LiteralPath $StatePath) { Get-Content -Raw -LiteralPath $StatePath | ConvertFrom-Json } else { $null }
if ($existingState -and (Test-ProcessAlive $existingState.control_plane_pid) -and (Test-HttpReady "http://127.0.0.1:$ControlPlanePort/api/v1/health")) {
    $controlPlanePid = [int]$existingState.control_plane_pid
} else {
    $stdoutPath = Join-Path $LocalRoot "control-plane.stdout.log"
    $stderrPath = Join-Path $LocalRoot "control-plane.stderr.log"
    $controlPlane = Start-Process -FilePath "java" -ArgumentList @("-jar", $jarPath) -WorkingDirectory $Root -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath -PassThru
    $controlPlanePid = $controlPlane.Id
}

$healthDeadline = (Get-Date).AddSeconds(45)
while (-not (Test-HttpReady "http://127.0.0.1:$ControlPlanePort/api/v1/health")) {
    if ((Get-Date) -ge $healthDeadline) { throw "Control Plane did not become ready before the deadline." }
    Start-Sleep -Milliseconds 250
}

Push-Location $Root
try {
    & python demo/seed_demo.py --root $Root --base-url "http://127.0.0.1:$ControlPlanePort/api/v1" --artifact-store-root $ArtifactRoot --json
    if ($LASTEXITCODE -ne 0) { throw "Golden Demo seed failed." }
} finally { Pop-Location }

$webPid = $null
if (-not $NoWeb) {
    $env:VITE_CONTROL_PLANE_DATA_SOURCE = "api"
    $env:RPF_CONTROL_PLANE_PROXY_TARGET = "http://127.0.0.1:$ControlPlanePort"
    $env:RPF_CONTROL_PLANE_READ_TOKEN = "$($credentials.read)"
    if ($existingState -and (Test-ProcessAlive $existingState.web_pid) -and (Test-WebReady)) {
        $webPid = [int]$existingState.web_pid
    } else {
        $webLog = Join-Path $LocalRoot "web.stdout.log"
        $webError = Join-Path $LocalRoot "web.stderr.log"
        $web = Start-Process -FilePath "npm.cmd" -ArgumentList @("run", "dev", "--", "--host", "127.0.0.1", "--port", "$WebPort") -WorkingDirectory $Root -RedirectStandardOutput $webLog -RedirectStandardError $webError -PassThru
        $webPid = $web.Id
    }
    $webDeadline = (Get-Date).AddSeconds(30)
    while (-not (Test-WebReady)) {
        if ((Get-Date) -ge $webDeadline) { throw "Web did not become ready before the deadline." }
        Start-Sleep -Milliseconds 250
    }
}

$state = [ordered]@{
    schema_version = "rpf-19-demo-runtime-state-v1"
    control_plane_pid = $controlPlanePid
    web_pid = $webPid
    postgres_container = $PgContainer
    postgres_volume = $PgVolume
    postgres_port = $PgPort
    control_plane_url = "http://127.0.0.1:$ControlPlanePort"
    web_url = if ($NoWeb) { $null } else { "http://127.0.0.1:$WebPort/overview" }
    artifact_root = $ArtifactRoot
    started_at = (Get-Date).ToUniversalTime().ToString("o")
}
$state | ConvertTo-Json | Set-Content -LiteralPath $StatePath -Encoding utf8

Write-Output "Golden Demo ready."
Write-Output "Control Plane: http://127.0.0.1:$ControlPlanePort"
if (-not $NoWeb) { Write-Output "Web Overview: http://127.0.0.1:$WebPort/overview" }
Write-Output "Stop: powershell -ExecutionPolicy Bypass -File demo/stop-demo.ps1"

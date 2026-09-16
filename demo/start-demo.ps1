[CmdletBinding()]
param(
    [switch]$NoWeb,
    [ValidateSet("none", "control-plane", "seed", "web", "state-write")][string]$FailurePoint = "none",
    [string]$StateRoot,
    [string]$ContainerName,
    [string]$VolumeName,
    [ValidateRange(1024, 65535)][int]$PgPort = 55432,
    [ValidateRange(1024, 65535)][int]$ControlPlanePort = 8081,
    [ValidateRange(1024, 65535)][int]$WebPort = 4173
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "lifecycle.ps1")

# This script is itself the short-lived Demo supervisor.  Remove inherited
# credential variables from that supervisor before any child is created; the
# user shell is never modified because the documented entrypoint runs as a
# separate PowerShell process.
foreach ($secretName in $script:RpfDemoSecretEnvironmentNames) {
    if (Test-Path -LiteralPath "Env:$secretName") { Remove-Item -LiteralPath "Env:$secretName" -ErrorAction SilentlyContinue }
}

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$LocalRoot = if ([string]::IsNullOrWhiteSpace($StateRoot)) { Join-Path $Root ".local\rpf-19\demo" } else { Get-RunProofFullPath $StateRoot }
$StatePath = Join-Path $LocalRoot "demo-state.json"
$SecretPath = Join-Path $LocalRoot "demo-credentials.json"
$PostgresPasswordPath = Join-Path $LocalRoot "postgres-password"
$ArtifactRoot = Join-Path $LocalRoot "artifacts"
$PgContainer = if ([string]::IsNullOrWhiteSpace($ContainerName)) { "rpf19-demo-postgres" } else { $ContainerName }
$PgVolume = if ([string]::IsNullOrWhiteSpace($VolumeName)) { "rpf19-demo-postgres-volume" } else { $VolumeName }
$PgImage = "postgres:16-alpine"
$SessionId = [guid]::NewGuid().ToString("N")
$SessionMarker = "rpf-demo-session:$SessionId"
$StartedProcesses = @{}
$ContainerCreatedBySession = $false
$ContainerStartedBySession = $false
$VolumeCreatedBySession = $false
$ContainerRecord = $null
$VolumeRecord = $null
$State = $null

function Invoke-RunProofChecked {
    param([Parameter(Mandatory)][string]$FilePath, [Parameter(Mandatory)][string[]]$ArgumentList)
    & $FilePath @ArgumentList
    if ($LASTEXITCODE -ne 0) { throw "COMMAND_FAILED:$([System.IO.Path]::GetFileName($FilePath))" }
}

function Assert-RunProofManagedName {
    param([Parameter(Mandatory)][string]$Name, [Parameter(Mandatory)][string]$Kind)
    $pattern = if ($Kind -eq "container") { "^rpf19-demo-postgres$|^rpf23-test-[a-z0-9-]+$" } else { "^rpf19-demo-postgres-volume$|^rpf23-test-[a-z0-9-]+$" }
    if ($Name -notmatch $pattern) { throw "UNSAFE_${Kind}_NAME" }
}

function Test-RunProofHttpReady {
    param([Parameter(Mandatory)][string]$Url)
    try {
        $response = Invoke-RestMethod -Uri $Url -TimeoutSec 3
        return $response.ready -eq $true -and $response.readiness -eq "READY"
    } catch {
        return $false
    }
}

function Test-RunProofWebReady {
    param([Parameter(Mandatory)][int]$Port)
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/" -TimeoutSec 3
        return $response.StatusCode -eq 200 -and $response.Content -match "RunProof"
    } catch {
        return $false
    }
}

function Wait-RunProofHttpReady {
    param(
        [Parameter(Mandatory)][string]$Url,
        [Parameter(Mandatory)][System.Diagnostics.Process]$Process,
        [Parameter(Mandatory)][int]$TimeoutSeconds,
        [Parameter(Mandatory)][string]$Role
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while (-not (Test-RunProofHttpReady $Url)) {
        if ($Process.HasExited) { throw "PROCESS_EXITED_BEFORE_READY:$Role" }
        if ((Get-Date) -ge $deadline) { throw "PROCESS_READY_TIMEOUT:$Role" }
        Start-Sleep -Milliseconds 250
    }
}

function Wait-RunProofWebReady {
    param(
        [Parameter(Mandatory)][int]$Port,
        [Parameter(Mandatory)][System.Diagnostics.Process]$Process,
        [Parameter(Mandatory)][int]$TimeoutSeconds
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while (-not (Test-RunProofWebReady $Port)) {
        if ($Process.HasExited) { throw "PROCESS_EXITED_BEFORE_READY:web" }
        if ((Get-Date) -ge $deadline) { throw "PROCESS_READY_TIMEOUT:web" }
        Start-Sleep -Milliseconds 250
    }
}

function Invoke-RunProofFailurePoint {
    param([Parameter(Mandatory)][string]$Point)
    if ($FailurePoint -eq $Point) { throw "TEST_INJECTED_FAILURE:$Point" }
}

function New-RunProofVolumeRecord {
    param([Parameter(Mandatory)][string]$Name, [Parameter(Mandatory)][bool]$CreatedBySession)
    $inspect = Get-RunProofDockerInspect -Kind volume -Name $Name
    if ($null -eq $inspect) { return $null }
    $ownership = Get-RunProofResourceOwnership -Inspect $inspect -Kind volume
    if ($ownership -eq "FOREIGN") { throw "DOCKER_VOLUME_OWNERSHIP_INVALID:$Name" }
    return [ordered]@{
        name = $Name
        id = [string]$inspect.Name
        ownership = $ownership
        demo_owned = $ownership -eq "MANAGED"
        created_by_session = $CreatedBySession
        labels_verified = $ownership -eq "MANAGED"
    }
}

function Stop-RunProofContainerRecord {
    param([Parameter(Mandatory)][object]$Record)
    $inspect = Get-RunProofDockerInspect -Kind container -Name ([string]$Record.name)
    if ($null -eq $inspect) { return $true }
    if ([string]$inspect.Id -ne [string]$Record.id) { return $false }
    if (-not (Test-RunProofContainerConfig $inspect $PgImage ([string]$Record.volume) ([int]$Record.port))) { return $false }
    if ((Get-RunProofResourceOwnership -Inspect $inspect -Kind container -ExpectedImage $PgImage -ExpectedVolume ([string]$Record.volume) -ExpectedPort ([int]$Record.port)) -ne [string]$Record.ownership) { return $false }
    if ([bool]$inspect.State.Running) {
        & docker stop ([string]$Record.name) 1>$null 2>$null
        if ($LASTEXITCODE -ne 0) { return $false }
    }
    return $true
}

function New-RunProofState {
    param([Parameter(Mandatory)][string]$Status)
    return [ordered]@{
        schema_version = "rpf-23-demo-runtime-state-v2"
        demo_id = "rpf19-golden-demo"
        session_id = $SessionId
        status = $Status
        processes = [ordered]@{ control_plane = $null; web = $null }
        postgres = $ContainerRecord
        postgres_volume = $VolumeRecord
        artifact_root = Get-RunProofFullPath $ArtifactRoot
        secret_path = Get-RunProofFullPath $SecretPath
        postgres_password_path = Get-RunProofFullPath $PostgresPasswordPath
        control_plane_url = "http://127.0.0.1:$ControlPlanePort"
        web_url = if ($NoWeb) { $null } else { "http://127.0.0.1:$WebPort/overview" }
        ports = [ordered]@{ postgres = $PgPort; control_plane = $ControlPlanePort; web = if ($NoWeb) { $null } else { $WebPort } }
        started_at = (Get-Date).ToUniversalTime().ToString("o")
        stopped_at = $null
        cleanup_status = $null
        last_error_code = $null
    }
}

function Get-RunProofErrorCode {
    param([Parameter(Mandatory)][System.Management.Automation.ErrorRecord]$ErrorRecord)
    $message = [string]$ErrorRecord.Exception.Message
    if ($message -match "^[A-Z0-9_:-]+") { return $Matches[0] }
    return "START_FAILED"
}

function Invoke-RunProofRollback {
    $failures = @()
    foreach ($role in @("web", "control_plane")) {
        if ($StartedProcesses.ContainsKey($role)) {
            try {
                $outcome = Stop-RunProofVerifiedProcess -Record $StartedProcesses[$role].record
                if ($outcome.status -notin @("STOPPED", "ALREADY_EXITED")) { $failures += "PROCESS:${role}:$($outcome.status)" }
            } catch {
                $failures += "PROCESS:${role}:EXCEPTION:$([string]$_.Exception.Message)"
            }
        }
    }
    if ($null -ne $ContainerRecord -and $ContainerStartedBySession) {
        try {
            if ($ContainerCreatedBySession) {
                $removed = Remove-RunProofExactDockerContainer -Record $ContainerRecord -ExpectedImage $PgImage -ExpectedVolume $PgVolume -ExpectedPort $PgPort
                if (-not $removed.removed) { $failures += "CONTAINER:$($removed.status)" }
            } else {
                if (-not (Stop-RunProofContainerRecord -Record $ContainerRecord)) { $failures += "CONTAINER:STOP_FAILED" }
            }
        } catch {
            $failures += "CONTAINER:EXCEPTION:$([string]$_.Exception.Message)"
        }
    }
    return $failures
}

try {
    Assert-RunProofManagedName -Name $PgContainer -Kind container
    Assert-RunProofManagedName -Name $PgVolume -Kind volume
    if (-not (Test-RunProofPathWithin $LocalRoot (Join-Path $Root ".local"))) { throw "STATE_ROOT_OUTSIDE_LOCAL" }
    New-Item -ItemType Directory -Force -Path $LocalRoot, $ArtifactRoot | Out-Null

    foreach ($command in @("docker", "python", "java", "npm.cmd", "mvn.cmd")) {
        if (-not (Get-Command $command -ErrorAction SilentlyContinue)) { throw "REQUIRED_COMMAND_MISSING:$command" }
    }
    & docker info *> $null
    if ($LASTEXITCODE -ne 0) { throw "DOCKER_DAEMON_UNAVAILABLE" }
    $localImages = @(& docker image ls --format "{{.Repository}}:{{.Tag}}" 2>$null)
    if ($LASTEXITCODE -ne 0 -or $localImages -notcontains $PgImage) { throw "POSTGRES_IMAGE_MISSING" }

    $stateResult = Read-RunProofState -Path $StatePath
    if ($stateResult.status -in @("MALFORMED", "UNSUPPORTED")) {
        $null = Move-RunProofStateToArchive -Path $StatePath
        $stateResult = [pscustomobject]@{ status = "MISSING"; state = $null; reason = $null }
    }
    $priorState = $stateResult.state
    if ($stateResult.status -eq "VALID" -and [string]$priorState.status -eq "READY") {
        $containerHealthy = $null -ne $priorState.postgres -and (Test-RunProofContainerRecord -Record $priorState.postgres -ExpectedImage $PgImage -ExpectedVolume ([string]$priorState.postgres.volume) -ExpectedPort ([int]$priorState.postgres.port))
        $controlIdentityHealthy = $null -ne $priorState.processes.control_plane -and (Test-RunProofProcessIdentity -Record $priorState.processes.control_plane)
        $controlReadyHealthy = Test-RunProofHttpReady -Url ("$([string]$priorState.control_plane_url)/api/v1/health")
        $controlHealthy = $controlIdentityHealthy -and $controlReadyHealthy
        $webIdentityHealthy = $null -ne $priorState.processes.web -and (Test-RunProofProcessIdentity -Record $priorState.processes.web)
        $webReadyHealthy = Test-RunProofWebReady -Port ([int]$priorState.ports.web)
        $webHealthy = $NoWeb -or ($webIdentityHealthy -and $webReadyHealthy)
        Write-Verbose "Existing state checks: container=$containerHealthy control=$controlHealthy (identity=$controlIdentityHealthy ready=$controlReadyHealthy) web=$webHealthy (identity=$webIdentityHealthy ready=$webReadyHealthy) state=$($stateResult.status)"
        if ($containerHealthy -and $controlHealthy -and $webHealthy) {
            Write-Output "Golden Demo is already ready; verified session $([string]$priorState.session_id) was reused."
            if (-not $NoWeb) { Write-Output "Web Overview: $([string]$priorState.web_url)" }
            exit 0
        }
    }
    if ((Test-RunProofTcpPortOpen -Port $ControlPlanePort) -or ((-not $NoWeb) -and (Test-RunProofTcpPortOpen -Port $WebPort))) {
        throw "PORT_OCCUPIED_BY_UNVERIFIED_PROCESS"
    }

    $buildLog = Join-Path $LocalRoot "maven.stdout.log"
    $buildEnv = New-RunProofChildEnvironment -Role build -Values @{ RPF_DEMO_SESSION_ID = $SessionId }
    $maven = Start-RunProofManagedProcess -FilePath "mvn.cmd" -ArgumentList @("-q", "test", "package", "-f", "control-plane/pom.xml") -WorkingDirectory $Root -Environment $buildEnv -StdOutPath $buildLog -StdErrPath $buildLog -SessionMarker $SessionMarker
    if ((Wait-RunProofProcessExit -Process $maven -TimeoutSeconds 300 -Role "maven") -ne 0) { throw "BUILD_FAILED" }

    $credentialResult = Get-RunProofCredentials -Path $SecretPath -LocalRoot $LocalRoot
    $credentials = $credentialResult.values
    if (-not (Test-Path -LiteralPath $PostgresPasswordPath)) {
        $utf8 = [System.Text.UTF8Encoding]::new($false)
        [System.IO.File]::WriteAllText((Get-RunProofFullPath $PostgresPasswordPath), [string]$credentials.db_password, $utf8)
        $null = Set-RunProofPrivateFileAcl -Path $PostgresPasswordPath
    }

    $volumeInspect = Get-RunProofDockerInspect -Kind volume -Name $PgVolume
    if ($null -eq $volumeInspect) {
        & docker volume create --label "com.runproof.owner=$script:RpfDemoOwnerLabel" --label "com.runproof.demo=$script:RpfDemoIdentity" --label "com.runproof.lifecycle=$script:RpfDemoLifecycleLabel" $PgVolume 1>$null
        if ($LASTEXITCODE -ne 0) { throw "DOCKER_VOLUME_CREATE_FAILED" }
        $VolumeCreatedBySession = $true
    }
    $VolumeRecord = New-RunProofVolumeRecord -Name $PgVolume -CreatedBySession $VolumeCreatedBySession
    if ($null -eq $VolumeRecord) { throw "DOCKER_VOLUME_MISSING_AFTER_CREATE" }

    $containerInspect = Get-RunProofDockerInspect -Kind container -Name $PgContainer
    if ($null -eq $containerInspect) {
        if (Test-RunProofTcpPortOpen -Port $PgPort) { throw "POSTGRES_PORT_OCCUPIED_BY_UNVERIFIED_PROCESS" }
        & docker run -d --name $PgContainer --label "com.runproof.owner=$script:RpfDemoOwnerLabel" --label "com.runproof.demo=$script:RpfDemoIdentity" --label "com.runproof.lifecycle=$script:RpfDemoLifecycleLabel" -e "POSTGRES_USER=runproof" -e "POSTGRES_DB=runproof" -e "POSTGRES_PASSWORD_FILE=/run/secrets/rpf-postgres-password" -p "127.0.0.1:${PgPort}:5432" --mount "type=volume,source=$PgVolume,target=/var/lib/postgresql/data" --mount "type=bind,source=$(Get-RunProofFullPath $PostgresPasswordPath),target=/run/secrets/rpf-postgres-password,readonly" $PgImage 1>$null
        if ($LASTEXITCODE -ne 0) { throw "DOCKER_CONTAINER_CREATE_FAILED" }
        $ContainerCreatedBySession = $true
        $ContainerStartedBySession = $true
    } else {
        $existingOwnership = Get-RunProofResourceOwnership -Inspect $containerInspect -Kind container -ExpectedImage $PgImage -ExpectedVolume $PgVolume -ExpectedPort $PgPort
        if ($existingOwnership -eq "FOREIGN") { throw "DOCKER_CONTAINER_OWNERSHIP_INVALID:$PgContainer" }
        if ([bool]$containerInspect.State.Running) {
            $ContainerStartedBySession = $false
        } else {
            & docker start $PgContainer 1>$null 2>$null
            if ($LASTEXITCODE -ne 0) { throw "DOCKER_CONTAINER_START_FAILED" }
            $ContainerStartedBySession = $true
        }
    }
    $ContainerRecord = Get-RunProofContainerRecord -Name $PgContainer -VolumeName $PgVolume -ExpectedImage $PgImage -ExpectedPort $PgPort -CreatedBySession $ContainerCreatedBySession -StartedBySession $ContainerStartedBySession
    if ($null -eq $ContainerRecord) { throw "DOCKER_CONTAINER_MISSING_AFTER_START" }

    $State = New-RunProofState -Status "STARTING"
    Write-RunProofStateAtomic -Path $StatePath -State $State

    $pgDeadline = (Get-Date).AddSeconds(45)
    do {
        & docker exec $PgContainer pg_isready -U runproof -d runproof 1>$null 2>$null
        $pgReady = $LASTEXITCODE -eq 0
        if ($pgReady) { break }
        Start-Sleep -Milliseconds 250
    } while ((Get-Date) -lt $pgDeadline)
    if (-not $pgReady) { throw "POSTGRES_READY_TIMEOUT" }

    $jarPath = Join-Path $Root "control-plane\target\runproof-control-plane-0.1.0-SNAPSHOT.jar"
    if (-not (Test-Path -LiteralPath $jarPath)) { throw "CONTROL_PLANE_JAR_MISSING_AFTER_BUILD" }
    $controlValues = @{
        RPF_DEMO_SESSION_ID = $SessionId; RPF_CONTROL_PLANE_ADDRESS = "127.0.0.1"; RPF_CONTROL_PLANE_PORT = "$ControlPlanePort"; RPF_JDBC_URL = "jdbc:postgresql://127.0.0.1:$PgPort/runproof"; RPF_DB_USER = "runproof"; RPF_DB_PASSWORD = [string]$credentials.db_password; RPF_ARTIFACT_STORE_ROOT = Get-RunProofFullPath $ArtifactRoot; RPF_PROBE_ENABLED = "true"; RPF_AUTH_READ_TOKEN = [string]$credentials.read; RPF_AUTH_EVIDENCE_TOKEN = [string]$credentials.evidence; RPF_AUTH_DECISION_TOKEN = [string]$credentials.decision; RPF_AUTH_AGENT_TOKEN = [string]$credentials.agent; RPF_AUTH_CI_TOKEN = [string]$credentials.ci; RPF_AUTH_WORKER_TOKEN = [string]$credentials.worker
    }
    $controlEnv = New-RunProofChildEnvironment -Role control-plane -Values $controlValues
    $controlLog = Join-Path $LocalRoot "control-plane.stdout.log"
    $controlProcess = Start-RunProofManagedProcess -FilePath "java" -ArgumentList @("-Drpf.demo.session-marker=$SessionMarker", "-jar", $jarPath) -WorkingDirectory $Root -Environment $controlEnv -StdOutPath $controlLog -StdErrPath $controlLog -SessionMarker $SessionMarker
    $controlRecord = New-RunProofProcessRecord -Process $controlProcess -Role "control-plane" -SessionMarker $SessionMarker -ExpectedPort $ControlPlanePort
    $StartedProcesses["control_plane"] = [ordered]@{ process = $controlProcess; record = $controlRecord }
    $State.processes.control_plane = $controlRecord
    Write-RunProofStateAtomic -Path $StatePath -State $State
    Wait-RunProofHttpReady -Url "http://127.0.0.1:$ControlPlanePort/api/v1/health" -Process $controlProcess -TimeoutSeconds 45 -Role "control-plane"
    Invoke-RunProofFailurePoint -Point "control-plane"

    $seedValues = @{ RPF_DEMO_SESSION_ID = $SessionId; RPF_CONTROL_PLANE_URL = "http://127.0.0.1:$ControlPlanePort/api/v1"; RPF_AUTH_READ_TOKEN = [string]$credentials.read; RPF_AUTH_EVIDENCE_TOKEN = [string]$credentials.evidence; RPF_AUTH_DECISION_TOKEN = [string]$credentials.decision }
    $seedEnv = New-RunProofChildEnvironment -Role seed -Values $seedValues
    $seedLog = Join-Path $LocalRoot "seed.stdout.log"
    $pythonPath = (Get-Command python -ErrorAction Stop).Source
    $seedProcess = Start-RunProofManagedProcess -FilePath $pythonPath -ArgumentList @("demo/seed_demo.py", "--root", $Root, "--base-url", "http://127.0.0.1:$ControlPlanePort/api/v1", "--artifact-store-root", $ArtifactRoot, "--json") -WorkingDirectory $Root -Environment $seedEnv -StdOutPath $seedLog -StdErrPath $seedLog -SessionMarker $SessionMarker
    if ((Wait-RunProofProcessExit -Process $seedProcess -TimeoutSeconds 120 -Role "seed") -ne 0) { throw "SEED_FAILED" }
    Invoke-RunProofFailurePoint -Point "seed"

    if (-not $NoWeb) {
        $webValues = @{ RPF_DEMO_SESSION_ID = $SessionId; VITE_CONTROL_PLANE_DATA_SOURCE = "api"; RPF_CONTROL_PLANE_PROXY_TARGET = "http://127.0.0.1:$ControlPlanePort"; RPF_CONTROL_PLANE_READ_TOKEN = [string]$credentials.read }
        $webEnv = New-RunProofChildEnvironment -Role web -Values $webValues
        $webLog = Join-Path $LocalRoot "web.stdout.log"
        $webProcess = Start-RunProofManagedProcess -FilePath "npm.cmd" -ArgumentList @("run", "dev", "--", "--host", "127.0.0.1", "--port", "$WebPort") -WorkingDirectory $Root -Environment $webEnv -StdOutPath $webLog -StdErrPath $webLog -SessionMarker $SessionMarker
        $webRecord = New-RunProofProcessRecord -Process $webProcess -Role "web" -SessionMarker $SessionMarker -ExpectedPort $WebPort
        $StartedProcesses["web"] = [ordered]@{ process = $webProcess; record = $webRecord }
        $State.processes.web = $webRecord
        Write-RunProofStateAtomic -Path $StatePath -State $State
        Invoke-RunProofFailurePoint -Point "web"
        Wait-RunProofWebReady -Port $WebPort -Process $webProcess -TimeoutSeconds 30
    }

    Invoke-RunProofFailurePoint -Point "state-write"
    $State.status = "READY"
    $State.started_at = (Get-Date).ToUniversalTime().ToString("o")
    $State.last_error_code = $null
    Write-RunProofStateAtomic -Path $StatePath -State $State

    Write-Output "Golden Demo ready."
    Write-Output "Session: $SessionId"
    Write-Output "Control Plane: http://127.0.0.1:$ControlPlanePort"
    if (-not $NoWeb) { Write-Output "Web Overview: http://127.0.0.1:$WebPort/overview" }
    Write-Output "Stop: powershell -ExecutionPolicy Bypass -File demo/stop-demo.ps1"
} catch {
    $errorCode = Get-RunProofErrorCode -ErrorRecord $_
    $rollbackFailures = @()
    try { $rollbackFailures = @(Invoke-RunProofRollback) } catch { $rollbackFailures += "ROLLBACK_EXCEPTION" }
    if ($null -ne $State) {
        $State.processes.control_plane = $null
        $State.processes.web = $null
        $State.status = if ($rollbackFailures.Count -eq 0) { "STOPPED" } else { "RECOVERY_REQUIRED" }
        $State.stopped_at = (Get-Date).ToUniversalTime().ToString("o")
        $State.cleanup_status = if ($rollbackFailures.Count -eq 0) { "ROLLBACK_COMPLETE" } else { ($rollbackFailures -join ",") }
        $State.last_error_code = $errorCode
        try { Write-RunProofStateAtomic -Path $StatePath -State $State } catch { }
    }
    Write-Error "Golden Demo start failed: $errorCode. No unverified process or Docker resource was removed; inspect logs under $LocalRoot."
    exit 1
}

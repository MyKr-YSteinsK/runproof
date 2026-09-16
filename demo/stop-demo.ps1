[CmdletBinding()]
param(
    [switch]$RemoveData,
    [string]$StateRoot
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "lifecycle.ps1")
foreach ($secretName in $script:RpfDemoSecretEnvironmentNames) {
    if (Test-Path -LiteralPath "Env:$secretName") { Remove-Item -LiteralPath "Env:$secretName" -ErrorAction SilentlyContinue }
}

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$LocalRoot = if ([string]::IsNullOrWhiteSpace($StateRoot)) { Join-Path $Root ".local\rpf-19\demo" } else { Get-RunProofFullPath $StateRoot }
$StatePath = Join-Path $LocalRoot "demo-state.json"
$ArtifactRoot = Join-Path $LocalRoot "artifacts"
$SecretPath = Join-Path $LocalRoot "demo-credentials.json"
$PostgresPasswordPath = Join-Path $LocalRoot "postgres-password"

function Stop-RunProofContainerFromState {
    param([Parameter(Mandatory)][object]$Record)
    $inspect = Get-RunProofDockerInspect -Kind container -Name ([string]$Record.name)
    if ($null -eq $inspect) { return [pscustomobject]@{ status = "ALREADY_REMOVED"; safe = $true } }
    if ([string]$inspect.Id -ne [string]$Record.id) { return [pscustomobject]@{ status = "SKIPPED_IDENTITY_MISMATCH"; safe = $false } }
    if (-not (Test-RunProofContainerConfig $inspect "postgres:16-alpine" ([string]$Record.volume) ([int]$Record.port))) { return [pscustomobject]@{ status = "SKIPPED_CONFIG_MISMATCH"; safe = $false } }
    if ((Get-RunProofResourceOwnership -Inspect $inspect -Kind container -ExpectedImage "postgres:16-alpine" -ExpectedVolume ([string]$Record.volume) -ExpectedPort ([int]$Record.port)) -ne [string]$Record.ownership) { return [pscustomobject]@{ status = "SKIPPED_OWNERSHIP_MISMATCH"; safe = $false } }
    if ([bool]$inspect.State.Running -and [bool]$Record.started_by_session) {
        & docker stop ([string]$Record.name) 1>$null 2>$null
        if ($LASTEXITCODE -ne 0) { return [pscustomobject]@{ status = "STOP_FAILED"; safe = $false } }
    }
    return [pscustomobject]@{ status = if ([bool]$Record.started_by_session) { "STOPPED_OR_PRESERVED" } else { "PREEXISTING_PRESERVED" }; safe = $true }
}

function Update-RunProofStoppedState {
    param([Parameter(Mandatory)][object]$State, [Parameter(Mandatory)][string]$Status, [string]$CleanupStatus)
    $State.status = $Status
    $State.processes.control_plane = $null
    $State.processes.web = $null
    $State.stopped_at = (Get-Date).ToUniversalTime().ToString("o")
    $State.cleanup_status = $CleanupStatus
    Write-RunProofStateAtomic -Path $StatePath -State $State
}

try {
    if (-not (Test-RunProofPathWithin $LocalRoot (Join-Path $Root ".local"))) { throw "STATE_ROOT_OUTSIDE_LOCAL" }
    $stateResult = Read-RunProofState -Path $StatePath
    if ($stateResult.status -eq "MISSING") {
        if ($RemoveData) {
            Write-Error "No verified Demo state exists; RemoveData refused and no process, container, volume, artifact, or credential was deleted."
            exit 1
        }
        Write-Output "Golden Demo is already stopped; no verified state exists and local credentials/artifacts are preserved."
        exit 0
    }
    if ($stateResult.status -ne "VALID") {
        Write-Error "Demo state is $($stateResult.status) ($($stateResult.reason)); no destructive action was taken. Review or archive the state manually before retrying."
        exit 1
    }
    $state = $stateResult.state
    if ([string]$state.artifact_root -ne (Get-RunProofFullPath $ArtifactRoot) -or [string]$state.secret_path -ne (Get-RunProofFullPath $SecretPath)) {
        throw "STATE_TARGET_BOUNDARY_INVALID"
    }

    $identityFailure = $false
    foreach ($role in @("web", "control_plane")) {
        $record = $state.processes.$role
        if ($null -eq $record) { continue }
        $outcome = Stop-RunProofVerifiedProcess -Record $record
        if ($outcome.status -eq "SKIPPED_IDENTITY_MISMATCH") {
            $identityFailure = $true
            Write-Error "Process $role PID $($record.pid) did not match its recorded start time, executable, command fingerprint, and session marker; it was not killed."
        } elseif ($outcome.status -eq "STOP_FAILED") {
            $identityFailure = $true
            Write-Error "Process $role PID $($record.pid) could not be stopped after verified identity; no Docker or data cleanup was attempted."
        }
    }
    if ($identityFailure) { exit 1 }

    $container = $state.postgres
    if ($null -eq $container -or $null -eq $container.name -or $null -eq $container.id) { throw "STATE_CONTAINER_IDENTITY_MISSING" }
    $containerResult = Stop-RunProofContainerFromState -Record $container
    if (-not $containerResult.safe) {
        Write-Error "PostgreSQL container identity/config did not match state; it was not stopped or removed."
        exit 1
    }

    if (-not $RemoveData) {
        $containerAfterStop = Get-RunProofDockerInspect -Kind container -Name ([string]$container.name)
        if ($null -ne $containerAfterStop) { $container.running = [bool]$containerAfterStop.State.Running }
        Update-RunProofStoppedState -State $state -Status "STOPPED" -CleanupStatus "RUNTIME_STOPPED_DATA_PRESERVED"
        Write-Output "Golden Demo stopped. Named PostgreSQL volume, reviewed artifact copies, and local credentials were preserved for restart."
        exit 0
    }

    if ([string]$container.ownership -ne "MANAGED" -or [bool]$container.demo_owned -ne $true) {
        Update-RunProofStoppedState -State $state -Status "STOPPED" -CleanupStatus "DATA_REMOVAL_REFUSED_UNLABELLED_CONTAINER"
        Write-Error "RemoveData refused: the exact PostgreSQL container is legacy/unlabelled, so ownership is not strong enough for destructive removal. Runtime was stopped where verified; data and credentials were preserved."
        exit 1
    }
    $removedContainer = Remove-RunProofExactDockerContainer -Record $container -ExpectedImage "postgres:16-alpine" -ExpectedVolume ([string]$container.volume) -ExpectedPort ([int]$container.port)
    if (-not $removedContainer.removed) {
        Update-RunProofStoppedState -State $state -Status "RECOVERY_REQUIRED" -CleanupStatus "CONTAINER_$($removedContainer.status)"
        Write-Error "RemoveData could not remove the verified Demo container: $($removedContainer.status)."
        exit 1
    }

    $volume = $state.postgres_volume
    if ($null -eq $volume -or [string]$volume.name -ne [string]$container.volume) { throw "STATE_VOLUME_IDENTITY_MISSING" }
    $removedVolume = Remove-RunProofExactDockerVolume -Record $volume
    if (-not $removedVolume.removed) {
        Update-RunProofStoppedState -State $state -Status "RECOVERY_REQUIRED" -CleanupStatus "VOLUME_$($removedVolume.status)"
        Write-Error "RemoveData removed no further data because the Demo volume was not verified: $($removedVolume.status)."
        exit 1
    }

    foreach ($path in @($ArtifactRoot, $SecretPath, $PostgresPasswordPath)) {
        if (-not (Test-RunProofPathWithin $path $LocalRoot)) { throw "DATA_TARGET_BOUNDARY_INVALID" }
    }
    if (Test-Path -LiteralPath $ArtifactRoot) { Remove-Item -LiteralPath $ArtifactRoot -Recurse -Force }
    if (Test-Path -LiteralPath $SecretPath) { Remove-Item -LiteralPath $SecretPath -Force }
    if (Test-Path -LiteralPath $PostgresPasswordPath) { Remove-Item -LiteralPath $PostgresPasswordPath -Force }
    Remove-Item -LiteralPath $StatePath -Force
    Write-Output "Golden Demo stopped and its exact label-verified Demo container, volume, artifact store, credential file, and database password file were removed."
} catch {
    $message = [string]$_.Exception.Message
    $code = if ($message -match "^[A-Z0-9_:-]+") { $Matches[0] } else { "STOP_FAILED" }
    Write-Error "Golden Demo stop failed closed: $code. No unverified destructive action was taken."
    exit 1
}

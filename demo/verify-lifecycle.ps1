[CmdletBinding()]
param(
    [ValidateSet("all", "contracts", "lifecycle")][string]$Mode = "all"
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "lifecycle.ps1")

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ProbeId = [guid]::NewGuid().ToString("N")
$ProbeRoot = Join-Path $Root ".local\rpf23-$($ProbeId.Substring(0, 8))"
$Results = [ordered]@{}
$CreatedContainers = @()
$CreatedVolumes = @()
$ProcessRecords = @()

function Assert-Probe {
    param([Parameter(Mandatory)][bool]$Condition, [Parameter(Mandatory)][string]$Name)
    if (-not $Condition) { throw "PROBE_FAILED:$Name" }
    $Results[$Name] = $true
}

function Invoke-ChildEnvironmentDump {
    param(
        [Parameter(Mandatory)][string]$Role,
        [Parameter(Mandatory)][hashtable]$Environment,
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$SessionMarker
    )
    $python = (Get-Command python -ErrorAction Stop).Source
    $process = Start-RunProofManagedProcess -FilePath $python -ArgumentList @("demo/dump_child_environment.py", $Path) -WorkingDirectory $Root -Environment $Environment -StdOutPath "$Path.stdout.log" -StdErrPath "$Path.stderr.log" -SessionMarker $SessionMarker
    $exitCode = Wait-RunProofProcessExit -Process $process -TimeoutSeconds 30 -Role "env-$Role"
    Assert-Probe ($exitCode -eq 0 -and (Test-Path -LiteralPath $Path)) "child_env_dump_$Role"
    return Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json
}

function Invoke-DemoScript {
    param([Parameter(Mandatory)][string]$Script, [Parameter(Mandatory)][string[]]$Arguments)
    $powershell = (Get-Command powershell.exe -ErrorAction Stop).Source
    Write-Verbose "invoke demo script: $([System.IO.Path]::GetFileName($Script)) $($Arguments -join ' ')"
    $runId = [guid]::NewGuid().ToString("N")
    $stdoutPath = Join-Path $ProbeRoot "demo-$runId.stdout.log"
    $stderrPath = Join-Path $ProbeRoot "demo-$runId.stderr.log"
    $argumentParts = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $Script) + $Arguments
    $argumentLine = ($argumentParts | ForEach-Object { ConvertTo-RunProofCmdArgument ([string]$_) }) -join " "
    $process = Start-Process -FilePath $powershell -ArgumentList $argumentLine -WorkingDirectory $Root -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath -WindowStyle Hidden -PassThru
    $completed = $process.WaitForExit(180000)
    if (-not $completed) {
        & taskkill.exe /PID $process.Id /T /F 1>$null 2>$null
        $exitCode = 124
        Write-Verbose "demo script timed out and was terminated: $([System.IO.Path]::GetFileName($Script))"
    } else {
        $process.Refresh()
        $exitCode = [int]$process.ExitCode
    }
    $raw = @()
    if (Test-Path -LiteralPath $stdoutPath) { $raw += @(Get-Content -Raw -LiteralPath $stdoutPath -ErrorAction SilentlyContinue) }
    if (Test-Path -LiteralPath $stderrPath) { $raw += @(Get-Content -Raw -LiteralPath $stderrPath -ErrorAction SilentlyContinue) }
    # Windows PowerShell 5.1 can expose a blank ExitCode on a redirected
    # powershell.exe Process object after WaitForExit.  The demo scripts emit a
    # stable failure marker, so fail closed instead of treating that case as 0.
    $combinedOutput = ($raw | ForEach-Object { [string]$_ }) -join "`n"
    if ($exitCode -eq 0 -and $combinedOutput -match "(?i)(Golden Demo (start|stop) failed:|did not match its recorded|could not be stopped|stop failed closed:)") { $exitCode = 1 }
    Write-Verbose "demo script process result: hasExited=$($process.HasExited) processExit=$($process.ExitCode) normalizedExit=$exitCode"
    Write-Verbose "demo script returned: $([System.IO.Path]::GetFileName($Script)) exit=$exitCode"
    return [pscustomobject]@{ exit_code = $exitCode; output = $combinedOutput }
}

function New-DemoArguments {
    param(
        [Parameter(Mandatory)][string]$StateRoot,
        [Parameter(Mandatory)][string]$ContainerName,
        [Parameter(Mandatory)][string]$VolumeName,
        [Parameter(Mandatory)][int]$PgPort,
        [Parameter(Mandatory)][int]$ControlPlanePort,
        [Parameter(Mandatory)][int]$WebPort,
        [switch]$NoWeb,
        [string]$FailurePoint
    )
    $arguments = @("-StateRoot", $StateRoot, "-ContainerName", $ContainerName, "-VolumeName", $VolumeName, "-PgPort", "$PgPort", "-ControlPlanePort", "$ControlPlanePort", "-WebPort", "$WebPort")
    if ($NoWeb) { $arguments += "-NoWeb" }
    if (-not [string]::IsNullOrWhiteSpace($FailurePoint)) { $arguments += @("-FailurePoint", $FailurePoint) }
    return $arguments
}

function Read-ProbeState {
    param([Parameter(Mandatory)][string]$StateRoot)
    $result = Read-RunProofState -Path (Join-Path $StateRoot "demo-state.json")
    Assert-Probe ($result.status -eq "VALID") "state_valid_$([System.IO.Path]::GetFileName($StateRoot))"
    return $result.state
}

function Assert-ProbeNoSessionProcesses {
    param([Parameter(Mandatory)][object]$State, [Parameter(Mandatory)][string]$Name)
    Assert-Probe ($null -eq $State.processes.control_plane -and $null -eq $State.processes.web) "${Name}_state_has_no_children"
    Assert-Probe (-not (Test-RunProofTcpPortOpen -Port ([int]$State.ports.control_plane))) "${Name}_control_port_closed"
    if ($null -ne $State.ports.web) { Assert-Probe (-not (Test-RunProofTcpPortOpen -Port ([int]$State.ports.web))) "${Name}_web_port_closed" }
    $marker = "rpf-demo-session:$([string]$State.session_id)"
    $live = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { [string]$_.CommandLine -like "*$marker*" })
    Assert-Probe ($live.Count -eq 0) "${Name}_no_orphaned_session_process"
}

function Invoke-ContainerCreate {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string]$Volume,
        [Parameter(Mandatory)][int]$Port,
        [Parameter(Mandatory)][hashtable]$Labels
    )
    $arguments = @("create", "--name", $Name)
    foreach ($entry in $Labels.GetEnumerator()) { $arguments += @("--label", "$($entry.Key)=$($entry.Value)") }
    $arguments += @("-e", "POSTGRES_USER=runproof", "-e", "POSTGRES_DB=runproof", "-e", "POSTGRES_PASSWORD_FILE=/run/secrets/probe", "-p", "127.0.0.1:${Port}:5432", "--mount", "type=volume,source=$Volume,target=/var/lib/postgresql/data", "postgres:16-alpine")
    & docker @arguments 1>$null 2>$null
    if ($LASTEXITCODE -ne 0) { throw "PROBE_DOCKER_CREATE_FAILED:$Name" }
}

try {
    New-Item -ItemType Directory -Force -Path $ProbeRoot | Out-Null

    if ($Mode -in @("all", "contracts")) {
        $session = [guid]::NewGuid().ToString("N")
        $dummy = @{
            RPF_DEMO_SESSION_ID = $session
            RPF_CONTROL_PLANE_ADDRESS = "127.0.0.1"
            RPF_CONTROL_PLANE_PORT = "18081"
            RPF_JDBC_URL = "jdbc:postgresql://127.0.0.1:15532/runproof"
            RPF_DB_USER = "runproof"
            RPF_DB_PASSWORD = "dummy-db-password"
            RPF_ARTIFACT_STORE_ROOT = (Join-Path $ProbeRoot "artifacts")
            RPF_PROBE_ENABLED = "true"
            RPF_AUTH_READ_TOKEN = "dummy-read-token"
            RPF_AUTH_EVIDENCE_TOKEN = "dummy-evidence-token"
            RPF_AUTH_DECISION_TOKEN = "dummy-decision-token"
            RPF_AUTH_AGENT_TOKEN = "dummy-agent-token"
            RPF_AUTH_CI_TOKEN = "dummy-ci-token"
            RPF_AUTH_WORKER_TOKEN = "dummy-worker-token"
        }
        $beforeParent = @{}
        foreach ($name in $script:RpfDemoSecretEnvironmentNames) { $beforeParent[$name] = [System.Environment]::GetEnvironmentVariable($name, "Process") }
        $webEnvironment = New-RunProofChildEnvironment -Role web -Values @{ RPF_DEMO_SESSION_ID = $session; VITE_CONTROL_PLANE_DATA_SOURCE = "api"; RPF_CONTROL_PLANE_PROXY_TARGET = "http://127.0.0.1:18081"; RPF_CONTROL_PLANE_READ_TOKEN = "dummy-read-token" }
        $workerEnvironment = New-RunProofChildEnvironment -Role worker -Values @{ RPF_DEMO_SESSION_ID = $session; RPF_CONTROL_PLANE_URL = "http://127.0.0.1:18081/api/v1"; RPF_AUTH_WORKER_TOKEN = "dummy-worker-token"; RPF_REPO_ROOT = $Root; RPF_ARTIFACT_STORE_ROOT = (Join-Path $ProbeRoot "artifacts"); RPF_WORKER_IO_ROOT = $ProbeRoot }
        $seedEnvironment = New-RunProofChildEnvironment -Role seed -Values @{ RPF_DEMO_SESSION_ID = $session; RPF_CONTROL_PLANE_URL = "http://127.0.0.1:18081/api/v1"; RPF_AUTH_READ_TOKEN = "dummy-read-token"; RPF_AUTH_EVIDENCE_TOKEN = "dummy-evidence-token"; RPF_AUTH_DECISION_TOKEN = "dummy-decision-token" }
        $webDump = Invoke-ChildEnvironmentDump -Role web -Environment $webEnvironment -Path (Join-Path $ProbeRoot "web-env.json") -SessionMarker "rpf-demo-session:$session-web"
        $workerDump = Invoke-ChildEnvironmentDump -Role worker -Environment $workerEnvironment -Path (Join-Path $ProbeRoot "worker-env.json") -SessionMarker "rpf-demo-session:$session-worker"
        $seedDump = Invoke-ChildEnvironmentDump -Role seed -Environment $seedEnvironment -Path (Join-Path $ProbeRoot "seed-env.json") -SessionMarker "rpf-demo-session:$session-seed"
        $webForbidden = @("DEEPSEEK_API_KEY", "RPF_DB_PASSWORD", "RPF_AUTH_DECISION_TOKEN", "RPF_AUTH_EVIDENCE_TOKEN", "RPF_AUTH_WORKER_TOKEN", "RPF_AUTH_AGENT_TOKEN", "RPF_AUTH_CI_TOKEN", "RPF_AUTH_READ_TOKEN")
        $workerForbidden = @("DEEPSEEK_API_KEY", "RPF_DB_PASSWORD", "RPF_AUTH_DECISION_TOKEN", "RPF_AUTH_EVIDENCE_TOKEN", "RPF_AUTH_AGENT_TOKEN", "RPF_AUTH_CI_TOKEN", "RPF_AUTH_READ_TOKEN", "RPF_CONTROL_PLANE_READ_TOKEN")
        $seedForbidden = @("DEEPSEEK_API_KEY", "RPF_DB_PASSWORD", "RPF_AUTH_WORKER_TOKEN", "RPF_AUTH_AGENT_TOKEN", "RPF_AUTH_CI_TOKEN", "RPF_CONTROL_PLANE_READ_TOKEN")
        Assert-Probe (@($webForbidden | Where-Object { $null -ne $webDump.PSObject.Properties[$_] }).Count -eq 0) "web_child_has_no_write_or_db_credentials"
        Assert-Probe ([string]$webDump.RPF_CONTROL_PLANE_READ_TOKEN -eq "dummy-read-token") "web_child_has_only_read_credential"
        Assert-Probe (@($workerForbidden | Where-Object { $null -ne $workerDump.PSObject.Properties[$_] }).Count -eq 0) "worker_child_has_no_decision_or_unrelated_credentials"
        Assert-Probe ([string]$workerDump.RPF_AUTH_WORKER_TOKEN -eq "dummy-worker-token") "worker_child_has_worker_credential"
        Assert-Probe (@($seedForbidden | Where-Object { $null -ne $seedDump.PSObject.Properties[$_] }).Count -eq 0) "seed_child_has_only_seed_credentials"
        foreach ($name in $script:RpfDemoSecretEnvironmentNames) { Assert-Probe ([System.Environment]::GetEnvironmentVariable($name, "Process") -eq $beforeParent[$name]) "parent_environment_unchanged_$name" }
        $Results["parent_supervisor_does_not_add_sensitive_environment"] = $true
    }

    if ($Mode -in @("all", "contracts")) {
        $processSession = [guid]::NewGuid().ToString("N")
        $processEnvironment = New-RunProofChildEnvironment -Role build -Values @{ RPF_DEMO_SESSION_ID = $processSession }
        $ownedProcess = Start-RunProofManagedProcess -FilePath "ping.exe" -ArgumentList @("192.0.2.1", "-w", "1000", "-n", "10") -WorkingDirectory $Root -Environment $processEnvironment -StdOutPath (Join-Path $ProbeRoot "owned.stdout.log") -StdErrPath (Join-Path $ProbeRoot "owned.stderr.log") -SessionMarker "rpf-demo-session:$processSession-owned"
        $ownedRecord = New-RunProofProcessRecord -Process $ownedProcess -Role "owned" -SessionMarker "rpf-demo-session:$processSession-owned" -ExpectedPort 0
        $foreignProcess = Start-RunProofManagedProcess -FilePath "ping.exe" -ArgumentList @("192.0.2.1", "-w", "1000", "-n", "10") -WorkingDirectory $Root -Environment $processEnvironment -StdOutPath (Join-Path $ProbeRoot "foreign.stdout.log") -StdErrPath (Join-Path $ProbeRoot "foreign.stderr.log") -SessionMarker "rpf-demo-session:$processSession-foreign"
        $foreignRecord = New-RunProofProcessRecord -Process $foreignProcess -Role "foreign" -SessionMarker "rpf-demo-session:$processSession-foreign" -ExpectedPort 0
        $forgedRecord = [ordered]@{ role = "owned"; pid = $foreignRecord.pid; start_time_utc = $ownedRecord.start_time_utc; executable_path = $ownedRecord.executable_path; command_line_sha256 = $ownedRecord.command_line_sha256; session_marker = $ownedRecord.session_marker; expected_port = 0 }
        $forgedOutcome = Stop-RunProofVerifiedProcess -Record $forgedRecord
        Assert-Probe ($forgedOutcome.status -eq "SKIPPED_IDENTITY_MISMATCH" -and (Test-RunProofProcessAlive $foreignRecord)) "pid_reuse_does_not_kill_foreign_process"
        $null = Stop-RunProofVerifiedProcess -Record $ownedRecord
        $null = Stop-RunProofVerifiedProcess -Record $foreignRecord
        $Results["process_identity_uses_pid_start_executable_command_and_session"] = $true
    }

    if ($Mode -in @("all", "lifecycle")) {
        $foreignPort = Get-RunProofFreeTcpPort
        $foreignPortSession = [guid]::NewGuid().ToString("N")
        $foreignPortEnvironment = New-RunProofChildEnvironment -Role build -Values @{ RPF_DEMO_SESSION_ID = $foreignPortSession }
        $foreignPortProcess = Start-RunProofManagedProcess -FilePath "python" -ArgumentList @("-m", "http.server", "$foreignPort", "--bind", "127.0.0.1") -WorkingDirectory $Root -Environment $foreignPortEnvironment -StdOutPath (Join-Path $ProbeRoot "foreign-port.stdout.log") -StdErrPath (Join-Path $ProbeRoot "foreign-port.stderr.log") -SessionMarker "rpf-demo-session:$foreignPortSession-port"
        $foreignPortRecord = New-RunProofProcessRecord -Process $foreignPortProcess -Role "foreign-port" -SessionMarker "rpf-demo-session:$foreignPortSession-port" -ExpectedPort $foreignPort
        $ProcessRecords += $foreignPortRecord
        Start-Sleep -Milliseconds 500
        $portStateRoot = Join-Path $ProbeRoot "foreign-port-demo"
        $portContainer = "rpf23-test-port-$($ProbeId.Substring(0, 8))"
        $portVolume = "rpf23-test-port-volume-$($ProbeId.Substring(0, 8))"
        $portResult = Invoke-DemoScript -Script (Join-Path $Root "demo\start-demo.ps1") -Arguments (New-DemoArguments -StateRoot $portStateRoot -ContainerName $portContainer -VolumeName $portVolume -PgPort (Get-RunProofFreeTcpPort) -ControlPlanePort $foreignPort -WebPort (Get-RunProofFreeTcpPort) -NoWeb)
        Assert-Probe ($portResult.exit_code -ne 0 -and $portResult.output -match "PORT_OCCUPIED_BY_UNVERIFIED_PROCESS") "foreign_port_fails_closed"
        Assert-Probe (Test-RunProofProcessAlive $foreignPortRecord) "foreign_port_process_not_killed"
        $null = Stop-RunProofVerifiedProcess -Record $foreignPortRecord
        $Results["foreign_service_port_is_not_reused"] = $true

        $dockerShort = $ProbeId.Substring(0, 10)
        $foreignVolume = "rpf23-test-foreign-volume-$dockerShort"
        $foreignContainer = "rpf23-test-foreign-container-$dockerShort"
        $ownedVolume = "rpf23-test-owned-volume-$dockerShort"
        $ownedContainer = "rpf23-test-owned-container-$dockerShort"
        $foreignContainerPort = Get-RunProofFreeTcpPort
        $ownedContainerPort = Get-RunProofFreeTcpPort
        & docker volume create $foreignVolume 1>$null 2>$null
        if ($LASTEXITCODE -ne 0) { throw "PROBE_FOREIGN_VOLUME_CREATE_FAILED" }
        $CreatedVolumes += $foreignVolume
        Invoke-ContainerCreate -Name $foreignContainer -Volume $foreignVolume -Port $foreignContainerPort -Labels @{ "com.runproof.owner" = "other"; "com.runproof.demo" = "other-demo"; "com.runproof.lifecycle" = "other" }
        $CreatedContainers += $foreignContainer
        $foreignInspect = Get-RunProofDockerInspect -Kind container -Name $foreignContainer
        $foreignOwnership = Get-RunProofResourceOwnership -Inspect $foreignInspect -Kind container -ExpectedImage "postgres:16-alpine" -ExpectedVolume $foreignVolume -ExpectedPort $foreignContainerPort
        Assert-Probe ($foreignOwnership -eq "FOREIGN") "foreign_container_ownership_rejected"
        $foreignRecord = [ordered]@{ name = $foreignContainer; id = [string]$foreignInspect.Id; volume = $foreignVolume; port = $foreignContainerPort; ownership = "FOREIGN"; demo_owned = $false; config_fingerprint = Get-RunProofContainerConfigFingerprint $foreignInspect }
        $foreignRemove = Remove-RunProofExactDockerContainer -Record $foreignRecord -ExpectedImage "postgres:16-alpine" -ExpectedVolume $foreignVolume -ExpectedPort $foreignContainerPort
        Assert-Probe (-not $foreignRemove.removed -and $null -ne (Get-RunProofDockerInspect -Kind container -Name $foreignContainer)) "foreign_container_not_removed"

        & docker volume create --label "com.runproof.owner=runproof" --label "com.runproof.demo=rpf19-golden-demo" --label "com.runproof.lifecycle=rpf-23" $ownedVolume 1>$null 2>$null
        if ($LASTEXITCODE -ne 0) { throw "PROBE_OWNED_VOLUME_CREATE_FAILED" }
        $CreatedVolumes += $ownedVolume
        Invoke-ContainerCreate -Name $ownedContainer -Volume $ownedVolume -Port $ownedContainerPort -Labels @{ "com.runproof.owner" = "runproof"; "com.runproof.demo" = "rpf19-golden-demo"; "com.runproof.lifecycle" = "rpf-23" }
        $CreatedContainers += $ownedContainer
        $ownedInspect = Get-RunProofDockerInspect -Kind container -Name $ownedContainer
        $ownedRecord = [ordered]@{ name = $ownedContainer; id = [string]$ownedInspect.Id; volume = $ownedVolume; port = $ownedContainerPort; ownership = "MANAGED"; demo_owned = $true; config_fingerprint = Get-RunProofContainerConfigFingerprint $ownedInspect }
        $ownedRemove = Remove-RunProofExactDockerContainer -Record $ownedRecord -ExpectedImage "postgres:16-alpine" -ExpectedVolume $ownedVolume -ExpectedPort $ownedContainerPort
        Assert-Probe $ownedRemove.removed "owned_container_removed_after_verified_identity"
        $ownedVolumeInspect = Get-RunProofDockerInspect -Kind volume -Name $ownedVolume
        $ownedVolumeRecord = [ordered]@{ name = $ownedVolume; ownership = "MANAGED"; demo_owned = $true }
        $ownedVolumeRemove = Remove-RunProofExactDockerVolume -Record $ownedVolumeRecord
        Assert-Probe ($ownedVolumeRemove.removed -and $null -eq $ownedVolumeInspect -or $ownedVolumeRemove.removed) "owned_volume_removed_after_verified_identity"
        $CreatedContainers = @($CreatedContainers | Where-Object { $_ -ne $ownedContainer })
        $CreatedVolumes = @($CreatedVolumes | Where-Object { $_ -ne $ownedVolume })
        $Results["container_ownership_requires_verified_label_or_legacy_preservation"] = $true

        $scenarioPoints = @("control-plane", "seed", "web", "state-write")
        foreach ($point in $scenarioPoints) {
            Write-Verbose "lifecycle scenario begin: $point"
            $scenarioShort = "$($point.Replace('-', ''))-$($ProbeId.Substring(0, 8))"
            $scenarioRoot = Join-Path $ProbeRoot "scenario-$scenarioShort"
            $scenarioContainer = "rpf23-test-$scenarioShort"
            $scenarioVolume = "rpf23-test-volume-$scenarioShort"
            $scenarioPgPort = Get-RunProofFreeTcpPort
            $scenarioControlPort = Get-RunProofFreeTcpPort
            $scenarioWebPort = Get-RunProofFreeTcpPort
            $withWeb = $point -eq "web"
            $CreatedContainers += $scenarioContainer
            $CreatedVolumes += $scenarioVolume
            $failureArguments = New-DemoArguments -StateRoot $scenarioRoot -ContainerName $scenarioContainer -VolumeName $scenarioVolume -PgPort $scenarioPgPort -ControlPlanePort $scenarioControlPort -WebPort $scenarioWebPort -FailurePoint $point
            if (-not $withWeb) { $failureArguments += "-NoWeb" }
            $failed = Invoke-DemoScript -Script (Join-Path $Root "demo\start-demo.ps1") -Arguments $failureArguments
            Write-Verbose "lifecycle scenario failure start returned: $point exit=$($failed.exit_code)"
            Assert-Probe ($failed.exit_code -ne 0) "rollback_${point}_returns_failure"
            $failedState = Read-ProbeState -StateRoot $scenarioRoot
            Assert-Probe ([string]$failedState.status -eq "STOPPED") "rollback_${point}_state_stopped"
            Assert-ProbeNoSessionProcesses -State $failedState -Name "rollback_${point}"
            Assert-Probe ($null -ne (Get-RunProofDockerInspect -Kind volume -Name $scenarioVolume)) "rollback_${point}_volume_preserved"
            Assert-Probe ($null -eq (Get-RunProofDockerInspect -Kind container -Name $scenarioContainer)) "rollback_${point}_new_container_removed"
            Assert-Probe ((Test-Path -LiteralPath (Join-Path $scenarioRoot "demo-credentials.json")) -and (Test-Path -LiteralPath (Join-Path $scenarioRoot "artifacts"))) "rollback_${point}_persistent_local_data_preserved"

            $recoveryArguments = New-DemoArguments -StateRoot $scenarioRoot -ContainerName $scenarioContainer -VolumeName $scenarioVolume -PgPort $scenarioPgPort -ControlPlanePort $scenarioControlPort -WebPort $scenarioWebPort
            if (-not $withWeb) { $recoveryArguments += "-NoWeb" }
            $recovered = Invoke-DemoScript -Script (Join-Path $Root "demo\start-demo.ps1") -Arguments $recoveryArguments
            Write-Verbose "lifecycle scenario recovery start returned: $point exit=$($recovered.exit_code)"
            Assert-Probe ($recovered.exit_code -eq 0) "rollback_${point}_restart_recovers"
            $readyState = Read-ProbeState -StateRoot $scenarioRoot
            Assert-Probe ([string]$readyState.status -eq "READY") "rollback_${point}_recovery_ready"
            Write-Verbose "lifecycle scenario recovery state ready: $point"
            Assert-Probe ((Test-RunProofProcessIdentity $readyState.processes.control_plane) -and (Test-RunProofHttpReady ("$([string]$readyState.control_plane_url)/api/v1/health"))) "rollback_${point}_control_ready_after_recovery"
            if ($withWeb) { Assert-Probe ((Test-RunProofProcessIdentity $readyState.processes.web) -and (Test-RunProofWebReady ([int]$readyState.ports.web))) "rollback_${point}_web_ready_after_recovery" }
            Write-Verbose "lifecycle scenario stopping: $point"
            $stopped = Invoke-DemoScript -Script (Join-Path $Root "demo\stop-demo.ps1") -Arguments @("-StateRoot", $scenarioRoot)
            Write-Verbose "lifecycle scenario stop returned: $point exit=$($stopped.exit_code)"
            Assert-Probe ($stopped.exit_code -eq 0) "rollback_${point}_stop_preserves_data"
            $removed = Invoke-DemoScript -Script (Join-Path $Root "demo\stop-demo.ps1") -Arguments @("-StateRoot", $scenarioRoot, "-RemoveData")
            Assert-Probe ($removed.exit_code -eq 0) "rollback_${point}_remove_data_succeeds_for_labeled_resources"
            Assert-Probe ($null -eq (Get-RunProofDockerInspect -Kind container -Name $scenarioContainer) -and $null -eq (Get-RunProofDockerInspect -Kind volume -Name $scenarioVolume)) "rollback_${point}_owned_resources_removed"
            $CreatedContainers = @($CreatedContainers | Where-Object { $_ -ne $scenarioContainer })
            $CreatedVolumes = @($CreatedVolumes | Where-Object { $_ -ne $scenarioVolume })
            $Results["rollback_$point"] = $true
        }

        $pidRoot = Join-Path $ProbeRoot "pid-reuse"
        $pidContainer = "rpf23-test-pid-$dockerShort"
        $pidVolume = "rpf23-test-pid-volume-$dockerShort"
        $pidPgPort = Get-RunProofFreeTcpPort
        $pidControlPort = Get-RunProofFreeTcpPort
        $pidWebPort = Get-RunProofFreeTcpPort
        $CreatedContainers += $pidContainer
        $CreatedVolumes += $pidVolume
        $pidArguments = New-DemoArguments -StateRoot $pidRoot -ContainerName $pidContainer -VolumeName $pidVolume -PgPort $pidPgPort -ControlPlanePort $pidControlPort -WebPort $pidWebPort -NoWeb
        $pidStarted = Invoke-DemoScript -Script (Join-Path $Root "demo\start-demo.ps1") -Arguments $pidArguments
        Assert-Probe ($pidStarted.exit_code -eq 0) "pid_reuse_fixture_start"
        $pidState = Read-ProbeState -StateRoot $pidRoot
        $foreignSession = [guid]::NewGuid().ToString("N")
        $foreignEnv = New-RunProofChildEnvironment -Role build -Values @{ RPF_DEMO_SESSION_ID = $foreignSession }
        $foreignPidPort = Get-RunProofFreeTcpPort
        $foreign = Start-RunProofManagedProcess -FilePath "python" -ArgumentList @("-m", "http.server", "$foreignPidPort", "--bind", "127.0.0.1") -WorkingDirectory $Root -Environment $foreignEnv -StdOutPath (Join-Path $ProbeRoot "pid-foreign.stdout.log") -StdErrPath (Join-Path $ProbeRoot "pid-foreign.stderr.log") -SessionMarker "rpf-demo-session:$foreignSession"
        $foreignRecord = New-RunProofProcessRecord -Process $foreign -Role "pid-foreign" -SessionMarker "rpf-demo-session:$foreignSession" -ExpectedPort $foreignPidPort
        $ProcessRecords += $foreignRecord
        $originalControl = $pidState.processes.control_plane
        $pidState.processes.control_plane = [ordered]@{ role = "control-plane"; pid = $foreignRecord.pid; start_time_utc = $originalControl.start_time_utc; executable_path = $originalControl.executable_path; command_line_sha256 = $originalControl.command_line_sha256; session_marker = $originalControl.session_marker; expected_port = $pidControlPort }
        Write-RunProofStateAtomic -Path (Join-Path $pidRoot "demo-state.json") -State $pidState
        $stopForged = Invoke-DemoScript -Script (Join-Path $Root "demo\stop-demo.ps1") -Arguments @("-StateRoot", $pidRoot)
        Assert-Probe ($stopForged.exit_code -ne 0 -and (Test-RunProofProcessAlive $foreignRecord)) "stop_pid_reuse_fails_closed_without_kill"
        $restored = Read-RunProofState -Path (Join-Path $pidRoot "demo-state.json")
        $restored.state.processes.control_plane = $originalControl
        Write-RunProofStateAtomic -Path (Join-Path $pidRoot "demo-state.json") -State $restored.state
        $stoppedPid = Invoke-DemoScript -Script (Join-Path $Root "demo\stop-demo.ps1") -Arguments @("-StateRoot", $pidRoot)
        Assert-Probe ($stoppedPid.exit_code -eq 0) "pid_reuse_fixture_safe_stop"
        $removedPid = Invoke-DemoScript -Script (Join-Path $Root "demo\stop-demo.ps1") -Arguments @("-StateRoot", $pidRoot, "-RemoveData")
        Assert-Probe ($removedPid.exit_code -eq 0) "pid_reuse_fixture_cleanup"
        $CreatedContainers = @($CreatedContainers | Where-Object { $_ -ne $pidContainer })
        $CreatedVolumes = @($CreatedVolumes | Where-Object { $_ -ne $pidVolume })
        $null = Stop-RunProofVerifiedProcess -Record $foreignRecord
        $Results["stop_pid_reuse_negative"] = $true

        & python (Join-Path $Root "demo\verify-golden-demo.py") "--root" $Root "--json" 1>$null 2>$null
        Assert-Probe ($LASTEXITCODE -eq 0) "golden_demo_verifier"
    }

    $secretPattern = "(?i)DEEPSEEK_API_KEY|RPF_DB_PASSWORD|RPF_AUTH_(DECISION|EVIDENCE|WORKER|AGENT|CI)_TOKEN|Authorization\s*:\s*Bearer\s+[A-Za-z0-9._-]+"
    $stateFiles = @(Get-ChildItem -LiteralPath $ProbeRoot -Recurse -File -Filter "demo-state.json" -ErrorAction SilentlyContinue)
    foreach ($file in $stateFiles) {
        $content = Get-Content -Raw -LiteralPath $file.FullName
        $safe = [string]::IsNullOrEmpty([string]$content) -or [bool]($content -notmatch $secretPattern)
        Assert-Probe $safe "state_secret_scan_$($file.Directory.Name)"
    }
    $logFiles = @(Get-ChildItem -LiteralPath $ProbeRoot -Recurse -File -Filter "*.log" -ErrorAction SilentlyContinue)
    foreach ($file in $logFiles) {
        $content = Get-Content -Raw -LiteralPath $file.FullName
        $safe = [string]::IsNullOrEmpty([string]$content) -or [bool]($content -notmatch $secretPattern)
        Assert-Probe $safe "log_secret_scan_$($file.Name)"
    }
    $Results["state_and_log_secret_scan"] = $true

    [ordered]@{
        status = "PASS"
        schema_version = "rpf-23-demo-runtime-state-v2"
        probe_root = (Get-RunProofFullPath $ProbeRoot)
        mode = $Mode
        checks = $Results
        fresh_lifecycle = $Mode -in @("all", "lifecycle")
        provider_invoked = $false
        release_or_deploy = $false
        reviewed_artifacts_modified = $false
    } | ConvertTo-Json -Depth 10
    exit 0
} catch {
    [ordered]@{ status = "FAIL"; error = ([string]$_.Exception.Message -replace "\r?\n", " "); checks = $Results; provider_invoked = $false; release_or_deploy = $false } | ConvertTo-Json -Depth 10
    exit 1
} finally {
    $stateFiles = @(Get-ChildItem -LiteralPath $ProbeRoot -Recurse -File -Filter "demo-state.json" -ErrorAction SilentlyContinue)
    foreach ($stateFile in $stateFiles) {
        try {
            $stateResult = Read-RunProofState -Path $stateFile.FullName
            if ($stateResult.status -eq "VALID") {
                foreach ($role in @("web", "control_plane")) {
                    if ($null -ne $stateResult.state.processes.$role) { $ProcessRecords += $stateResult.state.processes.$role }
                }
            }
        } catch { }
    }
    $seenProcesses = @{}
    foreach ($record in @($ProcessRecords)) {
        if ($null -eq $record -or $null -eq $record.pid) { continue }
        $key = "$([int]$record.pid):$([string]$record.session_marker)"
        if ($seenProcesses.ContainsKey($key)) { continue }
        $seenProcesses[$key] = $true
        try { $null = Stop-RunProofVerifiedProcess -Record $record } catch { }
    }
    foreach ($containerName in @($CreatedContainers)) {
        if ($null -ne (Get-RunProofDockerInspect -Kind container -Name $containerName)) { & docker rm -f $containerName 1>$null 2>$null }
    }
    foreach ($volumeName in @($CreatedVolumes)) {
        if ($null -ne (Get-RunProofDockerInspect -Kind volume -Name $volumeName)) { & docker volume rm $volumeName 1>$null 2>$null }
    }
}

Set-StrictMode -Version 3.0

$script:RpfDemoStateSchema = "rpf-23-demo-runtime-state-v2"
$script:RpfDemoIdentity = "rpf19-golden-demo"
$script:RpfDemoOwnerLabel = "runproof"
$script:RpfDemoLifecycleLabel = "rpf-23"
$script:RpfDemoSecretEnvironmentNames = @(
    "DEEPSEEK_API_KEY",
    "RPF_DB_PASSWORD",
    "RPF_AUTH_DECISION_TOKEN",
    "RPF_AUTH_EVIDENCE_TOKEN",
    "RPF_AUTH_WORKER_TOKEN",
    "RPF_AUTH_AGENT_TOKEN",
    "RPF_AUTH_CI_TOKEN",
    "RPF_CONTROL_PLANE_READ_TOKEN",
    "RPF_AUTH_READ_TOKEN"
)
$script:RpfDemoSafeEnvironmentNames = @(
    "Path",
    "PATHEXT",
    "SystemRoot",
    "ComSpec",
    "TEMP",
    "TMP",
    "USERPROFILE",
    "HOMEDRIVE",
    "HOMEPATH",
    "ProgramData",
    "ProgramFiles",
    "ProgramFiles(x86)",
    "CommonProgramFiles",
    "CommonProgramFiles(x86)",
    "LOCALAPPDATA",
    "APPDATA"
)

function Get-RunProofSha256 {
    param([Parameter(Mandatory)][string]$Value)
    $algorithm = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($Value)
        return ([System.BitConverter]::ToString($algorithm.ComputeHash($bytes)) -replace "-", "").ToLowerInvariant()
    } finally {
        $algorithm.Dispose()
    }
}

function Get-RunProofFullPath {
    param([Parameter(Mandatory)][string]$Path)
    return [System.IO.Path]::GetFullPath($Path)
}

function Test-RunProofPathWithin {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Root
    )
    $candidate = (Get-RunProofFullPath $Path).TrimEnd("\", "/")
    $base = (Get-RunProofFullPath $Root).TrimEnd("\", "/")
    return $candidate.Equals($base, [System.StringComparison]::OrdinalIgnoreCase) -or $candidate.StartsWith($base + "\", [System.StringComparison]::OrdinalIgnoreCase) -or $candidate.StartsWith($base + "/", [System.StringComparison]::OrdinalIgnoreCase)
}

function Get-RunProofSafeEnvironment {
    $environment = @{}
    foreach ($name in $script:RpfDemoSafeEnvironmentNames) {
        $value = [System.Environment]::GetEnvironmentVariable($name, "Process")
        if ($null -ne $value) {
            $environment[$name] = [string]$value
        }
    }
    return $environment
}

function New-RunProofChildEnvironment {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][ValidateSet("build", "control-plane", "seed", "web", "worker")][string]$Role,
        [Parameter(Mandatory)][hashtable]$Values
    )

    $allowed = @{
        "build" = @("RPF_DEMO_SESSION_ID")
        "control-plane" = @(
            "RPF_DEMO_SESSION_ID", "RPF_CONTROL_PLANE_ADDRESS", "RPF_CONTROL_PLANE_PORT", "RPF_JDBC_URL", "RPF_DB_USER", "RPF_DB_PASSWORD", "RPF_ARTIFACT_STORE_ROOT", "RPF_PROBE_ENABLED",
            "RPF_AUTH_READ_TOKEN", "RPF_AUTH_EVIDENCE_TOKEN", "RPF_AUTH_DECISION_TOKEN", "RPF_AUTH_AGENT_TOKEN", "RPF_AUTH_CI_TOKEN", "RPF_AUTH_WORKER_TOKEN"
        )
        "seed" = @("RPF_DEMO_SESSION_ID", "RPF_CONTROL_PLANE_URL", "RPF_AUTH_READ_TOKEN", "RPF_AUTH_EVIDENCE_TOKEN", "RPF_AUTH_DECISION_TOKEN")
        "web" = @("RPF_DEMO_SESSION_ID", "VITE_CONTROL_PLANE_DATA_SOURCE", "RPF_CONTROL_PLANE_PROXY_TARGET", "RPF_CONTROL_PLANE_READ_TOKEN")
        "worker" = @("RPF_DEMO_SESSION_ID", "RPF_CONTROL_PLANE_URL", "RPF_AUTH_WORKER_TOKEN", "RPF_REPO_ROOT", "RPF_ARTIFACT_STORE_ROOT", "RPF_WORKER_IO_ROOT")
    }
    $environment = Get-RunProofSafeEnvironment
    $environment["RPF_DEMO_ROLE"] = $Role
    foreach ($entry in $Values.GetEnumerator()) {
        if ($allowed[$Role] -notcontains [string]$entry.Key) {
            throw "CHILD_ENVIRONMENT_FIELD_NOT_ALLOWED:${Role}:$($entry.Key)"
        }
        if ($null -eq $entry.Value) {
            continue
        }
        $environment[[string]$entry.Key] = [string]$entry.Value
    }

    foreach ($secretName in $script:RpfDemoSecretEnvironmentNames) {
        if ($Role -eq "web" -and $secretName -ne "RPF_CONTROL_PLANE_READ_TOKEN") {
            if ($environment.ContainsKey($secretName)) { throw "WEB_SECRET_NOT_ALLOWED:$secretName" }
        }
        if ($Role -eq "worker" -and $secretName -ne "RPF_AUTH_WORKER_TOKEN") {
            if ($environment.ContainsKey($secretName)) { throw "WORKER_SECRET_NOT_ALLOWED:$secretName" }
        }
    }
    return $environment
}

function ConvertTo-RunProofCmdArgument {
    param([Parameter(Mandatory)][string]$Value)
    if ($Value -notmatch '[\s&()\[\]{}^=;!''+,`~]') {
        return $Value
    }
    return '"' + $Value.Replace('"', '\"') + '"'
}

function Start-RunProofManagedProcess {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [Parameter(Mandatory)][string[]]$ArgumentList,
        [Parameter(Mandatory)][string]$WorkingDirectory,
        [Parameter(Mandatory)][hashtable]$Environment,
        [Parameter(Mandatory)][string]$StdOutPath,
        [Parameter(Mandatory)][string]$StdErrPath,
        [Parameter(Mandatory)][string]$SessionMarker
    )

    $fullFilePath = (Get-Command $FilePath -ErrorAction Stop).Source
    if ([string]::IsNullOrWhiteSpace($fullFilePath)) {
        $fullFilePath = $FilePath
    }
    $commandParts = @((ConvertTo-RunProofCmdArgument $fullFilePath))
    foreach ($argument in $ArgumentList) {
        $commandParts += ConvertTo-RunProofCmdArgument ([string]$argument)
    }
    $isBatchFile = [System.IO.Path]::GetExtension($fullFilePath).ToLowerInvariant() -in @(".cmd", ".bat")
    $invocation = ($commandParts -join " ")
    if ($isBatchFile) {
        $invocation = "call $invocation"
    }
    # `rem ... & command` treats the ampersand as part of the comment in cmd.exe;
    # use a no-op echo so the non-secret session marker remains observable in the
    # supervisor command line while the real command still executes.
    $command = "echo $SessionMarker > nul & $invocation > " + (ConvertTo-RunProofCmdArgument (Get-RunProofFullPath $StdOutPath)) + " 2>&1"
    $comSpec = [System.Environment]::GetEnvironmentVariable("ComSpec", "Process")
    if ([string]::IsNullOrWhiteSpace($comSpec)) {
        $comSpec = Join-Path ([System.Environment]::GetEnvironmentVariable("SystemRoot", "Process")) "System32\cmd.exe"
    }
    $psi = [System.Diagnostics.ProcessStartInfo]::new()
    $psi.FileName = $comSpec
    $psi.WorkingDirectory = Get-RunProofFullPath $WorkingDirectory
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.Arguments = "/d /s /c `"$command`""
    # Do not let the detached supervisor inherit the caller's stdout/stderr
    # pipes.  A long-lived child can otherwise keep an `& powershell.exe` probe
    # pipeline open after its launcher has already exited.
    $psi.RedirectStandardInput = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.EnvironmentVariables.Clear()
    foreach ($entry in $Environment.GetEnumerator()) {
        $psi.EnvironmentVariables[[string]$entry.Key] = [string]$entry.Value
    }
    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $psi
    if (-not $process.Start()) {
        throw "PROCESS_START_FAILED:$SessionMarker"
    }
    $process.StandardInput.Close()
    $null = $process.StandardOutput.ReadToEndAsync()
    $null = $process.StandardError.ReadToEndAsync()
    return $process
}

function Get-RunProofProcessSnapshot {
    param([Parameter(Mandatory)][int]$ProcessId)
    try {
        $process = Get-CimInstance -ClassName Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction Stop
        if ($null -eq $process) { return $null }
        $creationValue = $process.CreationDate
        $creationDate = if ($creationValue -is [DateTime]) { [DateTime]$creationValue } else { [System.Management.ManagementDateTimeConverter]::ToDateTime([string]$creationValue) }
        $creation = $creationDate.ToUniversalTime().ToString("o")
        $commandLine = [string]$process.CommandLine
        return [ordered]@{
            pid = $ProcessId
            start_time_utc = $creation
            executable_path = if ([string]::IsNullOrWhiteSpace([string]$process.ExecutablePath)) { $null } else { Get-RunProofFullPath ([string]$process.ExecutablePath) }
            command_line_sha256 = Get-RunProofSha256 $commandLine
            command_line = $commandLine
        }
    } catch {
        return $null
    }
}

function New-RunProofProcessRecord {
    param(
        [Parameter(Mandatory)][System.Diagnostics.Process]$Process,
        [Parameter(Mandatory)][string]$Role,
        [Parameter(Mandatory)][string]$SessionMarker,
        [Parameter(Mandatory)][int]$ExpectedPort
    )
    $deadline = (Get-Date).AddSeconds(5)
    $snapshot = $null
    do {
        $snapshot = Get-RunProofProcessSnapshot -ProcessId $Process.Id
        if ($null -ne $snapshot -and [string]$snapshot.command_line -like "*$SessionMarker*") { break }
        Start-Sleep -Milliseconds 100
    } while ((Get-Date) -lt $deadline)
    if ($null -eq $snapshot -or [string]$snapshot.command_line -notlike "*$SessionMarker*") {
        throw "PROCESS_IDENTITY_UNOBSERVABLE:$Role"
    }
    return [ordered]@{
        role = $Role
        pid = [int]$snapshot.pid
        start_time_utc = [string]$snapshot.start_time_utc
        executable_path = [string]$snapshot.executable_path
        command_line_sha256 = [string]$snapshot.command_line_sha256
        session_marker = $SessionMarker
        expected_port = $ExpectedPort
    }
}

function Test-RunProofProcessIdentity {
    param([Parameter(Mandatory)][object]$Record)
    if ($null -eq $Record.pid -or [int]$Record.pid -le 0) { return $false }
    $snapshot = Get-RunProofProcessSnapshot -ProcessId ([int]$Record.pid)
    if ($null -eq $snapshot) { return $false }
    try {
        $invariant = [Globalization.CultureInfo]::InvariantCulture
        $roundTrip = [Globalization.DateTimeStyles]::RoundtripKind
        $recordStartValue = $Record.start_time_utc
        $recordStart = if ($recordStartValue -is [DateTime]) { ([DateTime]$recordStartValue).ToUniversalTime().Ticks } else { [DateTimeOffset]::Parse([string]$recordStartValue, $invariant, $roundTrip).UtcTicks }
        $liveStart = [DateTimeOffset]::Parse([string]$snapshot.start_time_utc, $invariant, $roundTrip).UtcTicks
        if ([Math]::Abs($recordStart - $liveStart) -gt [TimeSpan]::FromSeconds(2).Ticks) { return $false }
    } catch {
        return $false
    }
    if ([string]$snapshot.executable_path -ine [string]$Record.executable_path) { return $false }
    if ([string]$snapshot.command_line_sha256 -ne [string]$Record.command_line_sha256) { return $false }
    if ([string]$snapshot.command_line -notlike "*$([string]$Record.session_marker)*") { return $false }
    return $true
}

function Test-RunProofProcessAlive {
    param([Parameter(Mandatory)][object]$Record)
    if ($null -eq $Record.pid) { return $false }
    try {
        $process = Get-Process -Id ([int]$Record.pid) -ErrorAction Stop
        return -not $process.HasExited
    } catch {
        return $false
    }
}

function Stop-RunProofVerifiedProcess {
    param([Parameter(Mandatory)][object]$Record)
    if (-not (Test-RunProofProcessAlive $Record)) {
        return [pscustomobject]@{ status = "ALREADY_EXITED"; identity_verified = $false; pid = [int]$Record.pid }
    }
    if (-not (Test-RunProofProcessIdentity $Record)) {
        return [pscustomobject]@{ status = "SKIPPED_IDENTITY_MISMATCH"; identity_verified = $false; pid = [int]$Record.pid }
    }
    try {
        & taskkill.exe /PID ([int]$Record.pid) /T /F 1>$null 2>$null
    } catch {
    }
    $deadline = (Get-Date).AddSeconds(5)
    while ((Test-RunProofProcessAlive $Record) -and (Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 100
    }
    if (Test-RunProofProcessAlive $Record) {
        return [pscustomobject]@{ status = "STOP_FAILED"; identity_verified = $true; pid = [int]$Record.pid }
    }
    return [pscustomobject]@{ status = "STOPPED"; identity_verified = $true; pid = [int]$Record.pid }
}

function Wait-RunProofProcessExit {
    param(
        [Parameter(Mandatory)][System.Diagnostics.Process]$Process,
        [Parameter(Mandatory)][int]$TimeoutSeconds,
        [Parameter(Mandatory)][string]$Role
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while (-not $Process.HasExited -and (Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 100
    }
    if (-not $Process.HasExited) {
        throw "PROCESS_TIMEOUT:$Role"
    }
    return [int]$Process.ExitCode
}

function Test-RunProofTcpPortOpen {
    param([Parameter(Mandatory)][int]$Port)
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $async = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
        if (-not $async.AsyncWaitHandle.WaitOne(300)) { return $false }
        try {
            $client.EndConnect($async)
            return $true
        } catch {
            return $false
        }
    } catch {
        return $false
    } finally {
        $client.Dispose()
    }
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

function Get-RunProofFreeTcpPort {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
    $listener.Start()
    try { return ([System.Net.IPEndPoint]$listener.LocalEndpoint).Port } finally { $listener.Stop() }
}

function Set-RunProofPrivateFileAcl {
    param([Parameter(Mandatory)][string]$Path)
    try {
        $acl = Get-Acl -LiteralPath $Path -ErrorAction Stop
        $acl.SetAccessRuleProtection($true, $false)
        $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
        $rule = [System.Security.AccessControl.FileSystemAccessRule]::new($identity, "FullControl", "Allow")
        $acl.SetAccessRule($rule)
        Set-Acl -LiteralPath $Path -AclObject $acl -ErrorAction Stop
        return [pscustomobject]@{ applied = $true; reason = $null }
    } catch {
        return [pscustomobject]@{ applied = $false; reason = "ACL_NOT_APPLIED" }
    }
}

function Get-RunProofCredentials {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$LocalRoot
    )
    if (-not (Test-RunProofPathWithin $Path $LocalRoot)) { throw "CREDENTIAL_PATH_OUTSIDE_LOCAL_ROOT" }
    if (Test-Path -LiteralPath $Path) {
        try { $credentials = Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json } catch { throw "CREDENTIAL_FILE_INVALID" }
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
        $utf8 = [System.Text.UTF8Encoding]::new($false)
        [System.IO.File]::WriteAllText((Get-RunProofFullPath $Path), ($credentials | ConvertTo-Json -Compress), $utf8)
    }
    foreach ($name in @("db_password", "read", "evidence", "decision", "agent", "ci", "worker")) {
        if ($null -eq $credentials.$name -or [string]::IsNullOrWhiteSpace([string]$credentials.$name)) { throw "CREDENTIAL_FIELD_MISSING:$name" }
    }
    $acl = Set-RunProofPrivateFileAcl -Path $Path
    return [pscustomobject]@{
        values = $credentials
        acl_applied = [bool]$acl.applied
        acl_reason = $acl.reason
    }
}

function Write-RunProofStateAtomic {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][object]$State
    )
    $directory = Split-Path -Parent (Get-RunProofFullPath $Path)
    New-Item -ItemType Directory -Force -Path $directory | Out-Null
    $temporary = "$Path.$PID.$([guid]::NewGuid().ToString('N')).tmp"
    try {
        $utf8 = [System.Text.UTF8Encoding]::new($false)
        [System.IO.File]::WriteAllText((Get-RunProofFullPath $temporary), ($State | ConvertTo-Json -Depth 16), $utf8)
        Move-Item -LiteralPath $temporary -Destination $Path -Force
    } finally {
        if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue }
    }
}

function Read-RunProofState {
    param([Parameter(Mandatory)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        return [pscustomobject]@{ status = "MISSING"; state = $null; reason = $null }
    }
    try {
        $state = Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json
    } catch {
        return [pscustomobject]@{ status = "MALFORMED"; state = $null; reason = "STATE_JSON_INVALID" }
    }
    if ([string]$state.schema_version -ne $script:RpfDemoStateSchema) {
        return [pscustomobject]@{ status = "UNSUPPORTED"; state = $state; reason = "STATE_SCHEMA_UNSUPPORTED" }
    }
    $required = @("demo_id", "session_id", "status", "processes", "postgres", "artifact_root", "secret_path")
    foreach ($field in $required) {
        if ($null -eq $state.PSObject.Properties[$field]) {
            return [pscustomobject]@{ status = "MALFORMED"; state = $state; reason = "STATE_FIELD_MISSING:$field" }
        }
    }
    if ([string]$state.demo_id -ne $script:RpfDemoIdentity -or [string]$state.session_id -notmatch '^[0-9a-fA-F-]{20,}$') {
        return [pscustomobject]@{ status = "MALFORMED"; state = $state; reason = "STATE_OWNERSHIP_INVALID" }
    }
    if ($null -eq $state.processes.PSObject.Properties["control_plane"] -or $null -eq $state.postgres.PSObject.Properties["name"]) {
        return [pscustomobject]@{ status = "MALFORMED"; state = $state; reason = "STATE_OWNERSHIP_FIELDS_MISSING" }
    }
    return [pscustomobject]@{ status = "VALID"; state = $state; reason = $null }
}

function Move-RunProofStateToArchive {
    param([Parameter(Mandatory)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    $archive = "$Path.invalid-$([DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ'))"
    Move-Item -LiteralPath $Path -Destination $archive -Force
    return $archive
}

function Get-RunProofDockerInspect {
    param([Parameter(Mandatory)][ValidateSet("container", "volume")][string]$Kind, [Parameter(Mandatory)][string]$Name)
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { return $null }
    $previousErrorAction = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $raw = @(& docker inspect $Name 2>&1)
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorAction
    }
    if ($exitCode -ne 0 -or $raw.Count -eq 0) { return $null }
    try { return ($raw -join "`n" | ConvertFrom-Json)[0] } catch { return $null }
}

function Get-RunProofContainerConfigFingerprint {
    param([Parameter(Mandatory)][object]$Inspect)
    $portBinding = $Inspect.HostConfig.PortBindings.PSObject.Properties["5432/tcp"]
    $binding = if ($null -eq $portBinding) { $null } else { @($portBinding.Value)[0] }
    $mount = @($Inspect.Mounts | Where-Object { $_.Destination -eq "/var/lib/postgresql/data" })[0]
    $hostIp = if ($null -eq $binding) { "" } else { [string]$binding.HostIp }
    $hostPort = if ($null -eq $binding) { "" } else { [string]$binding.HostPort }
    $volumeName = if ($null -eq $mount) { "" } else { [string]$mount.Name }
    $env = @($Inspect.Config.Env | ForEach-Object { [string]$_ })
    $canonical = @(
        "image=$([string]$Inspect.Config.Image)",
        "host_ip=$hostIp",
        "host_port=$hostPort",
        "volume=$volumeName",
        "destination=/var/lib/postgresql/data",
        "postgres_user=$($env -contains 'POSTGRES_USER=runproof')",
        "postgres_db=$($env -contains 'POSTGRES_DB=runproof')",
        "password_configured=$([bool]($env | Where-Object { $_ -like 'POSTGRES_PASSWORD=*' -or $_ -like 'POSTGRES_PASSWORD_FILE=*' }))"
    ) -join ";"
    return Get-RunProofSha256 $canonical
}

function Test-RunProofContainerConfig {
    param(
        [Parameter(Mandatory)][object]$Inspect,
        [Parameter(Mandatory)][string]$ExpectedImage,
        [Parameter(Mandatory)][string]$ExpectedVolume,
        [Parameter(Mandatory)][int]$ExpectedPort
    )
    if ([string]$Inspect.Config.Image -ne $ExpectedImage) { return $false }
    $portBinding = $Inspect.HostConfig.PortBindings.PSObject.Properties["5432/tcp"]
    if ($null -eq $portBinding) { return $false }
    $binding = @($portBinding.Value)[0]
    if ([string]$binding.HostIp -ne "127.0.0.1" -or [int]$binding.HostPort -ne $ExpectedPort) { return $false }
    $mount = @($Inspect.Mounts | Where-Object { $_.Destination -eq "/var/lib/postgresql/data" })[0]
    if ($null -eq $mount -or [string]$mount.Name -ne $ExpectedVolume) { return $false }
    $env = @($Inspect.Config.Env | ForEach-Object { [string]$_ })
    if ($env -notcontains "POSTGRES_USER=runproof" -or $env -notcontains "POSTGRES_DB=runproof") { return $false }
    if (-not ($env | Where-Object { $_ -like "POSTGRES_PASSWORD=*" -or $_ -like "POSTGRES_PASSWORD_FILE=*" })) { return $false }
    return $true
}

function Get-RunProofResourceLabels {
    param([Parameter(Mandatory)][object]$Inspect)
    $labels = if ($null -ne $Inspect.PSObject.Properties["Config"] -and $null -ne $Inspect.Config) { $Inspect.Config.Labels } else { $Inspect.Labels }
    if ($null -eq $labels) { return @{} }
    $result = @{}
    foreach ($property in $labels.PSObject.Properties) { $result[[string]$property.Name] = [string]$property.Value }
    return $result
}

function Get-RunProofResourceOwnership {
    param(
        [Parameter(Mandatory)][object]$Inspect,
        [Parameter(Mandatory)][ValidateSet("container", "volume")][string]$Kind,
        [string]$ExpectedImage,
        [string]$ExpectedVolume,
        [int]$ExpectedPort
    )
    if ($Kind -eq "container" -and -not (Test-RunProofContainerConfig $Inspect $ExpectedImage $ExpectedVolume $ExpectedPort)) {
        return "FOREIGN"
    }
    $labels = Get-RunProofResourceLabels $Inspect
    if ($labels.Count -eq 0) { return "LEGACY_UNLABELLED" }
    if ($labels["com.runproof.owner"] -eq $script:RpfDemoOwnerLabel -and $labels["com.runproof.demo"] -eq $script:RpfDemoIdentity -and $labels["com.runproof.lifecycle"] -eq $script:RpfDemoLifecycleLabel) {
        return "MANAGED"
    }
    return "FOREIGN"
}

function Test-RunProofContainerRecord {
    param(
        [Parameter(Mandatory)][object]$Record,
        [Parameter(Mandatory)][string]$ExpectedImage,
        [Parameter(Mandatory)][string]$ExpectedVolume,
        [Parameter(Mandatory)][int]$ExpectedPort
    )
    $inspect = Get-RunProofDockerInspect -Kind container -Name ([string]$Record.name)
    if ($null -eq $inspect) { return $false }
    if ([string]$inspect.Id -ne [string]$Record.id) { return $false }
    if (-not (Test-RunProofContainerConfig $inspect $ExpectedImage $ExpectedVolume $ExpectedPort)) { return $false }
    if ([string]$Record.config_fingerprint -ne (Get-RunProofContainerConfigFingerprint $inspect)) { return $false }
    if ((Get-RunProofResourceOwnership -Inspect $inspect -Kind container -ExpectedImage $ExpectedImage -ExpectedVolume $ExpectedVolume -ExpectedPort $ExpectedPort) -ne [string]$Record.ownership) { return $false }
    return $true
}

function Get-RunProofContainerRecord {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string]$VolumeName,
        [Parameter(Mandatory)][string]$ExpectedImage,
        [Parameter(Mandatory)][int]$ExpectedPort,
        [Parameter(Mandatory)][bool]$CreatedBySession,
        [Parameter(Mandatory)][bool]$StartedBySession
    )
    $inspect = Get-RunProofDockerInspect -Kind container -Name $Name
    if ($null -eq $inspect) { return $null }
    $ownership = Get-RunProofResourceOwnership -Inspect $inspect -Kind container -ExpectedImage $ExpectedImage -ExpectedVolume $VolumeName -ExpectedPort $ExpectedPort
    if ($ownership -eq "FOREIGN") { throw "DOCKER_CONTAINER_OWNERSHIP_INVALID:$Name" }
    $labels = Get-RunProofResourceLabels $inspect
    return [ordered]@{
        name = $Name
        id = [string]$inspect.Id
        image = [string]$inspect.Config.Image
        volume = $VolumeName
        port = $ExpectedPort
        ownership = $ownership
        demo_owned = $ownership -eq "MANAGED"
        created_by_session = $CreatedBySession
        started_by_session = $StartedBySession
        running = [bool]$inspect.State.Running
        labels_verified = $ownership -eq "MANAGED"
        config_fingerprint = Get-RunProofContainerConfigFingerprint $inspect
    }
}

function Remove-RunProofExactDockerContainer {
    param(
        [Parameter(Mandatory)][object]$Record,
        [Parameter(Mandatory)][string]$ExpectedImage,
        [Parameter(Mandatory)][string]$ExpectedVolume,
        [Parameter(Mandatory)][int]$ExpectedPort
    )
    if ([string]$Record.ownership -ne "MANAGED" -or [bool]$Record.demo_owned -ne $true) {
        return [pscustomobject]@{ status = "SKIPPED_UNVERIFIED_OWNERSHIP"; removed = $false }
    }
    if ($null -eq (Get-RunProofDockerInspect -Kind container -Name ([string]$Record.name))) {
        return [pscustomobject]@{ status = "ALREADY_REMOVED"; removed = $true }
    }
    if (-not (Test-RunProofContainerRecord $Record $ExpectedImage $ExpectedVolume $ExpectedPort)) {
        return [pscustomobject]@{ status = "SKIPPED_IDENTITY_MISMATCH"; removed = $false }
    }
    & docker rm -f ([string]$Record.name) 1>$null 2>$null
    if ($LASTEXITCODE -ne 0 -or $null -ne (Get-RunProofDockerInspect -Kind container -Name ([string]$Record.name))) {
        return [pscustomobject]@{ status = "REMOVE_FAILED"; removed = $false }
    }
    return [pscustomobject]@{ status = "REMOVED"; removed = $true }
}

function Remove-RunProofExactDockerVolume {
    param([Parameter(Mandatory)][object]$Record)
    if ([string]$Record.ownership -ne "MANAGED" -or [bool]$Record.demo_owned -ne $true) {
        return [pscustomobject]@{ status = "SKIPPED_UNVERIFIED_OWNERSHIP"; removed = $false }
    }
    $inspect = Get-RunProofDockerInspect -Kind volume -Name ([string]$Record.name)
    if ($null -eq $inspect) {
        return [pscustomobject]@{ status = "ALREADY_REMOVED"; removed = $true }
    }
    if ([string]$inspect.Name -ne [string]$Record.name) {
        return [pscustomobject]@{ status = "SKIPPED_IDENTITY_MISMATCH"; removed = $false }
    }
    $ownership = Get-RunProofResourceOwnership -Inspect $inspect -Kind volume
    if ($ownership -ne "MANAGED") {
        return [pscustomobject]@{ status = "SKIPPED_UNVERIFIED_OWNERSHIP"; removed = $false }
    }
    & docker volume rm ([string]$Record.name) 1>$null 2>$null
    if ($LASTEXITCODE -ne 0 -or $null -ne (Get-RunProofDockerInspect -Kind volume -Name ([string]$Record.name))) {
        return [pscustomobject]@{ status = "REMOVE_FAILED"; removed = $false }
    }
    return [pscustomobject]@{ status = "REMOVED"; removed = $true }
}

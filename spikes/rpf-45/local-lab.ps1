param([ValidateSet('Start','Stop')][string]$Action = 'Start')
$ErrorActionPreference = 'Stop'
$taskRepo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
if ($taskRepo -ne 'D:\CS\runproof') { throw 'Launcher root must be independently reviewed on this machine.' }
$taskLocal = Join-Path $taskRepo '.local/rpf-45'
$taskRecord = Join-Path $taskLocal 'processes.json'
if ($Action -eq 'Stop') {
  if (-not (Test-Path -LiteralPath $taskRecord)) { throw 'No task-owned process record.' }
  $taskCapability = $null
  try { $taskCapability = Invoke-RestMethod 'http://127.0.0.1:4185/effectwitness-api/capabilities' -TimeoutSec 3 } catch { }
  if ($taskCapability -and $taskCapability.busy) { throw 'An execution is active. Inspect/reconcile it before stopping.' }
  $taskProcesses = Get-Content -LiteralPath $taskRecord -Raw | ConvertFrom-Json
  foreach ($taskEntry in $taskProcesses) {
    $taskProcess = Get-Process -Id $taskEntry.id -ErrorAction SilentlyContinue
    if (-not $taskProcess) { continue }
    if ($taskProcess.StartTime.ToUniversalTime().Ticks -ne ([DateTime]$taskEntry.started_at).ToUniversalTime().Ticks -or $taskProcess.Path -ne $taskEntry.executable) { throw 'PID identity changed; refusing to stop.' }
    Get-CimInstance Win32_Process -Filter "ParentProcessId=$($taskProcess.Id)" | ForEach-Object {
      if ($_.CommandLine -match 'effectwitness.lab_gateway|esbuild') { Stop-Process -Id $_.ProcessId -ErrorAction SilentlyContinue }
    }
    Stop-Process -Id $taskProcess.Id
  }
  Remove-Item -LiteralPath $taskRecord
  Write-Output 'Stopped task-owned local Lab processes; session ledger preserved.'
  exit
}
if (Test-Path -LiteralPath $taskRecord) { throw 'Existing process record: inspect or Stop before Start.' }
foreach ($taskPort in @(4185,8765)) {
  if (Get-NetTCPConnection -State Listen -LocalPort $taskPort -ErrorAction SilentlyContinue) { throw "Required port is occupied: $taskPort" }
}
$taskTemp = Join-Path $taskLocal 'tmp'
New-Item -ItemType Directory -Path $taskTemp -Force | Out-Null
$taskKeys = @('TEMP','TMP','TMPDIR','PYTHONDONTWRITEBYTECODE','RPF_EW_LAB_ENABLED','RPF_EW_LAB_GATEWAY_TOKEN','RPF_EW_LAB_TASK_OUTPUT')
$taskOld = @{}
foreach ($taskKey in $taskKeys) { $taskOld[$taskKey] = [Environment]::GetEnvironmentVariable($taskKey,'Process') }
$taskStarted = @()
try {
  $env:TEMP=$taskTemp; $env:TMP=$taskTemp; $env:TMPDIR=$taskTemp
  $env:PYTHONDONTWRITEBYTECODE='1'; $env:RPF_EW_LAB_ENABLED='1'; $env:RPF_EW_LAB_TASK_OUTPUT='1'
  $taskSecretBytes = New-Object byte[] 32
  $taskRng = [Security.Cryptography.RandomNumberGenerator]::Create()
  try { $taskRng.GetBytes($taskSecretBytes) } finally { $taskRng.Dispose() }
  $env:RPF_EW_LAB_GATEWAY_TOKEN = [Convert]::ToBase64String($taskSecretBytes)
  $taskPython = (Get-Command python.exe).Source
  $taskPython = (& $taskPython -c 'import sys; print(sys.executable)').Trim()
  $taskNode = (Get-Command node.exe).Source
  $taskStarted += Start-Process -FilePath $taskPython -ArgumentList @('-m','runtime.runproof_runtime.effectwitness.lab_gateway','--enable-local-simulation') -WorkingDirectory $taskRepo -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $taskLocal 'gateway.log') -RedirectStandardError (Join-Path $taskLocal 'gateway-error.log')
  $taskVite = Join-Path $taskRepo 'node_modules/vite/bin/vite.js'
  if (-not (Test-Path -LiteralPath $taskVite)) { throw 'Existing Vite dependency missing; no automatic install.' }
  $taskStarted += Start-Process -FilePath $taskNode -ArgumentList @($taskVite) -WorkingDirectory $taskRepo -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $taskLocal 'web.log') -RedirectStandardError (Join-Path $taskLocal 'web-error.log')
  $taskStarted | ForEach-Object { @{id=$_.Id; started_at=$_.StartTime.ToUniversalTime().ToString('o'); executable=$_.Path} } | ConvertTo-Json | Set-Content -LiteralPath $taskRecord -Encoding utf8
  $taskDeadline = [DateTime]::UtcNow.AddSeconds(15)
  $taskReady = $false
  while ([DateTime]::UtcNow -lt $taskDeadline) {
    try {
      $taskReply = Invoke-RestMethod 'http://127.0.0.1:4185/effectwitness-api/capabilities' -TimeoutSec 2
      if ($taskReply.schema_version -eq 'rpf-lab-v1') { $taskReady=$true; break }
    } catch { Start-Sleep -Milliseconds 250 }
  }
  if (-not $taskReady) { throw 'Gateway readiness failed; inspect task-local sanitized logs.' }
  Write-Output 'Ready: http://127.0.0.1:4185/effectwitness (local controlled simulation, 3 durable reservations maximum).'
} catch {
  foreach ($taskProcess in $taskStarted) { if (-not $taskProcess.HasExited) { Stop-Process -Id $taskProcess.Id } }
  if (Test-Path -LiteralPath $taskRecord) { Remove-Item -LiteralPath $taskRecord }
  throw
} finally {
  foreach ($taskKey in $taskKeys) { [Environment]::SetEnvironmentVariable($taskKey,$taskOld[$taskKey],'Process') }
}

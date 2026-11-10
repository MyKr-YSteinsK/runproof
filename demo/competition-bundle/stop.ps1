#Requires -Version 7.2
[CmdletBinding()]
param([Parameter(Mandatory)][ValidatePattern('^[a-f0-9]{32}$')][string]$Nonce)
$ErrorActionPreference = 'Stop'
$path = Join-Path $PSScriptRoot '.local/launch/processes.json'
for ($item = Get-Item -LiteralPath $path -Force; $item; ) {
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Linked receipt path.' }
    $parent = Split-Path -Parent $item.FullName
    $item = if ($parent) { Get-Item -LiteralPath $parent -Force }
}
$claim = [IO.File]::Open($path, 'Open', 'Read', 'None')
try {
    $reader = [IO.StreamReader]::new($claim)
    try { $receipt = ConvertFrom-Json -InputObject $reader.ReadToEnd() } finally { $reader.Dispose() }
    if ($receipt.nonce -cne $Nonce -or $receipt.records.Count -gt 2) { throw 'Unexpected process receipt.' }
    $owned = @()
    foreach ($record in $receipt.records) {
        $process = Get-Process -Id $record.pid -ErrorAction SilentlyContinue
        if (!$process) { continue }
        if ($process.Path -ne $record.exe -or $process.StartTime.ToUniversalTime().Ticks.ToString() -ne $record.started) {
            throw 'Process identity changed. Receipt retained.'
        }
        $owned += $process
    }
    foreach ($process in $owned) {
        if (!$process.HasExited) { $process.Kill() }
        if (!$process.WaitForExit(5000)) { throw 'Process exit not confirmed.' }
    }
} finally { $claim.Dispose() }
Write-Output 'Demo processes stopped. Local ledger and process receipt retained.'

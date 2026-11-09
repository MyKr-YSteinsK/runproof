[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$owner = Join-Path (Split-Path -Parent $PSScriptRoot) '.local/rpf-100-product/live'
$receipt = Join-Path $owner 'active.json'
if (!(Test-Path -LiteralPath $receipt -PathType Leaf)) { throw 'No active product process receipt.' }
foreach ($item in @((Get-Item -LiteralPath $receipt),(Get-Item -LiteralPath $owner),
    (Get-Item -LiteralPath (Split-Path -Parent $owner)),
    (Get-Item -LiteralPath (Split-Path -Parent (Split-Path -Parent $owner))))) {
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Linked receipt path.' }
}
$claim = [IO.File]::Open($receipt, [IO.FileMode]::Open, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
$stopped = $false
try {
    $reader = [IO.StreamReader]::new($claim,[Text.Encoding]::UTF8,$true,1024,$true)
    try { $records = @(ConvertFrom-Json -InputObject $reader.ReadToEnd()) } finally { $reader.Dispose() }
    if ($records.Count -gt 2) { throw 'Unexpected process receipt.' }
    $owned = @()
    foreach ($record in $records) {
        $process = Get-Process -Id $record.pid -ErrorAction SilentlyContinue
        if (!$process) { continue }
        if ($process.Path -ne $record.exe -or $process.StartTime.ToUniversalTime().Ticks.ToString() -ne $record.started) {
            throw 'Process identity changed. Preserve the receipt for review.'
        }
        $owned += $process
    }
    foreach ($process in $owned) {
        $process.Kill()
        if (!$process.WaitForExit(5000)) { throw 'Process exit not confirmed.' }
    }
    $stopped = $true
} finally { $claim.Dispose() }
if ($stopped) {
    Rename-Item -LiteralPath $receipt -NewName ('stopped-' + [guid]::NewGuid().ToString('N') + '.json')
    Write-Output 'Product processes stopped. Session ledger retained.'
}

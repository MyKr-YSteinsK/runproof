#Requires -Version 7.2
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$PythonExe,
    [Parameter(Mandatory)][string]$Witness,
    [ValidatePattern('^[a-f0-9]{64}$')][string]$ExpectedSha256
)
$ErrorActionPreference = 'Stop'
if (![IO.Path]::IsPathFullyQualified($PythonExe)) { throw 'Supply an absolute python.exe path.' }
$python = Get-Item -LiteralPath $PythonExe
if ($python.Name -ne 'python.exe' -or $python.PSIsContainer -or
    ($python.Attributes -band [IO.FileAttributes]::ReparsePoint) -or $python.FullName -match 'WindowsApps|PyManager') {
    throw 'Unverified python.exe.'
}
$arguments = @((Resolve-Path -LiteralPath $Witness).Path)
if ($ExpectedSha256) { $arguments += @('--expected-sha256', $ExpectedSha256) }
$manifest = Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot 'bundle-manifest.json') | ConvertFrom-Json
$verifier = if ($manifest.schema -eq 'runproof-competition-complete/v1') { 'competition_agent_verify' } else { 'product_local_verify' }
Push-Location -LiteralPath $PSScriptRoot
try {
    & $python.FullName -E -B -m ("runtime.runproof_runtime.effectwitness." + $verifier) @arguments
    exit $LASTEXITCODE
} finally { Pop-Location }

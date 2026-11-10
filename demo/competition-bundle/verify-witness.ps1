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
Push-Location -LiteralPath $PSScriptRoot
try {
    & $python.FullName -E -B -m runtime.runproof_runtime.effectwitness.product_local_verify @arguments
    exit $LASTEXITCODE
} finally { Pop-Location }

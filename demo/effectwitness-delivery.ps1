[CmdletBinding()]
param(
    [Parameter(Mandatory, Position=0)]
    [ValidateSet('Build', 'Preview', 'Package', 'Verify')]
    [string]$Action,
    [string]$RunRoot,
    [string]$BundleRoot,
    [string]$NodeExe,
    [ValidateRange(1,65535)][int]$Port = 4174
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$outputRoot = Join-Path $repo '.local/rpf-99-product-delivery'
if (!$NodeExe) { $NodeExe = (Get-Command node.exe -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source }
if (![IO.Path]::IsPathRooted($NodeExe)) { throw 'Provide an absolute Node executable path.' }
$nodeFile = Get-Item -LiteralPath $NodeExe
if ($nodeFile.Name -ne 'node.exe' -or $nodeFile.PSIsContainer -or
    ($nodeFile.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Node must be a regular node.exe.' }
$NodeExe = $nodeFile.FullName
$nodeVersion = & $NodeExe --version
if ($LASTEXITCODE -ne 0 -or $nodeVersion -notmatch '^v\d+\.\d+\.\d+$') { throw 'Node verification failed.' }

function Invoke-Checked {
    param([string]$Program, [string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed with exit $LASTEXITCODE." }
}

function Assert-RunRoot([string]$Value) {
    if (!$Value) { throw 'Supply -RunRoot from the Build output.' }
    $item = Get-Item -LiteralPath $Value
    if (!$item.PSIsContainer -or $item.Parent.FullName -ne [IO.Path]::GetFullPath($outputRoot) -or
        $item.Name -notmatch '^[a-f0-9]{12}-[a-f0-9]{32}$') { throw 'Invalid delivery run directory.' }
    foreach ($dir in @($item, $item.Parent, $item.Parent.Parent)) {
        if ($dir.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Linked delivery directory.' }
    }
    return $item.FullName
}

if ($Action -eq 'Build') {
    if ($RunRoot -or $BundleRoot) { throw 'Build creates a fresh run directory.' }
    $git = (Get-Command git -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
    $commit = & $git -C $repo rev-parse HEAD
    if ($LASTEXITCODE -ne 0 -or $commit -notmatch '^[a-f0-9]{40}$') { throw 'Git commit unavailable.' }
    $buildInputs = @('web','public','index.html','vite.config.ts','tsconfig.json','package.json','package-lock.json',
        'spikes/rpf-43','spikes/rpf-44','spikes/rpf-46','spikes/rpf-47',
        'demo/effectwitness-preview.cjs','docs/EFFECTWITNESS_DELIVERY.md','docs/EFFECTWITNESS_DELIVERY.zh-CN.md')
    $changes = & $git -C $repo status --porcelain --untracked-files=all -- @buildInputs
    if ($LASTEXITCODE -ne 0 -or $changes) { throw 'Commit the scoped bundle inputs before building.' }
    foreach ($dir in @((Join-Path $repo '.local'), $outputRoot)) {
        if (!(Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir | Out-Null }
        $item = Get-Item -LiteralPath $dir
        if (!$item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw 'Delivery output root must be a regular directory.'
        }
    }
    $run = Join-Path $outputRoot ($commit.Substring(0,12) + '-' + [guid]::NewGuid().ToString('N'))
    $bundle = Join-Path $run 'bundle'
    New-Item -ItemType Directory -Path $run | Out-Null
    New-Item -ItemType Directory -Path $bundle | Out-Null
    $npm = Join-Path $nodeFile.DirectoryName 'npm.cmd'
    if (!(Test-Path -LiteralPath $npm -PathType Leaf) -or
        !(Test-Path -LiteralPath (Join-Path $repo 'node_modules/vite/bin/vite.js') -PathType Leaf)) {
        throw 'Existing npm and project build dependencies are required.'
    }
    $previous = $env:VITE_RPF_RECORDED_DELIVERY
    $previousData = $env:VITE_CONTROL_PLANE_DATA_SOURCE
    $previousApi = $env:VITE_CONTROL_PLANE_API_URL
    $previousCache = $env:npm_config_cache
    $previousPath = $env:Path
    try {
        $env:VITE_RPF_RECORDED_DELIVERY = '1'
        $env:VITE_CONTROL_PLANE_DATA_SOURCE = 'fixture'
        $env:VITE_CONTROL_PLANE_API_URL = '/api/v1'
        $env:npm_config_cache = Join-Path $run 'npm-cache'
        $env:Path = $nodeFile.DirectoryName + [IO.Path]::PathSeparator + $previousPath
        Push-Location $repo
        try { Invoke-Checked $npm @('run','build','--','--configLoader','runner','--outDir',(Join-Path $bundle 'site')) }
        finally { Pop-Location }
    } finally {
        $env:VITE_RPF_RECORDED_DELIVERY = $previous
        $env:VITE_CONTROL_PLANE_DATA_SOURCE = $previousData
        $env:VITE_CONTROL_PLANE_API_URL = $previousApi
        $env:npm_config_cache = $previousCache
        $env:Path = $previousPath
    }
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'effectwitness-preview.cjs') -Destination $bundle
    Copy-Item -LiteralPath (Join-Path $repo 'docs/EFFECTWITNESS_DELIVERY.md') -Destination (Join-Path $bundle 'START_HERE.md')
    Copy-Item -LiteralPath (Join-Path $repo 'docs/EFFECTWITNESS_DELIVERY.zh-CN.md') -Destination (Join-Path $bundle 'START_HERE.zh-CN.md')
    Invoke-Checked $NodeExe @((Join-Path $PSScriptRoot 'effectwitness-preview.cjs'),'seal',$bundle,$commit)
    Write-Output "RunRoot=$run"
    return
}

$verifier = Join-Path $PSScriptRoot 'effectwitness-preview.cjs'
if ($Action -eq 'Package') {
    if ($BundleRoot) { throw 'Package takes -RunRoot only.' }
    $run = Assert-RunRoot $RunRoot
    $bundle = Join-Path $run 'bundle'
    Invoke-Checked $NodeExe @($verifier,'verify',$bundle)
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = Join-Path $run 'effectwitness-recorded.zip'
    $receipt = "$zip.sha256"
    if ((Test-Path -LiteralPath $zip) -or (Test-Path -LiteralPath $receipt)) { throw 'Package output already exists.' }
    [IO.Compression.ZipFile]::CreateFromDirectory($bundle, $zip)
    $hash = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant()
    $stream = [IO.File]::Open($receipt, [IO.FileMode]::CreateNew)
    try {
        $bytes = [Text.Encoding]::ASCII.GetBytes("$hash  effectwitness-recorded.zip`n")
        $stream.Write($bytes, 0, $bytes.Length)
    } finally { $stream.Dispose() }
    Write-Output "ZIP=$zip"
    Write-Output "SHA256=$hash"
    return
}

if ($BundleRoot -and $RunRoot) { throw 'Choose either -RunRoot or -BundleRoot.' }
$bundle = if ($BundleRoot) { (Get-Item -LiteralPath $BundleRoot).FullName }
          else { Join-Path (Assert-RunRoot $RunRoot) 'bundle' }
if ($Action -eq 'Verify') { Invoke-Checked $NodeExe @($verifier,'probe',$bundle,[string]$Port); return }
Invoke-Checked $NodeExe @($verifier,'serve',$bundle,[string]$Port)

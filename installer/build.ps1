# Build the Kali Linux Windows Substitute installer.
# Run from the repository root or from installer/ - both work.

[CmdletBinding()]
param(
    [switch]$SkipCheck,
    [switch]$SkipPyInstaller
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $Here
$Dist = Join-Path $Here 'dist'
$Build = Join-Path $Here 'build'
$AppName = 'KaliWindowsSubstitute'

Write-Host "== Kali Linux Windows Substitute: build ==" -ForegroundColor Green
Write-Host "repo root: $Root"

function Invoke-Python {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Args)
    foreach ($exe in @('py', 'python')) {
        $cmd = Get-Command $exe -ErrorAction SilentlyContinue
        if ($cmd) { & $cmd.Source @Args; return }
    }
    throw 'Python was not found on PATH.'
}

# 1. Headless self-check.
if (-not $SkipCheck) {
    Write-Host "`n[1/4] self-check" -ForegroundColor Cyan
    Push-Location $Root
    try {
        Invoke-Python app/main.py --check
    } finally {
        Pop-Location
    }
}

# 2. PyInstaller build.
if (-not $SkipPyInstaller) {
    Write-Host "`n[2/4] PyInstaller" -ForegroundColor Cyan
    Push-Location $Root
    try {
        Invoke-Python -m pip install --upgrade pip | Out-Null
        Invoke-Python -m pip install -r requirements.txt | Out-Null
        Invoke-Python -m pip install pyinstaller | Out-Null
        $sep = [IO.Path]::PathSeparator
        $add = @(
            "ui$sep=ui",
            "catalog$sep=catalog",
            "server$sep=server",
            "runtime$sep=runtime",
            "kws$sep=kws"
        )
        $pyArgs = @(
            '-m', 'PyInstaller', '--noconfirm', '--clean',
            '--name', $AppName, '--windowed',
            '--distpath', $Dist, '--workpath', $Build,
            '--paths', $Root
        )
        foreach ($a in $add) { $pyArgs += @('--add-data', $a) }
        $pyArgs += (Join-Path $Root 'app/main.py')
        Invoke-Python @pyArgs
    } finally {
        Pop-Location
    }
}

# 3. Stage the app + setup scripts, then zip.
Write-Host "`n[3/4] packaging" -ForegroundColor Cyan
$appDir = Join-Path $Dist $AppName
if (-not (Test-Path $appDir)) {
    throw "expected build output at $appDir"
}
$stage = Join-Path $Build 'stage'
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory -Force -Path (Join-Path $stage 'app') | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $stage 'setup') | Out-Null
Copy-Item (Join-Path $appDir '*') (Join-Path $stage 'app') -Recurse -Force
Copy-Item (Join-Path $Here 'setup\*') (Join-Path $stage 'setup') -Recurse -Force

$payload = Join-Path $Dist 'payload.zip'
if (Test-Path $payload) { Remove-Item $payload -Force }
Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $payload -Force
Write-Host ("payload: {0:N1} MB" -f ((Get-Item $payload).Length / 1MB))

# 4. Compile the self-extracting stub.
Write-Host "`n[4/4] setup stub" -ForegroundColor Cyan
$csc = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path $csc)) {
    Write-Warning "csc.exe not found; the installer exe could not be compiled."
    Write-Host "The portable build is still available at $appDir"
    exit 0
}
$setup = Join-Path $Dist 'KaliWindowsSubstitute-Setup.exe'
& $csc /nologo /target:winexe /out:$setup `
    /resource:$payload,"$AppName.payload" `
    (Join-Path $Here 'SetupStub.cs')
if ($LASTEXITCODE -ne 0) { throw "csc failed with code $LASTEXITCODE" }
Remove-Item $payload -Force

Write-Host "`nDone: $setup" -ForegroundColor Green
Write-Host "Portable build: $appDir"

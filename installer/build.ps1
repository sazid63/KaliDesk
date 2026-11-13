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

# Python must answer "--version" with exit 0. The Microsoft Store alias in
# WindowsApps is skipped: without a real Python it exits with 9009.
$script:PythonCmd = $null
function Find-Python {
    foreach ($exe in @('py', 'python')) {
        $cmd = Get-Command $exe -ErrorAction SilentlyContinue
        if (-not $cmd) { continue }
        if ($cmd.Source -match '\\WindowsApps\\') { continue }
        try {
            & $cmd.Source --version *> $null
            if ($LASTEXITCODE -eq 0) { return $cmd.Source }
        } catch {
            continue
        }
    }
    return $null
}

function Invoke-Python {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$PyArgs)
    if (-not $script:PythonCmd) {
        $script:PythonCmd = Find-Python
    }
    if (-not $script:PythonCmd) {
        throw ('Python 3 was not found (or only the Microsoft Store alias is present). ' +
               'Install Python 3.10+ from https://www.python.org/downloads/ and run this build again.')
    }
    & $script:PythonCmd @PyArgs
    if ($LASTEXITCODE -ne 0) { throw "python $($PyArgs -join ' ') failed with code $LASTEXITCODE" }
}

# 0. Version. The installer's DisplayVersion is a literal in setup\Install.ps1
#    (tests/test_version.py asserts it), so fail the build if it drifts from
#    kws\__about__.py instead of silently shipping the wrong number.
$aboutText = Get-Content -Path (Join-Path $Root 'kws\__about__.py') -Raw
$aboutMatch = [regex]::Match($aboutText, '__version__\s*=\s*"([^"]+)"')
if (-not $aboutMatch.Success) { throw 'could not read __version__ from kws/__about__.py' }
$appVersion = $aboutMatch.Groups[1].Value
$installText = Get-Content -Path (Join-Path $Here 'setup\Install.ps1') -Raw
$displayMatch = [regex]::Match($installText, "'DisplayVersion'\s+-Value\s+'([^']+)'")
if (-not $displayMatch.Success) { throw 'could not find DisplayVersion in setup\Install.ps1' }
if ($displayMatch.Groups[1].Value -ne $appVersion) {
    throw "setup\Install.ps1 DisplayVersion is '$($displayMatch.Groups[1].Value)' but kws/__about__.py says '$appVersion'. Update Install.ps1."
}
Write-Host "version: $appVersion"

# Files the app reads from its bundle at run time (see app/runtime.py,
# kws/paths.py and server/app.py, server/catalog.py). server/ and kws/ are
# Python packages: PyInstaller collects them from the imports, so they are not
# added as data.
$bundled = @(
    @{ Src = 'runtime\agent\agent.py';                          Dest = 'runtime\agent' },
    @{ Src = 'runtime\rootfs\etc\kalisub\tools.json';           Dest = 'runtime\rootfs\etc\kalisub' },
    @{ Src = 'runtime\rootfs\etc\wsl.conf';                     Dest = 'runtime\rootfs\etc' },
    @{ Src = 'runtime\rootfs\usr\local\bin\kalisub-agent-start'; Dest = 'runtime\rootfs\usr\local\bin' },
    @{ Src = 'ui';                                              Dest = 'ui' },
    @{ Src = 'catalog';                                         Dest = 'catalog' }
)
foreach ($b in $bundled) {
    if (-not (Test-Path -LiteralPath (Join-Path $Root $b.Src))) {
        throw "bundled file or folder is missing: $($b.Src)"
    }
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

# 2. PyInstaller build. requirements-build.txt pins PyInstaller and includes
#    the runtime requirements.
if (-not $SkipPyInstaller) {
    Write-Host "`n[2/4] PyInstaller" -ForegroundColor Cyan
    Push-Location $Root
    try {
        Invoke-Python -m pip install --upgrade pip | Out-Null
        Invoke-Python -m pip install -r (Join-Path $Root 'requirements-build.txt') | Out-Null
        $sep = [IO.Path]::PathSeparator
        $pyArgs = @(
            '-m', 'PyInstaller', '--noconfirm', '--clean',
            '--name', $AppName, '--windowed',
            '--distpath', $Dist, '--workpath', $Build,
            '--paths', $Root
        )
        foreach ($b in $bundled) {
            $src = Join-Path $Root $b.Src
            $pyArgs += @('--add-data', ($src + $sep + $b.Dest))
        }
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
foreach ($doc in @('LICENSE', 'THIRD_PARTY_NOTICES.md')) {
    Copy-Item -LiteralPath (Join-Path $Root $doc) -Destination (Join-Path $stage 'app') -Force
}
Copy-Item (Join-Path $Here 'setup\*') (Join-Path $stage 'setup') -Recurse -Force
# enable-wsl.ps1 sits in installer\ but ships in setup\ next to Prereqs.ps1.
Copy-Item -LiteralPath (Join-Path $Here 'enable-wsl.ps1') -Destination (Join-Path $stage 'setup') -Force

$payload = Join-Path $Dist 'payload.zip'
if (Test-Path $payload) { Remove-Item $payload -Force }
Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $payload -Force
Write-Host ("payload: {0:N1} MB" -f ((Get-Item $payload).Length / 1MB))

# 4. Compile the self-extracting stub.
Write-Host "`n[4/4] setup stub" -ForegroundColor Cyan
$cscCandidates = @(
    (Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'),
    (Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319\csc.exe')
)
$csc = $cscCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $csc) {
    # A missing compiler is a failed build, locally and in CI. The portable build
    # in $appDir is still on disk if you only need the app folder.
    throw "csc.exe not found under $env:WINDIR\Microsoft.NET (tried Framework64 and Framework v4.0.30319); the installer exe cannot be compiled. (Portable build: $appDir)"
}
$setup = Join-Path $Dist 'KaliWindowsSubstitute-Setup.exe'
# The .NET Framework csc.exe is a C# 5 compiler: the stub must not use newer
# syntax (e.g. `using static`), and the zip assemblies are not referenced by default.
& $csc /nologo /target:winexe /out:$setup `
    /r:System.Windows.Forms.dll /r:System.IO.Compression.dll `
    /r:System.IO.Compression.FileSystem.dll `
    /resource:$payload,"$AppName.payload" `
    (Join-Path $Here 'SetupStub.cs')
if ($LASTEXITCODE -ne 0) { throw "csc failed with code $LASTEXITCODE" }
Remove-Item $payload -Force

Write-Host "`nDone: $setup" -ForegroundColor Green
Write-Host "Portable build: $appDir"

<#
    Install Kali Linux Windows Substitute for the current user.

    - Copies the app into the chosen directory (default
      %LOCALAPPDATA%\Programs\KaliWindowsSubstitute)
    - Creates a Start Menu shortcut
    - Registers an uninstall entry under HKCU
    - Optionally copies a runtime image the app can import
    - Optionally launches the app

    This is the *silent core*. The click-through wizard (Wizard.ps1) collects
    the choices and calls this script. It never creates, terminates or
    unregisters a WSL distribution - the app does that itself, for its own
    distribution only, the first time you press "Set up runtime".
#>
[CmdletBinding()]
param(
    [string]$AppSource = '',
    [string]$InstallDir = '',
    [string]$RuntimeImage = '',
    [string]$LogFile = '',
    [switch]$Launch,
    [switch]$Quiet
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$AppName    = 'Kali Linux Windows Substitute'
$FolderName = 'KaliWindowsSubstitute'
$ExeName    = "$FolderName.exe"

if ([string]::IsNullOrWhiteSpace($InstallDir)) {
    $InstallDir = Join-Path $env:LOCALAPPDATA "Programs\$FolderName"
}
$Target = $InstallDir

if ([string]::IsNullOrWhiteSpace($AppSource)) {
    $AppSource = Join-Path (Split-Path -Parent $PSScriptRoot) 'app'
}
if (-not (Test-Path $AppSource)) {
    throw "application files were not found at '$AppSource'"
}

function Write-Step {
    param([string]$Message, [ConsoleColor]$Color = [ConsoleColor]::Gray)
    if (-not $Quiet) { Write-Host $Message -ForegroundColor $Color }
    if (-not [string]::IsNullOrWhiteSpace($LogFile)) {
        Add-Content -Path $LogFile -Value $Message -Encoding UTF8
    }
}

Write-Step "Installing $AppName" ([ConsoleColor]::Green)
Write-Step "  from: $AppSource"
Write-Step "  into: $Target"

# Stop a running copy so files are not locked.
Get-Process -Name $FolderName -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

New-Item -ItemType Directory -Path $Target -Force | Out-Null
Copy-Item -Path (Join-Path $AppSource '*') -Destination $Target -Recurse -Force

# Start Menu shortcut.
$startMenu = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'
$lnkPath = Join-Path $startMenu "$AppName.lnk"
$exePath = Join-Path $Target $ExeName
if (Test-Path $exePath) {
    $shell = New-Object -ComObject WScript.Shell
    $lnk = $shell.CreateShortcut($lnkPath)
    $lnk.TargetPath = $exePath
    $lnk.WorkingDirectory = $Target
    $lnk.Description = $AppName
    $lnk.Save()
    Write-Step "  shortcut: $lnkPath"
}

# Optional runtime image. The app looks for it in its user data folder, so copy
# it there under the name the app expects.
if (-not [string]::IsNullOrWhiteSpace($RuntimeImage)) {
    if (Test-Path $RuntimeImage) {
        $dataDir = Join-Path $env:LOCALAPPDATA $FolderName
        New-Item -ItemType Directory -Path $dataDir -Force | Out-Null
        $ext = [IO.Path]::GetExtension($RuntimeImage).ToLowerInvariant()
        $destName = if ($ext -eq '.gz') { 'kalisub-rootfs.tar.gz' } else { 'kalisub-rootfs.tar' }
        Copy-Item -Path $RuntimeImage -Destination (Join-Path $dataDir $destName) -Force
        Write-Step "  runtime image: $destName" ([ConsoleColor]::Green)
    } else {
        Write-Warning "runtime image not found: $RuntimeImage"
    }
}

# Uninstall entry (per-user, no admin needed).
$uninstallKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\$FolderName"
New-Item -Path $uninstallKey -Force | Out-Null
Set-ItemProperty -Path $uninstallKey -Name 'DisplayName'     -Value $AppName
Set-ItemProperty -Path $uninstallKey -Name 'DisplayVersion'  -Value '0.1.0'
Set-ItemProperty -Path $uninstallKey -Name 'Publisher'       -Value 'Kali Linux Windows Substitute contributors'
Set-ItemProperty -Path $uninstallKey -Name 'InstallLocation' -Value $Target
Set-ItemProperty -Path $uninstallKey -Name 'NoModify'        -Value 1 -Type DWord
Set-ItemProperty -Path $uninstallKey -Name 'NoRepair'        -Value 1 -Type DWord
$uninstallCmd = "powershell -NoProfile -ExecutionPolicy Bypass -Command `"& '$PSScriptRoot\Uninstall.ps1'`""
Set-ItemProperty -Path $uninstallKey -Name 'UninstallString' -Value $uninstallCmd
Write-Step "  uninstall entry: $uninstallKey"

# WSL2 check (message only - it never enables anything by itself).
Write-Step ''
$wsl = Get-Command wsl.exe -ErrorAction SilentlyContinue
$wslReady = $false
if ($wsl) {
    & $wsl.Source --status 2>&1 | Out-Null
    $wslReady = ($LASTEXITCODE -eq 0)
}
if ($wslReady) {
    Write-Step 'WSL2 is available. Open the app and press "Set up runtime"." ' ([ConsoleColor]::Green)
} else {
    Write-Step 'WSL2 does not look ready on this machine.' ([ConsoleColor]::Yellow)
    Write-Step 'The app needs WSL2 to run the real tools. See docs/PREREQUISITES.md.'
    $enableScript = Join-Path $PSScriptRoot 'Prereqs.ps1'
    if (Test-Path $enableScript) {
        Write-Step "To enable it later, run (as administrator): $enableScript -Wsl"
    }
}

if ($Launch -and (Test-Path $exePath)) {
    Write-Step 'Launching the app ...' ([ConsoleColor]::Green)
    Start-Process -FilePath $exePath -WorkingDirectory $Target
}

Write-Step "Installed. Launch it from the Start Menu: $AppName" ([ConsoleColor]::Green)
exit 0

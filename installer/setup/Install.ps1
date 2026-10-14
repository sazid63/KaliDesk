<#
    Install Kali Linux Windows Substitute for the current user.

    - Copies the app into %LOCALAPPDATA%\Programs\KaliWindowsSubstitute
    - Creates a Start Menu shortcut
    - Registers an uninstall entry under HKCU
    - Offers to enable WSL2 (a one-time Windows feature)

    It never creates, terminates or unregisters a WSL distribution - the app
    does that itself, for its own distribution only, the first time you press
    "Set up runtime".
#>
[CmdletBinding()]
param(
    [string]$AppSource = '',
    [switch]$Quiet
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$AppName    = 'Kali Linux Windows Substitute'
$FolderName = 'KaliWindowsSubstitute'
$Target     = Join-Path $env:LOCALAPPDATA "Programs\$FolderName"
$ExeName    = "$FolderName.exe"

if ([string]::IsNullOrWhiteSpace($AppSource)) {
    $AppSource = Join-Path (Split-Path -Parent $PSScriptRoot) 'app'
}
if (-not (Test-Path $AppSource)) {
    throw "application files were not found at '$AppSource'"
}

Write-Host "Installing $AppName" -ForegroundColor Green
Write-Host "  from: $AppSource"
Write-Host "  into: $Target"

# Stop a running copy so files are not locked.
Get-Process -Name $FolderName -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

if (-not (Test-Path $Target)) { New-Item -ItemType Directory -Path $Target -Force | Out-Null }
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
    Write-Host "  shortcut: $lnkPath"
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

# WSL2 check.
Write-Host ''
$wsl = Get-Command wsl.exe -ErrorAction SilentlyContinue
$wslReady = $false
if ($wsl) {
    $status = & $wsl.Source --status 2>&1 | Out-String
    $wslReady = ($LASTEXITCODE -eq 0)
}
if ($wslReady) {
    Write-Host 'WSL2 is available. Open the app and press "Set up runtime".' -ForegroundColor Green
} else {
    Write-Host 'WSL2 does not look ready on this machine.' -ForegroundColor Yellow
    Write-Host 'The app needs WSL2 to run the real tools. See docs/PREREQUISITES.md.'
    $enableScript = Join-Path $PSScriptRoot '..\enable-wsl.ps1'
    if (Test-Path $enableScript) {
        Write-Host "To enable it later, run (as administrator): $enableScript"
    }
}

if (-not $Quiet) {
    Write-Host ''
    Write-Host "Installed. Launch it from the Start Menu: $AppName" -ForegroundColor Green
}

<#
    Uninstall Kali Linux Windows Substitute for the current user.

    Removes the program files, the Start Menu shortcut and the uninstall entry.
    It asks separately whether to remove the app's private WSL2 distribution.

    It never runs `wsl --shutdown` and never touches any other distribution.
#>
[CmdletBinding()]
param(
    [switch]$RemoveRuntime
)

$ErrorActionPreference = 'Continue'
Set-StrictMode -Version Latest

$AppName    = 'Kali Linux Windows Substitute'
$FolderName = 'KaliWindowsSubstitute'
$Target     = Join-Path $env:LOCALAPPDATA "Programs\$FolderName"
# The private runtime is a WSL2 distribution owned by the app. Its name is
# fixed in server/config.py (KWS_DISTRO, default "KaliSubstitute"), not the
# app folder name.
$RuntimeDistro = 'KaliSubstitute'

Write-Host "Uninstalling $AppName" -ForegroundColor Green

Get-Process -Name $FolderName -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

if (Test-Path $Target) {
    Remove-Item -Path $Target -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "  removed $Target"
}

$lnkPath = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\$AppName.lnk"
if (Test-Path $lnkPath) {
    Remove-Item $lnkPath -Force -ErrorAction SilentlyContinue
    Write-Host '  removed Start Menu shortcut'
}

$uninstallKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\$FolderName"
if (Test-Path $uninstallKey) {
    Remove-Item $uninstallKey -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host '  removed uninstall entry'
}

$dataDir = Join-Path $env:LOCALAPPDATA $DotFolder
if (Test-Path $dataDir) {
    Remove-Item -Path $dataDir -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "  removed user data ($dataDir)"
}

# The private runtime is a WSL2 distribution named after the folder.
if ($RemoveRuntime) {
    $remove = $true
} else {
    $answer = Read-Host 'Remove the private WSL2 runtime distribution as well? (y/N)'
    $RemoveRuntime = ($answer -match '^(y|yes)$')
}
if ($RemoveRuntime) {
    $wsl = Get-Command wsl.exe -ErrorAction SilentlyContinue
    if ($wsl) {
        & $wsl.Source --unregister $DotFolder 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  removed the $DotFolder runtime"
        } else {
            Write-Host "  runtime '$DotFolder' was not present"
        }
    }
}
Write-Host 'Uninstall complete.' -ForegroundColor Green

<#
    Enable the Windows features Kali Linux Windows Substitute needs.

    Run from an *elevated* PowerShell:

        powershell -ExecutionPolicy Bypass -File enable-wsl.ps1

    This turns on the Virtual Machine Platform and the Windows Subsystem for
    Linux, then tells you to reboot. It does not install a distribution and it
    does not install a kernel on your behalf.
#>
[CmdletBinding()]
param(
    [switch]$NoRebootPrompt
)

$ErrorActionPreference = 'Stop'

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Please run this script from an elevated (administrator) PowerShell.'
}

Write-Host 'Enabling Windows features for WSL2...' -ForegroundColor Green
foreach ($feature in @('Microsoft-Windows-Subsystem-Linux', 'VirtualMachinePlatform')) {
    Write-Host "  enabling $feature"
    Enable-WindowsOptionalFeature -Online -FeatureName $feature -All -NoRestart | Out-Null
}

Write-Host ''
Write-Host 'Windows features enabled.' -ForegroundColor Green
Write-Host 'Updating the WSL kernel (if wsl.exe is present)...'
$wsl = Get-Command wsl.exe -ErrorAction SilentlyContinue
if ($wsl) {
    try { & $wsl.Source --update 2>&1 | Write-Host } catch { Write-Host '  (skipped: wsl --update failed)' }
} else {
    Write-Host '  wsl.exe not found yet - it appears after the reboot.'
}

Write-Host ''
Write-Host 'A reboot is required before WSL2 will work. Restart Windows, then'
Write-Host 'launch the app and press "Set up runtime".'

if (-not $NoRebootPrompt) {
    $answer = Read-Host 'Reboot now? (y/N)'
    if ($answer -match '^[Yy]$') { Restart-Computer }
}

<#
    Enable the Windows features Kali Linux Windows Substitute needs.

    Run from an *elevated* PowerShell:

        powershell -ExecutionPolicy Bypass -File enable-wsl.ps1

    The feature logic lives in Prereqs.ps1, the same script the setup wizard
    uses, so there is only one implementation. This script is copied into the
    installed app folder next to Prereqs.ps1; in the source tree Prereqs.ps1 is
    in setup\. It calls Prereqs.ps1 with -Wsl and then offers to reboot.
    It does not install a distribution and it does not install a kernel.

    Prereqs.ps1 exit 3010 means "enabled, restart needed"; any other non-zero
    exit code is a failure and is reported.
#>
[CmdletBinding()]
param(
    [switch]$NoRebootPrompt
)

$ErrorActionPreference = 'Stop'

$prereqs = $null
foreach ($candidate in @((Join-Path $PSScriptRoot 'Prereqs.ps1'), (Join-Path $PSScriptRoot 'setup\Prereqs.ps1'))) {
    if (Test-Path -LiteralPath $candidate) { $prereqs = $candidate; break }
}
if (-not $prereqs) {
    throw "Prereqs.ps1 not found next to this script or in setup\ under $PSScriptRoot"
}

Write-Host 'Enabling Windows features for WSL2...' -ForegroundColor Green
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $prereqs -Wsl
$code = $LASTEXITCODE
if ($code -ne 0 -and $code -ne 3010) {
    throw "Enabling WSL2 failed (exit code $code). Run this from an elevated PowerShell."
}

if ($code -eq 3010) {
    Write-Host ''
    Write-Host 'A reboot is required before WSL2 will work. Restart Windows, then'
    Write-Host 'launch the app and press "Set up runtime".'
    if (-not $NoRebootPrompt) {
        $answer = Read-Host 'Reboot now? (y/N)'
        if ($answer -match '^[Yy]$') { Restart-Computer }
    }
} else {
    Write-Host 'WSL2 features are in place. No restart is needed.' -ForegroundColor Green
}

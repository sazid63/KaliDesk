<#
    Install prerequisites for Kali Linux Windows Substitute.

    This script is launched elevated (with a UAC prompt) by the setup wizard, or
    by hand from an administrator PowerShell.

    -Wsl      enable the two Windows features WSL2 needs
              (Virtual Machine Platform + Windows Subsystem for Linux)
    -Python   install Python 3 with winget if it is missing
              (optional: only needed to run from source or build the runtime)

    It changes only Windows features and, when asked, installs Python. It never
    creates, terminates or unregisters a WSL distribution and never runs
    `wsl --shutdown`.
#>
[CmdletBinding()]
param(
    [switch]$Wsl,
    [switch]$Python
)

$ErrorActionPreference = 'Continue'
Set-StrictMode -Version Latest

function Test-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-Administrator)) {
    Write-Warning 'This step needs administrator rights. Re-run from an elevated PowerShell.'
    exit 2
}

$rebootNeeded = $false

if ($Wsl) {
    foreach ($feature in @('VirtualMachinePlatform', 'Microsoft-Windows-Subsystem-Linux')) {
        $state = $null
        try {
            $state = (Get-WindowsOptionalFeature -Online -FeatureName $feature -ErrorAction Stop).State
        } catch {
            Write-Warning "could not query feature '$feature': $($_.Exception.Message)"
        }
        if ($state -eq 'Enabled') {
            Write-Host "  $feature already enabled"
            continue
        }
        Write-Host "  enabling $feature ..."
        try {
            Enable-WindowsOptionalFeature -Online -FeatureName $feature -All -NoRestart -ErrorAction Stop | Out-Null
            $rebootNeeded = $true
        } catch {
            Write-Warning "failed to enable '$feature': $($_.Exception.Message)"
        }
    }

    $wsl = Get-Command wsl.exe -ErrorAction SilentlyContinue
    if ($wsl) {
        & $wsl.Source --set-default-version 2 2>&1 | Out-Null
    }
}

if ($Python) {
    $hasPython = (Get-Command python -ErrorAction SilentlyContinue) -or (Get-Command py -ErrorAction SilentlyContinue)
    if ($hasPython) {
        Write-Host '  Python is already installed'
    } else {
        $winget = Get-Command winget -ErrorAction SilentlyContinue
        if ($winget) {
            Write-Host '  installing Python 3 with winget ...'
            & $winget.Source install --id Python.Python.3.12 -e --source winget `
                --accept-package-agreements --accept-source-agreements
        } else {
            Write-Warning 'winget was not found. Install Python 3 from https://www.python.org/downloads/'
        }
    }
}

if ($rebootNeeded) {
    Write-Host ''
    Write-Host 'A restart is required before WSL2 can run the Linux tools.' -ForegroundColor Yellow
}
exit 0

<#
    Install prerequisites for Kali Linux Windows Substitute.

    This script is launched elevated (with a UAC prompt) by the setup wizard, or
    by hand from an administrator PowerShell (or through enable-wsl.ps1).

    -Wsl      enable the two Windows features WSL2 needs
              (Virtual Machine Platform + Windows Subsystem for Linux)
    -Python   install Python 3 with winget if it is missing
              (optional: only needed to run from source or build the runtime)

    Exit codes:
      0     everything requested is in place
      1     at least one step failed (each failure is listed at the end)
      3010  everything worked, but Windows must restart before WSL2 runs

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

. (Join-Path $PSScriptRoot 'Common.ps1')

$failures = New-Object System.Collections.Generic.List[string]

if (-not (Test-Administrator)) {
    Write-Warning 'This step needs administrator rights. Re-run from an elevated PowerShell.'
    exit 1
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
            $failures.Add("could not enable '$feature': $($_.Exception.Message)")
        }
    }

    # Needs the features to be active, so it waits for the restart.
    $wsl = Get-Command wsl.exe -ErrorAction SilentlyContinue
    if ($wsl -and -not $rebootNeeded) {
        & $wsl.Source --set-default-version 2 *> $null
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "wsl --set-default-version 2 returned $LASTEXITCODE. The app can still set this up later."
        }
    }
}

if ($Python) {
    if (Test-PythonInstalled) {
        Write-Host '  Python is already installed'
    } else {
        $winget = Get-Command winget -ErrorAction SilentlyContinue
        if (-not $winget) {
            $failures.Add('winget was not found, so Python 3 was not installed. Get it from https://www.python.org/downloads/')
        } else {
            Write-Host '  installing Python 3 with winget ...'
            & $winget.Source install --id Python.Python.3.12 -e --source winget `
                --accept-package-agreements --accept-source-agreements
            if ($LASTEXITCODE -ne 0) {
                $failures.Add("winget could not install Python 3 (exit code $LASTEXITCODE)")
            }
        }
    }
}

if ($rebootNeeded) {
    Write-Host ''
    Write-Host 'A restart is required before WSL2 can run the Linux tools.' -ForegroundColor Yellow
}

if ($failures.Count -gt 0) {
    Write-Host ''
    foreach ($f in $failures) { Write-Host "FAILED: $f" -ForegroundColor Red }
    exit 1
}
if ($rebootNeeded) { exit 3010 }
exit 0

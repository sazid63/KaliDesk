<#
    Uninstall Kali Linux Windows Substitute for the current user.

    Order of work:
      1. Refuse to touch any folder without the install marker, or a protected folder.
      2. Ask the app to close (it is force-closed only after you agree).
      3. Ask whether to remove the private WSL2 runtime (default No).
      4. Ask whether to delete your data (findings, evidence, secrets; default No).
      5. If the runtime is removed: wsl --unregister runs BEFORE any data is deleted.
      6. Delete user data. If the runtime is kept, its \wsl folder is excluded.
      7. Delete the app folder, the Start Menu shortcut and the uninstall entry.
      8. Check every path afterwards and report what could not be removed.

    The private runtime is the WSL2 distribution named by $env:KWS_DISTRO
    (default "KaliSubstitute", the same default as server/config.py). Only that
    distribution is ever unregistered. wsl --shutdown is never run.
#>
[CmdletBinding()]
param(
    [switch]$RemoveRuntime,
    [switch]$RemoveUserData
)

$ErrorActionPreference = 'Continue'
Set-StrictMode -Version Latest

. (Join-Path $PSScriptRoot 'Common.ps1')
Add-Type -AssemblyName System.Windows.Forms

$RuntimeDistro = if ([string]::IsNullOrWhiteSpace($env:KWS_DISTRO)) { 'KaliSubstitute' } else { $env:KWS_DISTRO.Trim() }
$uninstallKey  = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\$FolderName"
$dataDir       = Join-Path $env:LOCALAPPDATA $FolderName
$wslDir        = Join-Path $dataDir 'wsl'

# The folder the app was installed into: the location recorded at install time,
# or the default if the record is missing.
$Target = Join-Path $env:LOCALAPPDATA "Programs\$FolderName"
$record = Get-ItemProperty -Path $uninstallKey -ErrorAction SilentlyContinue
if ($record -and $record.PSObject.Properties['InstallLocation'] -and $record.InstallLocation) {
    $Target = $record.InstallLocation
}
$Target = $Target.TrimEnd('\')

$failures = New-Object System.Collections.Generic.List[string]
$interactive = [Environment]::UserInteractive

Write-Host "Uninstalling $AppName" -ForegroundColor Green

# 1. Safety checks before anything is closed or deleted.
if (Test-ProtectedPath $Target) {
    Write-Host "  refusing to remove '$Target': it is a protected location." -ForegroundColor Red
    exit 1
}
$markerPath = Join-Path $Target $MarkerName
if ((Test-Path -LiteralPath $Target) -and -not (Test-Path -LiteralPath $markerPath)) {
    Write-Host "  refusing to remove '$Target': it has no install marker ($MarkerName)." -ForegroundColor Red
    Write-Host '  Nothing was deleted. Remove the folder by hand if you are sure it is the app.' -ForegroundColor Yellow
    exit 1
}

# 2. Close the app.
if (-not (Stop-AppIfRunning)) {
    Write-Host 'Uninstall cancelled: close the app and run the uninstaller again.' -ForegroundColor Yellow
    exit 1
}

# 3. Runtime question first.
if ($RemoveRuntime) {
    $removeRuntime = $true
} elseif ($interactive) {
    $answer = [System.Windows.Forms.MessageBox]::Show(
        "Also remove the private WSL2 runtime ('$RuntimeDistro')?`n`nChoose No to keep it. A reinstall will reuse it.",
        $AppName, 'YesNo', 'Question', 'Button2')
    $removeRuntime = ($answer -eq 'Yes')
} else {
    $removeRuntime = $false
}

# 4. Data question.
$dataExists = Test-Path -LiteralPath $dataDir
$removeData = $false
if ($dataExists) {
    if ($RemoveUserData) {
        $removeData = $true
    } elseif ($interactive) {
        $answer = [System.Windows.Forms.MessageBox]::Show(
            "Also delete your findings, evidence and stored secrets in:`n$dataDir`n`nThis cannot be undone. Choose No to keep them.",
            $AppName, 'YesNo', 'Warning', 'Button2')
        $removeData = ($answer -eq 'Yes')
    }
}

# 5. Unregister the runtime BEFORE its files are deleted. Only our distribution.
$runtimeRemoved = $false
if ($removeRuntime) {
    $wsl = Get-Command wsl.exe -ErrorAction SilentlyContinue
    if (-not $wsl) {
        Write-Host "  wsl.exe was not found; runtime '$RuntimeDistro' was not removed" -ForegroundColor Yellow
    } else {
        & $wsl.Source --unregister $RuntimeDistro | Out-Null
        if ($LASTEXITCODE -eq 0) {
            $runtimeRemoved = $true
            Write-Host "  removed the $RuntimeDistro runtime"
        } else {
            # Not present, or still in use. Its disk files are kept so WSL's own
            # registry and the disk never disagree.
            Write-Host "  runtime '$RuntimeDistro' was not removed (not present, or wsl exit code $LASTEXITCODE)" -ForegroundColor Yellow
            Write-Host "  its files in $wslDir were kept. Run: wsl --unregister $RuntimeDistro" -ForegroundColor Yellow
        }
    }
}

# 6. User data. With the runtime kept, the \wsl folder is excluded.
if ($removeData) {
    # \wsl is never touched here: it is the runtime's disk, handled below.
    foreach ($item in @(Get-ChildItem -LiteralPath $dataDir -Force -ErrorAction SilentlyContinue)) {
        if ($item.FullName -eq $wslDir) { continue }
        Remove-Item -LiteralPath $item.FullName -Recurse -Force -ErrorAction SilentlyContinue
    }
    $left = @(Get-ChildItem -LiteralPath $dataDir -Force -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -ne $wslDir })
    if ($left.Count -gt 0) {
        $failures.Add("user data could not be fully removed: $dataDir")
    } else {
        Write-Host "  removed user data ($dataDir)"
    }
} elseif ($dataExists) {
    Write-Host "  kept user data ($dataDir)"
}

if ($runtimeRemoved -and (Test-Path -LiteralPath $wslDir)) {
    Remove-Item -LiteralPath $wslDir -Recurse -Force -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $wslDir) { $failures.Add("runtime files could not be removed: $wslDir") }
}
if ((Test-Path -LiteralPath $dataDir) -and
    @(Get-ChildItem -LiteralPath $dataDir -Force -ErrorAction SilentlyContinue).Count -eq 0) {
    Remove-Item -LiteralPath $dataDir -Force -ErrorAction SilentlyContinue
}

# 7. The app folder, then the shortcut and the uninstall entry.
$selfInside = $PSCommandPath -and
    $PSCommandPath.StartsWith($Target + '\', [StringComparison]::OrdinalIgnoreCase)
if (Test-Path -LiteralPath $Target) {
    Get-ChildItem -LiteralPath $Target -Force -ErrorAction SilentlyContinue |
        ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction SilentlyContinue }
    if ($selfInside) {
        # This script lives in the folder and cannot delete itself while it runs.
        # A detached cmd removes the folder a few seconds after this window closes.
        $cmdArgs = "/c ping -n 4 127.0.0.1 >nul & rmdir /s /q `"$Target`""
        Start-Process -FilePath 'cmd.exe' -ArgumentList $cmdArgs -WindowStyle Hidden
        Write-Host "  the app folder is removed as this uninstaller closes"
    } elseif (Test-Path -LiteralPath $Target) {
        $failures.Add("app folder could not be fully removed (files in use?): $Target")
    } else {
        Write-Host "  removed $Target"
    }
}

$lnkPath = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\$AppName.lnk"
if (Test-Path -LiteralPath $lnkPath) {
    Remove-Item -LiteralPath $lnkPath -Force -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $lnkPath) { $failures.Add("Start Menu shortcut could not be removed: $lnkPath") }
    else { Write-Host '  removed Start Menu shortcut' }
}

if (Test-Path -LiteralPath $uninstallKey) {
    Remove-Item -LiteralPath $uninstallKey -Recurse -Force -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $uninstallKey) { $failures.Add("uninstall entry could not be removed: $uninstallKey") }
    else { Write-Host '  removed uninstall entry' }
}

# 8. Report.
if ($failures.Count -gt 0) {
    Write-Host ''
    Write-Host 'Uninstall finished with problems:' -ForegroundColor Red
    foreach ($f in $failures) { Write-Host "  FAILED: $f" -ForegroundColor Red }
    exit 1
}
Write-Host 'Uninstall complete.' -ForegroundColor Green
exit 0

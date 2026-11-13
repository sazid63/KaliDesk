<#
    Install Kali Linux Windows Substitute for the current user.

    - Installs into <InstallDir>\KaliWindowsSubstitute. InstallDir is the parent
      folder you choose (default %LOCALAPPDATA%\Programs), so the app always lives
      in its own KaliWindowsSubstitute folder and never in a user folder.
    - Writes an install marker. Uninstall only deletes folders that have it.
    - On upgrade, removes the old app files first (keeps Uninstall.ps1 and the
      marker), then copies the new ones.
    - Copies the uninstaller, Prereqs.ps1, enable-wsl.ps1, INSTALL.txt and the
      shared Common.ps1 into the installed folder.
    - Creates a Start Menu shortcut and registers an uninstall entry under HKCU.
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

. (Join-Path $PSScriptRoot 'Common.ps1')

$ExeName      = "$FolderName.exe"
$uninstallKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\$FolderName"

if ([string]::IsNullOrWhiteSpace($InstallDir)) {
    $InstallDir = Join-Path $env:LOCALAPPDATA 'Programs'
}
$Target = Join-Path ([Environment]::ExpandEnvironmentVariables($InstallDir.Trim())) $FolderName

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

# Never install over a user folder.
if (Test-ProtectedPath $Target) {
    Write-Step "Setup refused: '$Target' is a protected location. Choose another folder." ([ConsoleColor]::Red)
    exit 1
}

# An existing folder is only reused when this installer made it: it has the
# marker, or the uninstall entry records it as the install location (installs
# made before the marker existed). Anything else is left alone.
$record = Get-ItemProperty -Path $uninstallKey -ErrorAction SilentlyContinue
$ownedByRecord = [bool]($record -and $record.PSObject.Properties['InstallLocation'] -and
                        ($record.InstallLocation -eq $Target))
$markerPath = Join-Path $Target $MarkerName
if ((Test-Path -LiteralPath $Target) -and -not (Test-Path -LiteralPath $markerPath) -and -not $ownedByRecord) {
    $existing = @(Get-ChildItem -LiteralPath $Target -Force -ErrorAction SilentlyContinue)
    if ($existing.Count -gt 0) {
        Write-Step "Setup refused: '$Target' already exists and was not created by this installer." ([ConsoleColor]::Red)
        exit 1
    }
}

# Close a running copy so files are not locked (asks first; see Stop-AppIfRunning).
if (-not (Stop-AppIfRunning -Quiet:$Quiet)) {
    Write-Step 'Setup cancelled: close the app and run setup again.' ([ConsoleColor]::Yellow)
    exit 1
}

New-Item -ItemType Directory -Path $Target -Force | Out-Null

# Upgrade: remove the previous app files. The uninstaller and the marker stay.
$keep = @('Uninstall.ps1', $MarkerName)
$oldFiles = @(Get-ChildItem -LiteralPath $Target -Force | Where-Object { $_.Name -notin $keep })
foreach ($old in $oldFiles) {
    Remove-Item -LiteralPath $old.FullName -Recurse -Force -ErrorAction SilentlyContinue
}
$stuck = @(Get-ChildItem -LiteralPath $Target -Force | Where-Object { $_.Name -notin $keep })
if ($stuck.Count -gt 0) {
    Write-Step "Setup stopped: could not remove old files in $Target (some may be in use): $($stuck.Name -join ', ')" ([ConsoleColor]::Red)
    exit 1
}

# The marker goes in before the copy, so a copy that fails part way still leaves
# a folder the uninstaller will accept.
Set-Content -LiteralPath $markerPath -Encoding UTF8 -Value @(
    "$AppName",
    'version=1.5.0',
    "installed=$((Get-Date).ToString('o'))",
    "folder=$Target"
)

Copy-Item -Path (Join-Path $AppSource '*') -Destination $Target -Recurse -Force

# Files the installed folder needs later: the uninstaller, the shared helpers,
# the WSL2 tools and the install notes. The setup folder is a temp folder that is
# deleted when setup finishes, so nothing can point back at it.
foreach ($name in @('Uninstall.ps1', 'Common.ps1', 'Prereqs.ps1', 'enable-wsl.ps1', 'INSTALL.txt')) {
    $src = Join-Path $PSScriptRoot $name
    if (-not (Test-Path -LiteralPath $src)) { throw "installer file missing: $src" }
    Copy-Item -LiteralPath $src -Destination (Join-Path $Target $name) -Force
}

foreach ($doc in @('LICENSE', 'THIRD_PARTY_NOTICES.md')) {
    if (-not (Test-Path -LiteralPath (Join-Path $Target $doc))) {
        Write-Warning "$doc was not found in the application files"
    }
}

# Start Menu shortcut.
$startMenu = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'
$lnkPath = Join-Path $startMenu "$AppName.lnk"
$exePath = Join-Path $Target $ExeName
if (Test-Path -LiteralPath $exePath) {
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
New-Item -Path $uninstallKey -Force | Out-Null
Set-ItemProperty -Path $uninstallKey -Name 'DisplayName'     -Value $AppName
Set-ItemProperty -Path $uninstallKey -Name 'DisplayVersion'  -Value '1.5.0'
Set-ItemProperty -Path $uninstallKey -Name 'Publisher'       -Value 'Kali Linux Windows Substitute contributors'
Set-ItemProperty -Path $uninstallKey -Name 'InstallLocation' -Value $Target
Set-ItemProperty -Path $uninstallKey -Name 'NoModify'        -Value 1 -Type DWord
Set-ItemProperty -Path $uninstallKey -Name 'NoRepair'        -Value 1 -Type DWord
$uninstallScript = Join-Path $Target 'Uninstall.ps1'
$uninstallCmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$uninstallScript`""
Set-ItemProperty -Path $uninstallKey -Name 'UninstallString' -Value $uninstallCmd
Write-Step "  uninstall entry: $uninstallKey"

# WSL2 check (message only - it never enables anything by itself).
Write-Step ''
$wsl = Get-Command wsl.exe -ErrorAction SilentlyContinue
$wslReady = $false
if ($wsl) {
    try {
        & $wsl.Source --status 2>&1 | Out-Null
        $wslReady = ($LASTEXITCODE -eq 0)
    } catch {
        $wslReady = $false
    }
}
if ($wslReady) {
    Write-Step 'WSL2 is available. Open the app and press "Set up runtime".' ([ConsoleColor]::Green)
} else {
    Write-Step 'WSL2 does not look ready on this machine.' ([ConsoleColor]::Yellow)
    Write-Step "The app needs WSL2 to run the real tools. See INSTALL.txt in $Target."
    Write-Step "To enable it, run enable-wsl.ps1 from an elevated PowerShell:"
    Write-Step "  powershell -ExecutionPolicy Bypass -File `"$(Join-Path $Target 'enable-wsl.ps1')`""
}

if ($Launch -and (Test-Path -LiteralPath $exePath)) {
    Write-Step 'Launching the app ...' ([ConsoleColor]::Green)
    Start-Process -FilePath $exePath -WorkingDirectory $Target
}

Write-Step "Installed. Launch it from the Start Menu: $AppName" ([ConsoleColor]::Green)
exit 0

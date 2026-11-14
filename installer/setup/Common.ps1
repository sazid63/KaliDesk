<#
    Shared helpers for the Kali Linux Windows Substitute installer scripts.

    Dot-sourced by Install.ps1, Uninstall.ps1, Wizard.ps1 and Prereqs.ps1 (and
    by enable-wsl.ps1 through Prereqs.ps1). It is staged next to them and copied
    into the installed folder, so the uninstaller can use it later.
#>

$AppName    = 'Kali Linux Windows Substitute'
$FolderName = 'KaliWindowsSubstitute'

# Written into the app folder at install time. Uninstall refuses to delete any
# folder that does not contain it, so a wrong or hand-made path can never take
# user files with it.
$MarkerName = 'kws-install.marker'

function Get-AppProcess {
    Get-Process -Name $FolderName -ErrorAction SilentlyContinue
}

# Ask the running app to close. It is only force-closed after the user agrees in
# a dialog. With -Quiet nobody can be asked, so it returns $false instead.
function Stop-AppIfRunning {
    param([switch]$Quiet)
    if (-not (Get-AppProcess)) { return $true }
    foreach ($p in @(Get-AppProcess)) { [void]$p.CloseMainWindow() }
    $deadline = (Get-Date).AddSeconds(10)
    while ((Get-AppProcess) -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 500 }
    if (-not (Get-AppProcess)) { return $true }
    if ($Quiet) { return $false }
    Add-Type -AssemblyName System.Windows.Forms
    $answer = [System.Windows.Forms.MessageBox]::Show(
        "$AppName is still running. Force it to close now? Unsaved work in it will be lost.",
        $AppName, 'YesNo', 'Warning', 'Button2')
    if ($answer -ne 'Yes') { return $false }
    Get-AppProcess | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 500
    return $true
}

function Test-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

# True when the folder is one the installer must never delete: the user's
# profile, its well-known folders, Program Files, Windows, a drive root, or
# anything under Windows / Program Files.
function Test-ProtectedPath {
    param([Parameter(Mandatory = $true)][string]$Path)
    $candidate = [IO.Path]::GetFullPath($Path).TrimEnd('\')
    $protected = @(
        ($env:USERPROFILE),
        ($env:LOCALAPPDATA),
        ($env:APPDATA),
        ($env:ProgramData),
        ($env:ProgramFiles),
        (${env:ProgramFiles(x86)}),
        ($env:WINDIR),
        ($env:SystemDrive + '\Users'),
        ($env:SystemDrive + '\Windows'),
        ([Environment]::GetFolderPath('MyDocuments')),
        ([Environment]::GetFolderPath('Desktop')),
        ([Environment]::GetFolderPath('UserProfile')),
        (Join-Path $env:USERPROFILE 'Documents'),
        (Join-Path $env:USERPROFILE 'Desktop'),
        (Join-Path $env:USERPROFILE 'Downloads')
    ) | Where-Object { $_ } | ForEach-Object { [IO.Path]::GetFullPath($_).TrimEnd('\') }

    if ($candidate.Length -le 3) { return $true }          # a drive root such as C:\
    if ($protected -contains $candidate) { return $true }
    foreach ($root in @($env:WINDIR, $env:ProgramFiles, ${env:ProgramFiles(x86)})) {
        if (-not $root) { continue }
        $prefix = [IO.Path]::GetFullPath($root).TrimEnd('\') + '\'
        if ($candidate.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) { return $true }
    }
    return $false
}

# True when a usable Python 3 is on PATH. The Microsoft Store alias in
# WindowsApps exits with 9009 when Python is not really installed, so those
# paths are skipped and every candidate must answer "--version" with exit 0.
function Test-PythonInstalled {
    foreach ($name in @('python', 'py')) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if (-not $cmd) { continue }
        if ($cmd.Source -match '\\WindowsApps\\') { continue }
        try {
            & $cmd.Source --version *> $null
            if ($LASTEXITCODE -eq 0) { return $true }
        } catch {
            continue
        }
    }
    return $false
}

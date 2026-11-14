<#
    Kali Linux Windows Substitute - click-through setup wizard.

    Flow (like a normal Windows installer):

      1. Welcome / prerequisites - checkboxes to enable WSL2 and, optionally,
         install Python 3.
      2. Install location - choose the parent folder. The app goes into
         <folder>\KaliWindowsSubstitute. Optionally point at a runtime image.
      3. Install - copies the app, creates the shortcut and uninstall entry.
      4. Finish - launches the app.

    Every step delegates to scripts in this folder:
      Prereqs.ps1   Windows features / optional software (elevated)
      Install.ps1   the actual per-user install (silent core)

    Quiet mode (-Quiet) skips the UI and just installs, for automation.

    Exit codes (read by SetupStub.cs):
      0     installed
      1     the install failed
      1223  the wizard was cancelled before installing (ERROR_CANCELLED)
#>
[CmdletBinding()]
param(
    [string]$AppSource = '',
    [string]$InstallDir = '',
    [switch]$Quiet,
    [switch]$NoLaunch
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Here          = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $Here 'Common.ps1')

$InstallScript = Join-Path $Here 'Install.ps1'
$PrereqScript  = Join-Path $Here 'Prereqs.ps1'
$CancelledExit = 1223

if ([string]::IsNullOrWhiteSpace($AppSource)) {
    $AppSource = Join-Path (Split-Path -Parent $Here) 'app'
}
# InstallDir is the PARENT folder; Install.ps1 adds \KaliWindowsSubstitute.
if ([string]::IsNullOrWhiteSpace($InstallDir)) {
    $InstallDir = Join-Path $env:LOCALAPPDATA 'Programs'
    # Upgrades default to the folder the app was installed into last time.
    $previous = Get-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\$FolderName" -ErrorAction SilentlyContinue
    if ($previous -and $previous.PSObject.Properties['InstallLocation'] -and $previous.InstallLocation) {
        $InstallDir = Split-Path -Parent $previous.InstallLocation
    }
}

# Exit code for the whole wizard. Cancelling (or closing the window) keeps the
# distinct "cancelled" code; a finished install sets 0 or 1.
$script:exitCode = $CancelledExit

function Test-WslReady {
    $wsl = Get-Command wsl.exe -ErrorAction SilentlyContinue
    if (-not $wsl) { return $false }
    try {
        & $wsl.Source --status *> $null
        return ($LASTEXITCODE -eq 0)
    } catch {
        # wsl.exe writing to stderr is a terminating error under -ErrorAction Stop.
        return $false
    }
}

# Runs Prereqs.ps1 and returns its exit code (0 ok, 1 failed, 3010 restart needed,
# 1223 the UAC prompt was declined). The caller reads the code; the window
# is not relied on for the result.
function Invoke-Prereqs {
    param([bool]$Wsl, [bool]$Python)
    $extra = @()
    if ($Wsl) { $extra += '-Wsl' }
    if ($Python) { $extra += '-Python' }
    if ($extra.Count -eq 0) { return 0 }
    if (-not (Test-Path $PrereqScript)) { return 1 }

    $argList = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PrereqScript`"") + $extra
    if (Test-Administrator) {
        # Out-Host keeps the child's console text out of the returned value.
        & powershell.exe @argList | Out-Host
        return $LASTEXITCODE
    }
    try {
        $proc = Start-Process -FilePath 'powershell.exe' -Verb RunAs -Wait -PassThru -ArgumentList $argList
        return $proc.ExitCode
    } catch [System.ComponentModel.Win32Exception] {
        # 1223 = the user declined the elevation prompt.
        return $CancelledExit
    } catch {
        return 1
    }
}

# ---------------------------------------------------------------------------
# Headless / quiet path (automation, or a session without a GUI).
# ---------------------------------------------------------------------------
if ($Quiet -or -not [Environment]::UserInteractive) {
    $coreArgs = @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$InstallScript`"",
        '-AppSource', "`"$AppSource`"", '-InstallDir', "`"$InstallDir`"", '-Quiet'
    )
    if (-not $NoLaunch) { $coreArgs += '-Launch' }
    & powershell.exe @coreArgs
    exit $LASTEXITCODE
}

# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

$wslReady = Test-WslReady
$hasPython = Test-PythonInstalled

$form = New-Object System.Windows.Forms.Form
$form.Text = "$AppName - Setup"
$form.ClientSize = New-Object System.Drawing.Size(600, 440)
$form.StartPosition = 'CenterScreen'
$form.FormBorderStyle = 'FixedDialog'
$form.MaximizeBox = $false
$form.MinimizeBox = $false
$form.Font = New-Object System.Drawing.Font('Segoe UI', 9)

$title = New-Object System.Windows.Forms.Label
$title.Text = $AppName
$title.Font = New-Object System.Drawing.Font('Segoe UI', 14, [System.Drawing.FontStyle]::Bold)
$title.Location = New-Object System.Drawing.Point(16, 12)
$title.Size = New-Object System.Drawing.Size(560, 30)
$form.Controls.Add($title)

$subtitle = New-Object System.Windows.Forms.Label
$subtitle.Text = 'Runs the real Kali Linux security tools, inside a private WSL2 runtime.'
$subtitle.ForeColor = [System.Drawing.Color]::DimGray
$subtitle.Location = New-Object System.Drawing.Point(18, 44)
$subtitle.Size = New-Object System.Drawing.Size(560, 20)
$form.Controls.Add($subtitle)

function New-Page {
    $page = New-Object System.Windows.Forms.Panel
    $page.Location = New-Object System.Drawing.Point(12, 72)
    $page.Size = New-Object System.Drawing.Size(576, 300)
    $page.Visible = $false
    $form.Controls.Add($page)
    return $page
}

function New-Button {
    param([string]$Text, [int]$X, [int]$Y, [int]$W = 96)
    $b = New-Object System.Windows.Forms.Button
    $b.Text = $Text
    $b.Location = New-Object System.Drawing.Point($X, $Y)
    $b.Size = New-Object System.Drawing.Size($W, 30)
    return $b
}

# --- page 1: prerequisites -------------------------------------------------
$pagePrereq = New-Page

$lblPrereq = New-Object System.Windows.Forms.Label
$lblPrereq.Text = 'Before installing, choose which prerequisites to set up:'
$lblPrereq.Location = New-Object System.Drawing.Point(4, 4)
$lblPrereq.Size = New-Object System.Drawing.Size(560, 20)
$pagePrereq.Controls.Add($lblPrereq)

$chkWsl = New-Object System.Windows.Forms.CheckBox
$chkWsl.Text = 'Enable WSL2 (Virtual Machine Platform + Windows Subsystem for Linux)'
$chkWsl.Location = New-Object System.Drawing.Point(4, 34)
$chkWsl.Size = New-Object System.Drawing.Size(560, 22)
$chkWsl.Checked = -not $wslReady
if ($wslReady) { $chkWsl.Enabled = $false }
$pagePrereq.Controls.Add($chkWsl)

$lblWslState = New-Object System.Windows.Forms.Label
$lblWslState.ForeColor = [System.Drawing.Color]::DimGray
$lblWslState.Location = New-Object System.Drawing.Point(24, 58)
$lblWslState.Size = New-Object System.Drawing.Size(540, 20)
$lblWslState.Text = if ($wslReady) { 'Already available on this machine.' }
                    else { 'Needs administrator rights and a restart.' }
$pagePrereq.Controls.Add($lblWslState)

$chkPy = New-Object System.Windows.Forms.CheckBox
$chkPy.Text = 'Install Python 3 (optional - only to run from source or build the runtime)'
$chkPy.Location = New-Object System.Drawing.Point(4, 92)
$chkPy.Size = New-Object System.Drawing.Size(560, 22)
$chkPy.Checked = -not $hasPython
if ($hasPython) { $chkPy.Enabled = $false }
$pagePrereq.Controls.Add($chkPy)

$lblPyState = New-Object System.Windows.Forms.Label
$lblPyState.ForeColor = [System.Drawing.Color]::DimGray
$lblPyState.Location = New-Object System.Drawing.Point(24, 116)
$lblPyState.Size = New-Object System.Drawing.Size(540, 20)
$lblPyState.Text = if ($hasPython) { 'Python is already installed.' }
                   else { 'Installed with winget if available.' }
$pagePrereq.Controls.Add($lblPyState)

$btnNext = New-Button -Text 'Next >' -X 386 -Y 262
$btnCancel1 = New-Button -Text 'Cancel' -X 484 -Y 262
$pagePrereq.Controls.Add($btnNext)
$pagePrereq.Controls.Add($btnCancel1)

# --- page 2: install location ----------------------------------------------
$pageDir = New-Page

$lblDirIntro = New-Object System.Windows.Forms.Label
$lblDirIntro.Text = 'Choose the parent folder. The app is installed into a KaliWindowsSubstitute folder inside it.'
$lblDirIntro.Location = New-Object System.Drawing.Point(4, 4)
$lblDirIntro.Size = New-Object System.Drawing.Size(560, 20)
$pageDir.Controls.Add($lblDirIntro)

$txtDir = New-Object System.Windows.Forms.TextBox
$txtDir.Location = New-Object System.Drawing.Point(4, 30)
$txtDir.Size = New-Object System.Drawing.Size(468, 24)
$txtDir.Text = $InstallDir
$pageDir.Controls.Add($txtDir)

$btnBrowseDir = New-Button -Text 'Browse...' -X 478 -Y 29 -W 80
$pageDir.Controls.Add($btnBrowseDir)

$lblImg = New-Object System.Windows.Forms.Label
$lblImg.Text = 'Runtime image (optional). Point at a kalisub-rootfs.tar / .tar.gz if you already have one.'
$lblImg.Location = New-Object System.Drawing.Point(4, 76)
$lblImg.Size = New-Object System.Drawing.Size(560, 20)
$pageDir.Controls.Add($lblImg)

$txtImg = New-Object System.Windows.Forms.TextBox
$txtImg.Location = New-Object System.Drawing.Point(4, 100)
$txtImg.Size = New-Object System.Drawing.Size(468, 24)
$pageDir.Controls.Add($txtImg)

$btnBrowseImg = New-Button -Text 'Browse...' -X 478 -Y 99 -W 80
$pageDir.Controls.Add($btnBrowseImg)

$lblNote = New-Object System.Windows.Forms.Label
$lblNote.ForeColor = [System.Drawing.Color]::DimGray
$lblNote.Location = New-Object System.Drawing.Point(4, 136)
$lblNote.Size = New-Object System.Drawing.Size(560, 60)
$lblNote.Text = 'No image yet? Press ''Set up runtime'' in the app: it downloads and verifies the official Kali WSL image on first run (internet needed).'
$pageDir.Controls.Add($lblNote)

$btnBack = New-Button -Text '< Back' -X 190 -Y 262
$btnInstall = New-Button -Text 'Install' -X 386 -Y 262
$btnCancel2 = New-Button -Text 'Cancel' -X 484 -Y 262
$pageDir.Controls.Add($btnBack)
$pageDir.Controls.Add($btnInstall)
$pageDir.Controls.Add($btnCancel2)

# --- page 3: progress ------------------------------------------------------
$pageProgress = New-Page

$lblProgress = New-Object System.Windows.Forms.Label
$lblProgress.Text = 'Installing ...'
$lblProgress.Location = New-Object System.Drawing.Point(4, 4)
$lblProgress.Size = New-Object System.Drawing.Size(560, 20)
$pageProgress.Controls.Add($lblProgress)

$progressBar = New-Object System.Windows.Forms.ProgressBar
$progressBar.Location = New-Object System.Drawing.Point(4, 30)
$progressBar.Size = New-Object System.Drawing.Size(560, 20)
$progressBar.Style = 'Marquee'
$progressBar.MarqueeAnimationSpeed = 30
$pageProgress.Controls.Add($progressBar)

$txtLog = New-Object System.Windows.Forms.TextBox
$txtLog.Location = New-Object System.Drawing.Point(4, 58)
$txtLog.Size = New-Object System.Drawing.Size(560, 232)
$txtLog.Multiline = $true
$txtLog.ReadOnly = $true
$txtLog.ScrollBars = 'Vertical'
$txtLog.Font = New-Object System.Drawing.Font('Consolas', 8)
$pageProgress.Controls.Add($txtLog)

# --- page 4: finish --------------------------------------------------------
$pageFinish = New-Page

$lblDone = New-Object System.Windows.Forms.Label
$lblDone.Text = 'Installation complete.'
$lblDone.Font = New-Object System.Drawing.Font('Segoe UI', 12, [System.Drawing.FontStyle]::Bold)
$lblDone.Location = New-Object System.Drawing.Point(4, 10)
$lblDone.Size = New-Object System.Drawing.Size(560, 28)
$pageFinish.Controls.Add($lblDone)

$lblDoneNote = New-Object System.Windows.Forms.Label
$lblDoneNote.Location = New-Object System.Drawing.Point(4, 44)
$lblDoneNote.Size = New-Object System.Drawing.Size(560, 120)
$lblDoneNote.Text = "The app is installed. On first launch, press ""Set up runtime"" to create its private WSL2 environment."
$pageFinish.Controls.Add($lblDoneNote)

$chkLaunch = New-Object System.Windows.Forms.CheckBox
$chkLaunch.Text = "Launch $AppName now"
$chkLaunch.Location = New-Object System.Drawing.Point(4, 150)
$chkLaunch.Size = New-Object System.Drawing.Size(560, 22)
$chkLaunch.Checked = -not $NoLaunch
$pageFinish.Controls.Add($chkLaunch)

$btnFinish = New-Button -Text 'Finish' -X 468 -Y 262 -W 96
$pageFinish.Controls.Add($btnFinish)

# --- navigation ------------------------------------------------------------
function Show-Page {
    param([System.Windows.Forms.Panel]$Page)
    foreach ($p in @($pagePrereq, $pageDir, $pageProgress, $pageFinish)) {
        $p.Visible = $false
    }
    $Page.Visible = $true
}

$btnCancel1.Add_Click({ $form.Close() })
$btnCancel2.Add_Click({ $form.Close() })

$btnBrowseDir.Add_Click({
    $dlg = New-Object System.Windows.Forms.FolderBrowserDialog
    $dlg.Description = 'Select the parent folder for the app'
    if (Test-Path $txtDir.Text) { $dlg.SelectedPath = $txtDir.Text }
    if ($dlg.ShowDialog() -eq 'OK') { $txtDir.Text = $dlg.SelectedPath }
})

$btnBrowseImg.Add_Click({
    $dlg = New-Object System.Windows.Forms.OpenFileDialog
    $dlg.Title = 'Select a runtime image'
    $dlg.Filter = 'Runtime image (*.tar;*.tar.gz)|*.tar;*.tar.gz|All files (*.*)|*.*'
    if ($dlg.ShowDialog() -eq 'OK') { $txtImg.Text = $dlg.FileName }
})

$btnNext.Add_Click({
    $btnNext.Enabled = $false
    [System.Windows.Forms.Application]::DoEvents()
    try {
        $code = Invoke-Prereqs -Wsl $chkWsl.Checked -Python $chkPy.Checked
    } finally {
        $btnNext.Enabled = $true
    }
    if ($code -eq 3010) {
        [System.Windows.Forms.MessageBox]::Show(
            'WSL2 was enabled. Restart Windows before using the tools.', $AppName, 'OK', 'Information')
    } elseif ($code -eq $CancelledExit) {
        [System.Windows.Forms.MessageBox]::Show(
            'Administrator approval was declined, so the prerequisites were not changed. You can run enable-wsl.ps1 later.',
            $AppName, 'OK', 'Warning')
    } elseif ($code -ne 0) {
        [System.Windows.Forms.MessageBox]::Show(
            "The prerequisite step did not finish (exit code $code). The install can continue; run enable-wsl.ps1 from the app folder later.",
            $AppName, 'OK', 'Warning')
    }
    Show-Page -Page $pageDir
})

$btnBack.Add_Click({ Show-Page -Page $pagePrereq })

$btnInstall.Add_Click({
    $dir = $txtDir.Text.Trim()
    if ([string]::IsNullOrWhiteSpace($dir)) {
        [System.Windows.Forms.MessageBox]::Show('Please choose an install folder.', $AppName)
        return
    }
    $dir = [Environment]::ExpandEnvironmentVariables($dir)
    try {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    } catch {
        [System.Windows.Forms.MessageBox]::Show("Cannot use that folder: $($_.Exception.Message)", $AppName)
        return
    }
    $target = Join-Path $dir $FolderName

    Show-Page -Page $pageProgress
    $lblProgress.Text = "Installing to $target ..."
    $txtLog.Text = ''
    [System.Windows.Forms.Application]::DoEvents()

    $logFile = Join-Path $env:TEMP ("kws-install-" + [Guid]::NewGuid().ToString('N') + ".log")
    $coreArgs = @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$InstallScript`"",
        '-AppSource', "`"$AppSource`"", '-InstallDir', "`"$dir`"",
        '-LogFile', "`"$logFile`""
    )
    $img = $txtImg.Text.Trim()
    if (-not [string]::IsNullOrWhiteSpace($img)) {
        $coreArgs += @('-RuntimeImage', "`"$img`"")
    }

    $code = 1
    try {
        $proc = Start-Process -FilePath 'powershell.exe' -ArgumentList $coreArgs -Wait -PassThru -WindowStyle Hidden
        $code = $proc.ExitCode
    } catch {
        $txtLog.AppendText("ERROR: $($_.Exception.Message)`r`n")
    }
    if (Test-Path $logFile) {
        $txtLog.AppendText((Get-Content -Path $logFile -Raw))
        Remove-Item $logFile -Force -ErrorAction SilentlyContinue
    }
    $ok = ($code -eq 0)

    $progressBar.Style = 'Continuous'
    $progressBar.Value = 100
    $script:installedDir = $target
    $script:launchExe = Join-Path $target "$FolderName.exe"
    $script:exitCode = if ($ok) { 0 } else { 1 }

    if (-not $ok) {
        $lblDone.Text = 'Installation finished with errors.'
        $lblDoneNote.Text = "The install did not complete (exit code $code). See the log above."
    }
    if (-not (Test-WslReady)) {
        $lblDoneNote.Text += "`r`n`r`nWSL2 does not look ready yet. See INSTALL.txt in the app folder, then enable WSL2 and restart Windows before using the tools."
    }
    Show-Page -Page $pageFinish
})

$btnFinish.Add_Click({
    if ($chkLaunch.Checked -and $script:installedDir) {
        $exe = $script:launchExe
        if (Test-Path $exe) {
            Start-Process -FilePath $exe -WorkingDirectory $script:installedDir
        }
    }
    $form.Close()
})

$form.AcceptButton = $btnNext

Show-Page -Page $pagePrereq
[void]$form.ShowDialog()
exit $script:exitCode

# Installer

Two ways to install **Kali Linux Windows Substitute**:

1. **Portable / source** (recommended while the project is young): run
   `python app/main.py`. See the root `README.md`.
2. **Built installer**: `installer/build.ps1` produces
   `installer/dist/KaliWindowsSubstitute-Setup.exe`, a small self-extracting
   setup. The wizard asks for a parent folder (default
   `%LOCALAPPDATA%\Programs`); the app is installed into a
   `KaliWindowsSubstitute` folder inside it and an uninstall entry is
   registered. No admin rights are required for the install itself; enabling
   WSL2 (a one-time Windows feature) may require elevation.

## What the installer does

* Copies the app to `<chosen folder>\KaliWindowsSubstitute`. The chosen folder
  is the parent; a full path is not the install directory.
* Refuses protected locations (your profile and its well-known folders,
  Program Files, Windows, a drive root) and refuses a non-empty folder it did
  not create.
* Writes a `kws-install.marker` file into the install folder. Uninstall only
  deletes folders that contain this marker.
* Creates a Start Menu shortcut and a Windows uninstall entry.
* Optionally installs Python 3 (via winget) and enables WSL2. Python detection
  skips the Microsoft Store stub in `WindowsApps`.
* Does **not** silently create a WSL distribution. The app imports its own
  distribution the first time you press **Set up runtime**, and it only ever
  touches that one.

## What the installer never does

* It never runs `wsl --shutdown`.
* It never modifies Docker Desktop or any other WSL distribution.
* It never writes secrets to disk in plain text.

## Exit codes

* `Wizard.ps1` (and `SetupStub.cs`): `0` installed, `1` failed, `1223` cancelled.
* `Prereqs.ps1`: `0` done, `1` a step failed, `3010` done but a restart is needed.

## Building the installer

```powershell
# from the repository root, in PowerShell
./installer/build.ps1
```

Requirements on the build machine: Python 3.10+, PowerShell 5.1+, and the .NET
Framework C# compiler (`csc`, present on Windows 10/11). The build installs
`requirements-build.txt`, which pins PyInstaller and includes the runtime
requirements.

The build:

1. Checks that the installer's version matches `kws/__about__.py`.
2. Runs the headless self-check (`python app/main.py --check`).
3. Builds the app with PyInstaller, bundling only the runtime files the app
   reads, plus `ui/` and `catalog/`.
4. Stages the app with `LICENSE` and `THIRD_PARTY_NOTICES.md`, and zips it.
5. Compiles `SetupStub.cs` into `KaliWindowsSubstitute-Setup.exe`, embedding the zip.

## Uninstalling

`Settings > Apps > Kali Linux Windows Substitute > Uninstall`, or run
`installer/setup/Uninstall.ps1`. The uninstaller refuses to delete a folder
without the install marker, then:

1. Asks whether to remove the private WSL2 runtime. The default is **No**.
   If Yes, it unregisters only that distribution, before any data is deleted.
2. Asks whether to delete your user data (findings, evidence and stored
   secrets). The default is **No**.
3. Removes the program files, the Start Menu shortcut and the uninstall entry.

It never shuts down WSL as a whole.

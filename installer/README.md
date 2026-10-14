# Installer

Two ways to install **Kali Linux Windows Substitute**:

1. **Portable / source** (recommended while the project is young): run
   `python app/main.py`. See the root `README.md`.
2. **Built installer**: `installer/build.ps1` produces
   `installer/dist/KaliWindowsSubstitute-Setup.exe`, a small self-extracting
   setup that installs to `%LOCALAPPDATA%\Programs\KaliWindowsSubstitute` and
   registers an uninstall entry. No admin rights are required for the install
   itself; enabling WSL2 (a one-time Windows feature) may require elevation.

## What the installer does

* Copies the app to `%LOCALAPPDATA%\Programs\KaliWindowsSubstitute`.
* Creates a Start Menu shortcut and a Windows uninstall entry.
* Optionally checks WSL2 and offers to enable it.
* Does **not** silently create a WSL distribution. The app imports its own
  distribution the first time you press **Set up runtime**, and it only ever
  touches that one.

## What the installer never does

* It never runs `wsl --shutdown`.
* It never modifies Docker Desktop or any other WSL distribution.
* It never writes secrets to disk in plain text.

## Building the installer

```powershell
# from the repository root, in PowerShell
./installer/build.ps1
```

Requirements on the build machine: Python 3.10+, PowerShell 5.1+, and the .NET
Framework C# compiler (`csc`, present on Windows 10/11).

The build:

1. Runs the headless self-check (`python app/main.py --check`).
2. Builds the app with PyInstaller.
3. Zips the output.
4. Compiles `SetupStub.cs` into `KaliWindowsSubstitute-Setup.exe`, embedding the zip.

## Uninstalling

`Settings > Apps > Kali Linux Windows Substitute > Uninstall`, or run
`installer/setup/Uninstall.ps1`. The uninstaller removes the program files and
shortcuts and asks separately whether to remove the private runtime image; it
still never shuts down WSL as a whole.

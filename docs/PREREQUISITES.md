# Prerequisites

Kali Linux Windows Substitute needs very little to *start*, and a bit more to
*run tools*. The app will tell you what is missing, but here is the whole list
with links.

## 1. Windows

| Requirement | Detail |
| --- | --- |
| Windows 11, or Windows 10 version 2004 (build 19041) or later | WSL2 is only available from these builds |
| 64-bit CPU with virtualisation enabled | WSL2 runs a real Linux kernel in a lightweight VM |
| ~2 GB free disk | for the runtime image, plus whatever tools you install |

Check your version: **Settings → System > About**, or

```powershell
winver
```

## 2. Enable WSL2 (one time)

### Option A: the one-command route (Windows 11, recent Windows 10)

From an **elevated** PowerShell:

```powershell
wsl --install --no-distribution
```

`--no-distribution` is deliberate: this app brings its own runtime, so you do
not need Ubuntu from the Store. After it finishes, **restart Windows**, then
check:

```powershell
wsl --status
```

Windows documentation:
<https://learn.microsoft.com/windows/wsl/install>

### 2b. If `wsl --install` is not available

Enable the two Windows features by hand, in an elevated PowerShell:

```powershell
dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
dism.exe /exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart
```

Or run the helper in this repository, which does the same thing:

```powershell
powershell -ExecutionPolicy Bypass -File installer/enable-wsl.ps1
```

Restart when prompted, then set WSL2 as the default and update the kernel:

```powershell
wsl --set-default-version 2
wsl --update
```

Official manual-install guide:
<https://learn.microsoft.com/windows/wsl/install-manual>

## 2.5. Virtualisation in firmware

If `wsl --status` complains about virtualisation, enable **Intel VT-x** or
**AMD-V** (sometimes labelled SVM) in your BIOS/UEFI, and make sure
**Virtual Machine Platform** is on in "Turn Windows features on or off".

- Intel: <https://www.intel.com/content/www/us/en/support/articles/000005486/processors.html>
- AMD: <https://www.amd.com/en/support/kb/faq/pa-100>

## 3. Python (only to run from source)

Python 3.10 or newer, from <https://www.python.org/downloads/windows/>. Tick
"Add python.exe to PATH" during install. Then:

```powershell
python -m pip install -r requirements.txt
```

If you only use the built installer, you do not need Python.

## 4. The runtime image

The tools live in a WSL2 distribution the app imports from a rootfs image. You
have two options.

### Build it yourself (recommended, fully transparent)

You need a Linux host — Kali, Debian or Ubuntu, or a WSL distribution you
already have — with `root`, `debootstrap` and `python3-yaml`:

```bash
sudo apt-get update && sudo apt-get install -y debootstrap python3-yaml
sudo ./runtime/build-rootfs.sh
# writes runtime/dist/kalisub-rootfs.tar.gz and its .sha256
```

Then, on Windows, press **Set up runtime** in the app. It imports the image into
`%LOCALAPPDATA%\KaliWindowsSubstitute\wsl`.

`debootstrap` reference: <https://wiki.debian.org/Debootstrap>

### Download a pinned image

If a maintainer publishes an image, set these in your environment (see
`.env.example`):

```
KWS_ROOTFS_URL=https://example.invalid/kalisub-rootfs.tar.gz
KWS_ROOTFS_SHA256=<the sha256 of that file>
```

The app downloads it and **refuses to import it if the SHA-256 does not match**.

## Optional prerequisites

| Feature | Needs |
| --- | --- |
| AI, local | [Ollama](https://ollama.com) running on `127.0.0.1:11434` |
| AI, cloud | an API key for an OpenAI-compatible endpoint |
| Wireless tools | a USB Wi-Fi adapter that can be passed through to WSL2 (see [LIMITATIONS.md](LIMITATIONS.md)) |

## What you do *not* need

- **Docker.** Docker is not used at all. If you run Docker Desktop, the app will
  not interfere with it.
- **A separate Kali install or VM.**
- **Administrator rights** after WSL2 is enabled.

## Troubleshooting

| Symptom | Try |
| --- | --- |
| `wsl --status` says WSL is not installed | Enable the features above and restart. |
| "virtualisation is not enabled" | Turn on VT-x/AMD-V in firmware. |
| The app says the runtime is not installed | Press **Set up runtime**; if the image is missing, build or download it (step 4). |
| "the runtime exists but its agent is not answering" | `wsl -d KaliSubstitute -u root -- tail -n 100 /var/log/kalisub-agent.log` |
| Everything looks broken | In the app, **Set up / repair runtime**. Do **not** run `wsl --shutdown` — it is not needed and it disrupts other distributions, including Docker. |

Microsoft's WSL troubleshooting page:
<https://learn.microsoft.com/windows/wsl/troubleshooting>

<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:0B2A7D,50:8A1C1C,100:0B2A7D&height=200&section=header&text=KALIDESK&font=Orbitron&fontSize=32&fontColor=F5F7FF&animation=fadeIn&fontAlignY=38&desc=Real%20Linux%20tools%20for%20Windows&descAlignY=62&descSize=16" alt="KaliDesk — real Linux tools for Windows" width="100%" />

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![WSL2](https://img.shields.io/badge/Runtime-Private%20WSL2-3AAE66?style=flat-square)](#the-runtime)
[![Windows](https://img.shields.io/badge/Platform-Windows-4A7A9B?style=flat-square)](#prerequisites)
[![MIT](https://img.shields.io/badge/License-MIT-6F8F76?style=flat-square)](LICENSE)

**A Kali-style security workbench for Windows—with a friendly GUI, real Linux tools, and an isolated WSL2 runtime.**

</div>

# Kali Linux Windows Substitute

KaliDesk brings a graphical, beginner-friendly workbench to Windows while running real Linux security tools inside the app's own private WSL2 distribution. Tools such as nmap, sqlmap, hashcat, and foremost run in Linux—not recompiled as Windows programs.

Use the tool catalog to explore available tools, read prerequisites and usage notes, install only what you need, fill in guided forms, review the exact command, and inspect results in the app. An optional local or cloud AI assistant can explain output or suggest a command; you stay in control and must confirm a proposed run.

> **Not affiliated with OffSec.** “Kali Linux” and the Kali logo are trademarks of OffSec Services Limited. This is an independent, unofficial workbench that runs Debian/Kali packages; it is not a product of or endorsed by OffSec.
>
> **Authorised testing only.** Use KaliDesk only on systems you own or have explicit written permission to test. Read [docs/ACCEPTABLE_USE.md](docs/ACCEPTABLE_USE.md).

## Why KaliDesk?

A bare Kali VM gives you command-line tools. KaliDesk adds a guided Windows desktop experience:

- **Friendly GUI:** browse a tool catalog, see prerequisites and explanations, enter options in forms, and review results.
- **Install on demand:** choose which tools to install or remove inside the private runtime.
- **Command review:** inspect the exact argument list before running a supported tool.
- **Optional AI assistant:** use a local or cloud model to explain output or propose a command. AI is not required, and suggestions are never run without your confirmation.
- **Private WSL2 runtime:** the app manages its own distribution and does not interfere with your other WSL distributions or Docker Desktop.

## New in v1.4.0

- **Soothing sage UI theme** with a nature-inspired palette and reduced eye strain.
- **Resilient frontend/backend connectivity** with automatic retry, connection-state tracking, polling utilities, and batch requests.
- **Real-time status monitoring** for runtime and agent state with configurable polling.
- **Enhanced security** including iframe sandboxing for Strix, URL validation, and CSP nonce support.
- **Accessibility improvements** including WCAG 2.1 AA support, reduced motion, and high contrast.

## How it works

```text
Windows desktop app                         Private WSL2 distribution
┌──────────────────────────────┐            ┌──────────────────────────────┐
│ KaliDesk                     │            │ KaliSubstitute               │
│ pywebview window             │◄──────────►│ kalisub-agent                 │
│ Flask backend + UI           │  loopback  │ tool allowlist                │
│ token + CSRF protection      │            │ scope guard + output caps    │
│ wsl.exe -d KaliSubstitute    │            │ runs Linux tools              │
└──────────────────────────────┘            └──────────────────────────────┘
```

1. The launcher starts a small Flask backend bound to `127.0.0.1` and opens the interface in a native pywebview window.
2. When you run a supported tool, the backend builds an argument list (not a shell command string), applies a scope guard, and sends the request to the agent in the app's private runtime.
3. The in-runtime agent checks the tool against its allowlist and checks the target scope. It runs the binary with `shell=False`, a timeout, and an output cap.
4. Results return to the interface, and the run is recorded in a local audit log.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the architecture details.

## Prerequisites

KaliDesk requires **WSL2** on Windows 10 (build 19041 or newer) or Windows 11, plus a private Linux runtime image to import.

- Windows 10/11 with WSL2 enabled
- A private runtime image or a root filesystem tarball you build
- Python 3.10 or newer
- PowerShell 5.1 or newer

The runtime image contains the Linux environment and tools. Build it with `runtime/build-rootfs.sh`, or configure a pinned image URL and SHA-256. Follow [docs/PREREQUISITES.md](docs/PREREQUISITES.md) for complete instructions.

## Quick start

```powershell
git clone https://github.com/sazid63/KaliDesk.git
cd KaliDesk
python -m pip install -r requirements.txt
python app/main.py
```

When the app opens for the first time, press **Set up runtime**. The app imports and manages its own `KaliSubstitute` distribution.

Useful options:

```powershell
python app/main.py --check      # headless self-check used by CI
python app/main.py --no-gui     # start the backend and print the URL
python app/main.py --port 8899  # use a different loopback port
```

### Build the Windows installer

From the repository root in PowerShell:

```powershell
./installer/build.ps1
# -> installer/dist/KaliWindowsSubstitute-Setup.exe
```

The installer places the app under `%LOCALAPPDATA%\Programs\KaliWindowsSubstitute`, creates a Start Menu shortcut, and registers an uninstall entry. See [installer/README.md](installer/README.md). Enabling WSL2 as a Windows feature may require elevation; installing the app itself does not.

## The runtime

The tools run inside a WSL2 distribution named `KaliSubstitute`, owned by KaliDesk. The application does not recompile Linux tools for Windows, and it does not touch the user's other distributions or Docker Desktop.

```text
┌──────────────────────── Windows ───────────────────────────┐
│  KaliDesk (pywebview window)                                │
│       │  fetch, loopback only, token + CSRF                 │
│  Flask backend  127.0.0.1:8788                              │
│       │  HTTP, loopback, bearer token                       │
│  wsl.exe -d KaliSubstitute                                  │
└───────┼─────────────────────────────────────────────────────┘
        ▼
┌────────────── private WSL2 distro: KaliSubstitute ──────────┐
│ kalisub-agent 127.0.0.1:5055 (inside the distro)            │
│   • allowlist from /etc/kalisub/tools.json                  │
│   • argv execution with shell=False, timeout, output cap    │
│   • scope guard; public targets require confirmation         │
│   • evidence folder shared with the Windows app             │
└─────────────────────────────────────────────────────────────┘
```

### Runtime ground rules

- The app only names and manages its own `KaliSubstitute` distribution.
- It never runs `wsl --shutdown`. WSL2 runs distributions in a shared VM; shutting it down could disrupt Docker Desktop and your other distributions.
- It never terminates, exports, or unregisters another distribution.

### Build the runtime image

On a Linux host with root, `debootstrap`, and `python3-yaml`:

```bash
sudo apt-get update && sudo apt-get install -y debootstrap python3-yaml
sudo ./runtime/build-rootfs.sh
# -> runtime/dist/kalisub-rootfs.tar.gz
```

Then, from Windows, press **Set up runtime** in the app. The import is equivalent to:

```powershell
wsl --import KaliSubstitute %LOCALAPPDATA%\KaliWindowsSubstitute\wsl runtime\dist\kalisub-rootfs.tar --version 2
```

Alternatively, set `KWS_ROOTFS_URL` and `KWS_ROOTFS_SHA256` (see `.env.example`) to download a pinned image. KaliDesk validates the archive against the configured SHA-256 before using it.

## Tools: install, use, remove

Open a tool in the catalog to see:

- **What it needs:** tool-specific prerequisites explained in plain language.
- **How to use it:** a short walkthrough and copyable examples.
- **A guided form:** for supported tools, enter options and use **Review command** to inspect the exact argument list before execution.

The **Tool manager** installs and removes tools inside the private runtime and shows what is currently present. Per-tool details are also documented in [docs/TOOLS.md](docs/TOOLS.md).

### Add a tool to the catalog

Add an entry to [`catalog/tools.yaml`](catalog/tools.yaml), then run:

```powershell
python tools/gen_docs.py
```

The catalog is the source of truth used by the dashboard, tool manager, prerequisites, and generated documentation, so the information stays in sync.

## The optional AI assistant

AI is optional; KaliDesk's tools work without it.

- **Local:** install Ollama and point Settings to `http://127.0.0.1:11434`.
- **Cloud:** configure an OpenAI-compatible endpoint. The API key is encrypted with the Windows Data Protection API and stored per user—not in the repository, database, or logs.

The assistant can explain output, answer questions, and propose a tool run. A proposal is presented for your review and confirmation; KaliDesk does not run model suggestions without your approval. See [docs/AI.md](docs/AI.md).

## Safety and repository hygiene

This repository is intended to be safe to clone and inspect.

- **No secrets in the tree:** `.env.example` only; Gitleaks runs in pre-commit and CI.
- **No machine-specific absolute paths:** paths are built at runtime from the user's profile.
- **No telemetry:** the backend is localhost-only. Network traffic is limited to the AI endpoint you configure or the runtime image URL you configure. Tool installation contacts the configured package sources.
- **Defence in depth:** bearer token and CSRF protection on writes, strict CSP, argument-list execution with `shell=False`, an in-runtime allowlist, scope checks, timeouts, output caps, and a local audit log.
- **Reports are download-only attachments:** a finding cannot run a script in the app's own window.

Report a problem privately; see [SECURITY.md](SECURITY.md).

## Project structure

```text
app/                    launcher (main.py) and WSL runtime lifecycle
server/                 Flask backend: routes, catalog, commands, security, DB, reports, AI
ui/                     the window: index.html, app.js, styles.css (soft bright theme)
catalog/                tools.yaml — the single source of truth for every tool
runtime/                the private WSL2 image: agent, build scripts, overlay
installer/              PowerShell build + install/uninstall scripts
tools/                  gen_docs.py and other maintenance scripts
docs/                   prerequisites, architecture, AI, tools, limits
tests/                  pytest suite (auth, CSRF, scope guard, commands, reports)
```

## Version history

### v1.4.0 (2026-11-03)

- **Sage UI redesign** with lower eye strain and subtle gradients.
- **Resilient frontend/backend connectivity** with auto-retry and status tracking.
- **Real-time status monitoring** with polling utilities and batch requests.
- **Enhanced security** via iframe sandboxing for Strix, URL validation, and CSP nonce support.
- **Accessibility** improvements with WCAG 2.1 AA color contrast.

### v1.3.0

- **Interactive tool catalog** with install/remove actions.
- **AI support integration** for local or cloud models.
- **Application logs and audit history** in file-backed storage.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Prerequisites](docs/PREREQUISITES.md)
- [Tools](docs/TOOLS.md)
- [AI assistant](docs/AI.md)
- [Acceptable use](docs/ACCEPTABLE_USE.md)
- [Security policy](SECURITY.md)

## License

MIT. See [LICENSE](LICENSE) for details.

<div align="center">

<img src="https://capsule-render.vercel.app/api?type=rect&color=0:071812,25:123A2D,68:214E3D,100:0D1B1B&height=180&section=header&text=KALIDESK&font=Orbitron&fontSize=30&fontColor=CFEBD9&animation=fadeIn&fontAlignY=38&desc=WINDOWS%20SECURITY%20WORKBENCH%20FOR%20REAL%20LINUX%20TOOLS&descAlignY=63&descSize=12" width="100%" alt="KaliDesk banner" />

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![WSL2](https://img.shields.io/badge/Runtime-Private%20WSL2-3AAE66?style=flat-square)](#)
[![Windows](https://img.shields.io/badge/Platform-Windows-4A7A9B?style=flat-square)](#)
[![MIT](https://img.shields.io/badge/License-MIT-6F8F76?style=flat-square)](LICENSE)

</div>

# Kali Linux Windows Substitute

**A Kali-style security workbench for Windows that runs the real Linux tools** in the app's own private WSL2 distribution — not recompiled for Windows.

> **Not affiliated with OffSec.** "Kali Linux" and the Kali logo are trademarks of OffSec Services Limited. This project is an independent, unofficial workbench that runs Debian/Kali packages. It is not endorsed by or connected to OffSec or the Kali Linux project.
>
> **Authorised testing only.** Use it on systems you own or have explicit written permission to test. See [docs/ACCEPTABLE_USE.md](docs/ACCEPTABLE_USE.md).

## Three things a bare Kali VM does not give you

- A **friendly GUI** with a tool catalog, per-tool form, prerequisites, and output
- **Install on demand** — you decide which tools live on your machine; add or uninstall from inside the app
- An **optional AI assistant** (local or cloud) that explains output and can propose a command (you still confirm)

## New in v1.4.0

- **Soothing sage UI theme** — nature-inspired palette with reduced eye strain
- **Resilient frontend-backend connectivity** — auto-retry, connection state tracking, polling utilities, batch requests
- **Real-time status monitoring** — live runtime and agent status with configurable polling
- **Enhanced security** — iframe sandboxing for Strix, URL validation, CSP nonce support
- **Accessibility** — WCAG 2.1 AA compliant, reduced motion, high contrast support

## Quick overview

Run real Linux security tools (nmap, sqlmap, hashcat, tshark, etc.) natively on Windows via a private WSL2 runtime. The Flask backend + pywebview UI gives you a graphical tool catalog, form-driven tool execution, and audit capabilities — all with defense-in-depth: bearer token + CSRF on writes, argv-only execution with `shell=False`, an in-runtime allowlist, scope guard, timeouts, output caps, and a local audit log.

Report a problem privately: see [SECURITY.md](SECURITY.md).

> **Not affiliated with OffSec.** "Kali Linux" and the Kali logo are trademarks of OffSec Services Limited. This project is an independent, unofficial workbench that runs Debian/Kali packages. It is not endorsed by or connected to OffSec or the Kali Linux project.
>
> **Authorised testing only.** Use it on systems you own or have explicit written permission to test. See [docs/ACCEPTABLE_USE.md](docs/ACCEPTABLE_USE.md).

---

## Contents

- [How it works](#how-it-works)
- [Prerequisites](#prerequisites)
- [Quick start](#quick-start)
- [The runtime](#the-runtime)
- [Tools: install, use, remove](#tools-install-use-remove)
- [The optional AI](#the-optional-ai)
- [Adding a tool to the catalog](#adding-a-tool-to-the-catalog)
- [Safety and repo hygiene](#safety-and-repo-hygiene)
- [Project layout](#project-layout)
- [Version history](#version-history)
- [Documentation](#documentation)
- [License](#license)

---

## How it works

```text
Windows                              private WSL2 distribution
┌──────────────────────────────┐    ┌────────────────────────────────────┐
│ Kali Linux Windows Substitute │◄──►│ KaliSubstitute                     │
│ pywebview window             │    │ kalisub-agent                     │
│ Flask backend + UI           │    │ allowlist from /etc/kalisub/tools.json │
│ loopback only, token + CSRF  │    │ runs argv with shell=False        │
│ wsl.exe -d KaliSubstitute    │    │ scope guard + output caps         │
└──────────────────────────────┘    └────────────────────────────────────┘
```

1. The launcher starts a small Flask backend on `127.0.0.1` and opens the UI in a native window.
2. When you run a tool, the backend builds an argv list (never a shell string), applies a scope guard, and asks the in-runtime agent over loopback.
3. The agent on the Linux side checks the tool is on its allowlist, checks the target is in scope, and runs the binary with `shell=False`, a timeout, and an output cap.
4. Output comes back to the UI, and the run is written to a local audit log.

More detail: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## Prerequisites

The app needs **WSL2** on Windows 10 (build 19041+) or Windows 11, and a **private runtime image** to import into it.

Full, link-by-link instructions are in [docs/PREREQUISITES.md](docs/PREREQUISITES.md). The short version:

- Windows 10/11 with WSL2 enabled
- A private runtime image or built rootfs tarball
- Python 3.10+
- PowerShell 5.1+

The runtime image is the actual Linux tools. It is built using `runtime/build-rootfs.sh`, or downloaded from a pinned URL you configure.

---

## Quick start

```powershell
git clone https://github.com/sazid63/KaliDesk.git
cd KaliDesk
python -m pip install -r requirements.txt
python app/main.py
```

The app opens. Press **Set up runtime** on the first run.

Useful flags:

```powershell
python app/main.py --check      # headless self-check used by CI
python app/main.py --no-gui     # start the backend and print the URL
python app/main.py --port 8899  # use a different loopback port
```

Build and install:

```powershell
./installer/build.ps1
# -> installer/dist/KaliWindowsSubstitute-Setup.exe
```

The installer copies the app to `%LOCALAPPDATA%\Programs\KaliWindowsSubstitute` and adds a Start Menu shortcut and an uninstall entry. See [installer/README.md](installer/README.md).

---

## The runtime

The tools run in a WSL2 distribution called `KaliSubstitute`. It is the app's own runtime; nothing is recompiled for Windows and the app never touches the user's other distributions or Docker Desktop.

```text
┌──────────────────────── Windows ────────────────────────┐
│  Kali Linux Windows Substitute (pywebview window)       │
│        │  fetch, loopback only, token + CSRF            │
│  Flask backend  127.0.0.1:8788                          │
│        │  HTTP, loopback, bearer token                  │
│  wsl.exe -d KaliSubstitute                              │
└────────┼────────────────────────────────────────────────┘
          ▼
┌──────────── private WSL2 distro: KaliSubstitute ────────┐
│  kalisub-agent  127.0.0.1:5055 (inside the distro)      │
│    - allowlist from /etc/kalisub/tools.json             │
│    - runs argv with shell=False, timeout, output cap    │
│    - scope guard: public targets need confirmation      │
│  /mnt/c/...\KaliWindowsSubstitute\evidence  (shared)    │
└─────────────────────────────────────────────────────────┘
```

### Ground rules

* The app only ever names its own distribution (`KaliSubstitute`).
* It never runs `wsl --shutdown`. WSL2 runs every distribution in one VM; shutting that VM down would disturb Docker Desktop and the user's distros.
* It never terminates, exports or unregisters another distribution.

### Building the image

```bash
# On any Linux host with root, debootstrap and python3-yaml:
sudo apt-get update && sudo apt-get install -y debootstrap python3-yaml
sudo ./runtime/build-rootfs.sh
# -> runtime/dist/kalisub-rootfs.tar.gz
```

Then, from Windows, press **Set up runtime** in the app. It runs:

```powershell
wsl --import KaliSubstitute %LOCALAPPDATA%\KaliWindowsSubstitute\wsl runtime\dist\kalisub-rootfs.tar --version 2
```

### Alternative: download a pinned image

Set `KWS_ROOTFS_URL` and `KWS_ROOTFS_SHA256` (see `.env.example`). The app will validate the archive before using it.

---

## Tools: install, use, remove

Open any tool to see, in plain English:

- **What this tool needs** — the prerequisites for that specific tool, written for someone who has not used it before
- **How to use it** — a short walkthrough and copyable examples
- **A form** — for the tools the app can drive, with a **Review command** button that shows the exact argv before anything runs

The **Tool manager** installs and uninstalls any tool inside the runtime and shows what is present. The same information is written up per tool in [docs/TOOLS.md](docs/TOOLS.md).

Want a tool the catalog does not have? Add one entry to [catalog/tools.yaml](catalog/tools.yaml), run `python tools/gen_docs.py`, and it appears everywhere: dashboard, manager, prerequisites and docs.

---

## The optional AI

You do not need the AI to use any tool. If you want it:

- **Local:** install Ollama, then point Settings at `http://127.0.0.1:11434`.
- **Cloud:** any OpenAI-compatible endpoint. The API key is encrypted with the Windows Data Protection API and stored per user — never in the repo, never in the database, never in logs.

The chat can explain output, answer questions, and propose a tool run. A proposal is shown with a confirm button; the app never runs what the model suggests without you approving it, and the normal scope guard still applies.

See [docs/AI.md](docs/AI.md).

---

## Adding a tool to the catalog

Want a tool the catalog does not have? Add one entry to [catalog/tools.yaml](catalog/tools.yaml), run `python tools/gen_docs.py`, and it appears everywhere: dashboard, manager, prerequisites and docs.

This keeps the app's catalog and the documentation in sync without editing a bunch of screenshots or copies in multiple places.

---

## Safety and repo hygiene

This repository is meant to be safe to clone and read.

- **No secrets in the tree.** `.env.example` only, gitleaks in pre-commit and CI.
- **No machine-specific absolute paths.** Paths are built at runtime from the user's own profile.
- **No telemetry.** The backend is localhost-only. The only network traffic it initiates is to the AI endpoint you configure, or to the runtime image download URL you configured. Tool installs come from the Kali package mirrors, and tools themselves only contact targets you authorize.
- **Defence in depth.** Bearer token + CSRF on writes, strict CSP, argv-only execution with `shell=False`, an in-runtime allowlist, a scope guard, timeouts, output caps, and a local audit log.
- **Reports are download-only attachments.** A finding can never run script in the app's own window.

Report a problem privately: see [SECURITY.md](SECURITY.md).

---

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

---

## Version history

### v1.4.0 (2026-11-03)

- **Sage UI redesign** with lower eye strain and subtle gradients
- **Resilient frontend-backend connectivity** with auto-retry and status tracking
- **Real-time status monitoring** with polling utilities and batch requests
- **Enhanced security** via iframe sandboxing for Strix, URL validation, CSP nonce support
- **Accessibility** improvements with WCAG 2.1 AA color contrast

### v1.3.0

- **Interactive tool catalog** with install/remove actions
- **AI support integration** for local or cloud models
- **Application logs and audit history** in file-backed storage

---

## Documentation

Useful docs are kept in the repository and updated as the app changes:

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [docs/PREREQUISITES.md](docs/PREREQUISITES.md)
- [docs/TOOLS.md](docs/TOOLS.md)
- [docs/AI.md](docs/AI.md)
- [docs/ACCEPTABLE_USE.md](docs/ACCEPTABLE_USE.md)
- [SECURITY.md](SECURITY.md)

---

## License

MIT. See [LICENSE](LICENSE) for details.

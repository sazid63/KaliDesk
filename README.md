# Kali Linux Windows Substitute

A Kali-style security workbench for Windows. The tools it runs are the **real
Linux tools** — nmap, sqlmap, hashcat, tshark and the rest — running inside a
private WSL2 distribution that the app creates and owns. They are not
recompiled for Windows.

It gives you three things a bare Kali VM does not:

- a **friendly GUI** with a tool catalog, per-tool form, prerequisites and output;
- **install on demand** — you decide which tools live on your machine, and you
  can add or uninstall them from inside the app;
- an **optional AI assistant** (local or cloud) that explains output and can
  propose a command, which you still have to confirm.

The workbench itself stays on your machine: the backend listens on loopback
only, and the app sends no telemetry anywhere. Downloading the runtime image,
installing on-demand tools, and some tools (plus the optional cloud AI) still
need an internet connection — see
[docs/LIMITATIONS.md](docs/LIMITATIONS.md#network-access).

> **Not affiliated with OffSec.** "Kali Linux" and the Kali logo are trademarks
> of OffSec Services Limited. This project is an independent, unofficial
> workbench that runs Debian/Kali packages. It is not endorsed by or connected
> to OffSec or the Kali Linux project.

> **Authorised testing only.** Use it on systems you own or have explicit
> written permission to test. See [docs/ACCEPTABLE_USE.md](docs/ACCEPTABLE_USE.md).

---

## Contents

- [How it works](#how-it-works)
- [Prerequisites](#prerequisites)
- [Quick start](#quick-start)
- [The runtime](#the-runtime)
- [Tools: install, use, remove](#tools-install-use-remove)
- [The optional AI](#the-optional-ai)
- [Adding a tool to the catalog](#tools-install-use-remove)
- [Safety and repository hygiene](#safety-and-repo-hygiene)
- [Project layout](#project-layout)
- [Documentation](#documentation)
- [Licence](#licence)
- [Publishing to GitHub](#publishing-to-github)

---

## How it works

```
Windows                                   private WSL2 distribution
┌──────────────────────────────┐          ┌──────────────────────────────┐
│  desktop window (pywebview)  │          │  kalisub-agent               │
│    │ loopback + token+CSRF   │          │  127.0.0.1:5055              │
│  Flask backend 127.0.0.1:8788│  HTTP →  │  allowlist + scope guard     │
│        │ bearer token        │          │  runs argv, shell=False      │
└────────┼─────────────────────┘          └──────────────┬───────────────┘
         │ wsl.exe -d KaliSubstitute                      │
         ▼                                                ▼
   your evidence folder  <──── /mnt/c/.../evidence ────────┘
```

1. The launcher starts a small Flask backend on `127.0.0.1` and opens the UI in a
   native window.
2. When you run a tool, the backend builds an **argv list** (never a shell
   string), applies a scope guard, and asks the in-runtime agent over loopback.
3. The agent on the Linux side checks the tool is on its allowlist, checks the
   target is in scope, and runs the binary with `shell=False`, a timeout and an
   output cap.
4. Output comes back to the UI, and the run is written to a local audit log.

More detail: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## Prerequisites

The app needs **WSL2** on Windows 10 (build 19041+) or Windows 11, and a
**private runtime image** to import into it.

Full, link-by-link instructions are in
**[docs/PREREQUISITES.md](docs/PREREQUISITES.md)**. The short version:

| What | Why | How |
| --- | --- | --- |
| Windows 10 2004+ or Windows 11 | WSL2 needs it | — |
| WSL2 feature | runs the Linux runtime | `wsl --install` (admin), then restart |
| Virtualisation enabled in BIOS/UEFI | WSL2 is a VM | see the docs page |
| ~2 GB free disk | the runtime image | — |
| The runtime image | the actual Linux tools | built with `runtime/build-rootfs.sh`, or downloaded |

One-time, elevated PowerShell:

```powershell
wsl --install --no-distribution
# restart Windows, then
wsl --status
```

You do **not** need Docker. If you already run Docker Desktop, this app will not
disturb it: it never shares a distribution with anything else and never runs
`wsl --shutdown`.

---

## Quick start

### Run from source (recommended while the project is young)

```powershell
git clone <your-fork-url> Kali-Windows-Substitute
cd Kali-Windows-Substitute
python -m pip install -r requirements.txt
python app/main.py
```

The app opens. Press **Set up runtime** on the first run.

Useful flags:

```powershell
python app/main.py --check      # headless self-check (used by CI)
python app/main.py --no-gui     # start the backend and print the URL
python app/main.py --port 8899  # use a different loopback port
```

### Build and install

```powershell
./installer/build.ps1
# -> installer/dist/KaliWindowsSubstitute-Setup.exe
```

The installer copies the app to `%LOCALAPPDATA%\Programs\KaliWindowsSubstitute`
and adds a Start Menu shortcut and an uninstall entry. See
[installer/README.md](installer/README.md).

---

## The runtime

The tools run in a WSL2 distribution called `KaliSubstitute`. It is the app's
own; the app creates it, and only the app uses it.

- **It never runs `wsl --shutdown`.** WSL2 runs every distribution in one shared
  VM, so shutting that VM down would disturb Docker Desktop and your own
  distributions. The app simply does not do it.
- **It never terminates, exports or unregisters another distribution.**
- **It never silently downloads and runs something unverified.** A downloaded
  image must match a SHA-256 you configured.

Build the image (on any Linux host with root):

```bash
sudo apt-get update && sudo apt-get install -y debootstrap python3-yaml
sudo ./runtime/build-rootfs.sh
# -> runtime/dist/kalisub-rootfs.tar.gz
```

Then press **Set up runtime** in the app. Details and troubleshooting:
[runtime/README.md](runtime/README.md).

---

## Tools: install, use, remove

Open any tile to see, in plain English:

- **What this tool needs** — the prerequisites for that specific tool, written
  for someone who has not used it before.
- **How to use it** — a short walkthrough and copyable examples.
- **A form** — for the tools the app can drive, with a *Preview command* button
  that shows the exact argv before anything runs.

The **Tool manager** installs and uninstalls any tool inside the runtime, and
shows what is present. The same information is written up per tool in
[docs/TOOLS.md](docs/TOOLS.md).

Want a tool the catalog does not have? Add one entry to
[`catalog/tools.yaml`](catalog/tools.yaml), run `python tools/gen_docs.py`, and it
appears everywhere: dashboard, manager, prerequisites and docs.

---

## The optional AI

You do not need the AI to use any tool. If you want it:

- **Local:** install [Ollama](https://ollama.com), then point Settings at
  `http://127.0.0.1:11434`.
- **Cloud:** any OpenAI-compatible endpoint. The API key is encrypted with the
  Windows Data Protection API and stored per user — never in the repository,
  never in the database, never in a log.

The chat can explain output, answer questions, and **propose** a tool run. A
proposal is shown with a confirm button; the app never runs what the model
suggests without you approving it, and the normal scope guard still applies. See
[docs/AI.md](docs/AI.md).

---

## Security and test hygiene

This repository is meant to be safe to clone and read.

- **No secrets in the tree.** `.env.example` only, gitleaks in pre-commit and CI.
- **No machine-specific absolute paths.** Paths are built at runtime from the
  user's own profile.
- **No telemetry.** The backend is loopback-only. The only network traffic it
  ever initiates itself is to the AI endpoint you configure, or to download
  the runtime image from a pinned URL you configure. Tool installs come from
  the Kali package mirrors, and tools themselves only contact targets you
  authorise.
- **Defence in depth.** Bearer token + CSRF on writes, strict CSP, argv-only
  execution with `shell=False`, an in-runtime allowlist, a scope guard, timeouts,
  output caps, and a local audit log.
- **Reports are download-only attachments**, so a finding can never run script
  in the app's own window.

Report a problem privately: see [SECURITY.md](SECURITY.md).

---

## Project structure

```
app/            launcher (main.py) and WSL2 runtime lifecycle (runtime.py)
server/         Flask backend: routes, catalog, commands, security, DB, reports, AI
ui/             the window: index.html, app.js, styles.css (terminal-green theme)
catalog/        tools.yaml - the single source of truth for every tool
runtime/        the private WSL2 image: agent, build script, overlay
installer/      PowerShell build + install/uninstall scripts
tools/          gen_docs.py and other maintenance scripts
docs/           prerequisites, architecture, per-tool docs, limitations
tests/          pytest suite (auth, CSRF, scope guard, commands, reports)
```

---

## License

MIT. See [LICENSE](LICENSE). Third-party tools keep their own licences; see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) — nmap in particular ships under
the NPSL, which is not OSI-approved.

---

## Publishing to GitHub

This tree is safe to push as-is: no secrets, no machine-specific absolute paths,
and the commit author is a neutral project identity rather than a personal one.

Three placeholders point at a repository that does not exist yet. Replace them
after you create the repository:

| Where | Placeholder | Replace with |
| --- | --- | --- |
| `pyproject.toml` | `Homepage = "https://github.com/your-org/..."` | your repository URL |
| `catalog/tools.yaml` (the `report` tool) | `homepage: "https://github.com/your-org/..."` | your repository URL |
| `README.md`, `CONTRIBUTING.md` | `<your-fork-url>` / `<your-fork>` | your fork URL |

After editing `catalog/tools.yaml`, run `python tools/gen_docs.py` so the
generated docs match, then push:

```powershell
# Create the repository first (web UI, or: gh repo create <you>/Kali-Windows-Substitute --source . --push)
git remote add origin https://github.com/<you>/Kali-Windows-Substitute.git
git push -u origin main
```

If you would rather your own name appear on the commits than the neutral
identity, set it before you commit: `git config --local user.name "<name>"` and
`git config --local user.email "<email>"`.

CI (`.github/workflows/ci.yml`) runs lint, the test suite, generated-file
drift checks and gitleaks on every push. It needs no secrets beyond the
automatic `GITHUB_TOKEN`.

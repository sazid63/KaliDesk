# The runtime

Kali Linux Windows Substitute runs the *real* Linux tools. It does that inside a
private WSL2 distribution that the app creates, owns and talks to. Nothing is
recompiled for Windows, and the app never touches the user's other distributions
or Docker Desktop.

```
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

## Ground rules

* The app only ever names its own distribution (`KaliSubstitute`).
* It never runs `wsl --shutdown`. WSL2 runs all distributions in one VM;
  shutting that VM down would disturb Docker Desktop and the user's distros.
* It never terminates, exports or unregisters another distribution.

## Building the image

```bash
# On any Linux host with root, debootstrap and python3-yaml:
sudo apt-get update && sudo apt-get install -y debootstrap python3-yaml
sudo ./runtime/build-rootfs.sh
# -> runtime/dist/kalisub-rootfs.tar.gz
```

Then, from Windows, press **Set up runtime** in the app. It runs:

```
wsl --import KaliSubstitute %LOCALAPPDATA%\KaliWindowsSubstitute\wsl runtime\dist\kalisub-rootfs.tar --version 2
```

### Alternative: download a pinned image

Set `KWS_ROOTFS_URL` and `KWS_ROOTFS_SHA256` (see `.env.example`). The app
downloads the image, verifies the SHA-256, and refuses to use it if the hash
does not match.

## What is inside the image

* A minimal Kali (`kali-rolling`) base.
* A small, safe baseline set of tools (see `BASELINE_PACKAGES` in
  `build-rootfs.sh`). Everything else is installed on demand from the Tool
  manager.
* The agent at `/usr/local/lib/kalisub/agent.py`, started by
  `/usr/local/bin/kalisub-agent-start`.
* The manifest at `/etc/kalisub/tools.json`, generated from
  `catalog/tools.yaml` by `runtime/tools/make_manifest.py`.

## Installing more tools

Tools are added by editing one file: `catalog/tools.yaml`. The catalog is the
single source of truth for the dashboard, the prerequisites panel, the Tool
manager and `docs/TOOLS.md`. Rebuild the image (or install on demand) and the
new tool is available.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| "WSL2 is not available" | Enable WSL2 (see `docs/PREREQUISITES.md`) and restart. |
| "image was not found" | Run `runtime/build-rootfs.sh`, or set `KWS_ROOTFS_URL`. |
| Agent never answers | `wsl -d KaliSubstitute -u root -- tail -n 100 /var/log/kalisub-agent.log` |
| A tool says "is not installed" | Install it from the Tool manager. |
| Nothing else works | In the app: **Set up / repair runtime**. |

Do **not** run `wsl --shutdown` to "fix" things — it is unnecessary here and
disturbs the user's other work.

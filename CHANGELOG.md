# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project uses
[semantic versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - unreleased

First public shape of the workbench.

### Added

- Terminal-green desktop app (`app/main.py`) with a native window (pywebview) and
  a browser fallback; `--check` and `--no-gui` modes for CI and headless use.
- Private WSL2 runtime (`KaliSubstitute`) with a lifecycle module that **never**
  runs `wsl --shutdown` and only ever names its own distribution.
- In-runtime tool agent: bearer-token auth, `shell=False` argv execution, a
  per-tool binary allowlist, argument sanity checks, timeouts and output caps.
- A re-checked scope guard on both sides: public targets are refused without an
  explicit, logged confirmation.
- `catalog/tools.yaml` as the single source of truth, with ~46 tools across 11
  categories, each with prerequisites and usage written for beginners.
- Tool manager: install or uninstall any tool inside the runtime from the app.
- One-click forms with a **Preview command** button for the tools the app drives.
- Findings, a local audit log, and HTML/JSON/CSV report downloads (escaped,
  served as attachments).
- Optional AI: local (Ollama) or OpenAI-compatible cloud, with the key stored
  via Windows DPAPI, and an action-proposal flow that always requires
  confirmation.
- Installer: `installer/build.ps1`, a self-extracting setup stub, per-user
  install, Start Menu shortcut, uninstall entry and an optional WSL enable
  helper.
- Generated documentation: `docs/TOOLS.md` and a page per tool under
  `docs/tools/`.
- Tests: auth, CSRF, scope guard, catalog integrity, command builders, report
  escaping and end-to-end route smoke tests.
- Repository hygiene: `.gitleaks.toml`, pre-commit, `.env.example`, CI workflow.

### Notes

- Linux tools are installed from distribution packages; their licences are listed
  in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). nmap ships under the NPSL,
  which is not OSI-approved.
- This project is not affiliated with OffSec or the Kali Linux project.

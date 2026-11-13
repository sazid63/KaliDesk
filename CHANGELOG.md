# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project uses
[semantic versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Test suites for the agent jobs API, AI, backup, cheat sheets, command safety, containers,
  features, install steps, the jobs API, the MCP server, playground, runtime, scope and version.
- `tools/smoke.py` and the *Tools smoke test* CI workflow; `requirements-build.txt` for the
  installer build.

### Removed

- The Strix panel, the separate AI chat and AI settings panels, and the portable-mode panel and
  module. Their replacements are the single AI assistant and Backup and restore. Strix is a
  command-line tool; see [docs/LIMITATIONS.md](docs/LIMITATIONS.md).

### Fixed

- **Security:** the window's session is set up by exchanging a one-time launch code
  for HttpOnly cookies, so no session secret is kept in the address bar or history.
  Keys and tokens stay out of URLs and logs.
- **Installer:** the Windows installer scripts (`installer/`) were brought in line
  with the current runtime and app layout.
- **UI and server:** the interface and backend were corrected to match each other
  and the catalog. The documentation was updated to match: the four AI providers,
  the module layout, the `KWS_*` environment variables, and the Sage theme.

### Notes

- Linux tools are installed from distribution packages; their licences are listed
  in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). nmap ships under the NPSL,
  which is not OSI-approved.
- This project is not affiliated with OffSec or the Kali Linux project.

## [1.5.0] - 2026-11-10

### Added

- First-run setup downloads and verifies the official Kali WSL image (SHA-256 from
  `SHA256SUMS`), imports it, pushes the agent and manifest, installs the baseline tools
  and keeps the agent alive. Progress and errors show in the UI.
- Streamed, cancellable jobs in the agent (`POST /jobs`, `GET /jobs/<id>`, cancel) used for
  runs and installs; the UI shows live output, elapsed time and a Stop button.
- One-click forms for socat, msfvenom, weevely and photorec; responder, bettercap and wifite
  open in a runtime terminal; "Open a shell in the runtime" in Settings.
- Installed/not-installed badges and an Install button in the tool panel.
- `tools/smoke.py` and the *Tools smoke test* workflow install and run every tool in a Kali container.
- Rotating log file, JSON error responses, automatic port fallback.

### Changed

- The extra panels were fixed rather than hidden: run transcripts are saved automatically,
  achievements are computed from history (no click-to-unlock), the playground is a real
  vulnerable app confined to its own folder, containers validate images, ports (loopback
  only), volumes and exec commands, onboarding is a live first-run guide, cheat sheets match
  the catalog (46 tools) and come from the server, and the panels' scripts no longer share
  global names.
- One AI assistant (Ollama, OpenAI-compatible, Anthropic, Gemini) replaces three overlapping
  AI panels. Keys are per provider (DPAPI) and are only ever sent to the URL they were saved
  for, over https unless the server is local.
- The MCP server was rewritten: valid JSON-RPC, works on Windows, files limited to the
  evidence and work folders, public targets can't be confirmed by a client.
- *Portable mode* became *Backup and restore* (a zip of your data without keys; strict restore).
- Icons are inline SVG (no icon font or CDN) and headings have a clear type scale.

### Fixed on real hardware (a Windows 11 machine with a real KaliSubstitute distro)

- Setup commands were run through the distro's shell, which ate `$1` and quotes; they now use
  `wsl --exec`.
- Metasploit, commix, msfvenom, nikto and wpscan could not install because only Kali's `main`
  section was enabled; setup now enables `contrib non-free non-free-firmware`.
- volatility3 is not in Kali's apt any more: the catalog supports `install_steps`/`remove_steps`
  and installs it with pip into its own venv. photorec now installs the package that ships it.
- Tools ran with an ungenerated default locale (crunch: "setlocale() failed"); the agent now
  uses `C.UTF-8`.
- The playground never started (WSL ended the session before the background job launched).
- The History panel listed oldest-first, hid exit code 0 and ignored its filters; the Audit panel
  read the wrong response key and always said "Nothing logged yet".
- `psutil` and `huggingface_hub` are no longer dependencies (the installer payload is 16 MB).

### Verified

- All 46 tools install and start in the real runtime; nmap, whatweb, netcat, socat, john (cracks
  an MD5 with rockyou), exiftool, binwalk, tshark, gobuster, crunch and searchsploit ran real work.
- In the real UI: first-run guide, live nmap run, Stop on tcpdump, install/uninstall of a tool,
  playground + sqlmap finding the SQL injection, history, transcripts, audit, achievements,
  report export and backup download.
- The packaged app starts, shows its window and serves the UI; the installer script installs it,
  creates the Start Menu shortcut and uninstall entry.

### Removed

- The Strix panel (Strix is a CLI that needs Docker and an LLM key; the app was calling an HTTP
  server that does not exist), the MCP client (it ran arbitrary stored commands), "skills"
  (could not save), and the local model downloader (nothing could run the models).
- Command builders validate every field (no option injection, fixed lists for services,
  payloads and plugins); john/hashcat use rockyou; tcpdump is bounded.
- Single version source: `kws/__about__.py` (checked by `tests/test_version.py`).

### Fixed

- The in-runtime agent crashed on every request and imported a package that is not in the image.
- UI handlers were never attached (colliding `wire()` functions); requests were aborted after
  10 s and POSTs were retried.
- CSRF cookie was unreadable by the UI; CSP errors and missing icons; panels outside `<main>`.
- Scope guard bypasses (`10.0.0.1/0`, `::ffff:8.8.8.8`, `evil.com\@10.0.0.1`).
- Metasploit form accepted any module; AI/skills/MCP could confirm external targets themselves.
- History trim deleted the newest row at 501 runs; history stored passwords.
- CI lint failures and the installer compile error (`using static` with the C# 5 compiler).

## [1.1.0] - 2026-11-01

### Fixed

- Strix AI Pentest panel: dot colours now use the shared `ok`/`info`/`bad`
  classes instead of the non-existent `green`/`yellow`/`red`, and all
  error toasts go through the shared `toast()` helper.
- AI chat markdown: consecutive `<li>` elements are wrapped in a single
  `<ul>` instead of producing broken nested tags.
- Onboarding: `loadStatus()` reads the `needed` field from the server
  response instead of the non-existent `completed` field, so the wizard
  actually starts on step 0 when onboarding is required.
- Recordings table: size is computed from `size_bytes / 1024` instead of
  the non-existent `size_kb` field.
- Fetch timeouts now use `AbortSignal.timeout()` (the `timeout` option is
  not supported by browsers) for OpenCode/DeepSeek auto-detection.
- Keyboard-shortcuts help: the close button is wired up instead of relying
  on an inline `onclick` that was never attached.
- Playground start no longer passes shell redirection tokens as argv and
  now redirects output via `subprocess`, and it honours the configured
  runtime distro.
- `container_runtime` and `playground` honour `config.runtime_distro` instead
  of hard-coding `KaliSubstitute`.
- Per-tool work directories: every tool run gets its own subdirectory so
  tools that refuse to overwrite an existing output directory (foremost,
  hcxtools, cewl) work on the second run.
- `onboarding` no longer creates its own `settings` table; it uses
  `db.init_db()`.
- `tools._target_of` no longer treats the overloaded `name` field as a
  network target.

### Added

- Strix AI Pentest agent: install, start, stop and live webview inside the
  WSL2 runtime, with status polling and a dedicated panel.
- `psutil` and `huggingface_hub` dependencies for the Portable panel and
  the local model downloader.


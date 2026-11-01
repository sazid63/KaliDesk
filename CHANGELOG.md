# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project uses
[semantic versioning](https://semver.org/spec/v2.0.0.html).

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

## [Unreleased]

### Notes

- Linux tools are installed from distribution packages; their licences are listed
  in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). nmap ships under the NPSL,
  which is not OSI-approved.
- This project is not affiliated with OffSec or the Kali Linux project.

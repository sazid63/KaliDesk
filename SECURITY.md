# Security policy

## Reporting a vulnerability

Please report privately. Use GitHub's **Report a vulnerability** (Security →
Advisories) on the repository, or email the maintainer address listed on the
repository profile. Do not open a public issue for something exploitable.

Include: what you found, how to reproduce it, the impact you believe it has, and
the version or commit. We will acknowledge as quickly as we can and credit you
unless you prefer otherwise.

## What is in scope

- the Windows launcher and the Flask backend in this repository;
- the in-runtime agent (`runtime/agent/agent.py`);
- the installer scripts;
- the catalog and command builders (e.g. a way to make a field escape its argv
  element, or to get a non-allowlisted binary executed).

## What is out of scope

- vulnerabilities in upstream tools (nmap, sqlmap, …) — report those upstream;
- the WSL2 platform itself — report those to Microsoft;
- anything that requires a machine that is already compromised, or that requires
  the user to paste an attacker's command in themselves.

## Design notes for reviewers

If you are looking for problems, these are the deliberate choices worth testing:

| Area | Where | Intent |
| --- | --- | --- |
| Auth | `server/security.py` (`require_auth`) | constant-time compare of the session token; loopback-only server |
| CSRF | `require_csrf` | double-submit cookie vs `X-KWS-CSRF` header, constant-time |
| Headers | `install_headers` | strict CSP, `nosniff`, `DENY`, `no-referrer`, `no-store` |
| Scope | `classify_target`, `scope_allows` | public targets refused without explicit confirmation |
| Execution | `runtime/agent/agent.py` | `argv[0]` must match the declared binary; `shell=False`; timeout; output cap |
| Install | agent `/tools/install` | package names validated against a strict pattern before `apt-get` |
| Secrets | `kws/secrets.py` | Windows DPAPI; no plaintext on disk; never in the repo |
| Reports | `server/report.py` | HTML-escaped; served as attachments, not inline |

A useful starting point is the test suite in `tests/`, which asserts the auth,
CSRF and scope behaviour.

## Secrets and this repository

The repository is designed to be safe to clone:

- `.gitleaks.toml` runs in pre-commit and in CI;
- `.env.example` documents configuration variables without values;
- there are no machine-specific absolute paths in tracked files.

If you ever commit a secret by accident: rotate it first, then remove it from
history. Rotating is the part that actually matters.

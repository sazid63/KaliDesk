# Architecture

## Why a private WSL2 distribution

The tools are Linux programs. The honest way to run them on Windows is to run
Linux, so the app creates its own WSL2 distribution and talks to it. There is no
reimplementation layer, no shim, and no fake --help text: if a tool is installed,
you are running the real binary.

The distribution is called `KaliSubstitute` and is the app's own. Hard rules:

1. The app only ever names its own distribution.
2. It never runs `wsl --shutdown`. WSL2 hosts every distribution in one VM;
   shutting that VM down disturbs Docker Desktop and the user's own distros.
3. It never terminates, exports or unregisters any other distribution.

## Components

```
 Windows side
 ┌────────────────────────────────────────────────────────────┐
 │ app/main.py          launcher: backend, launch code, window  │
 │ app/runtime.py       WSL2 lifecycle: status/setup/import/agent│
 │ ui/index.html        the single page and its nav views        │
 │ ui/app.js            dashboard, tool panels, forms, settings  │
 │ ui/utils.js + panel scripts (history, notebook, containers,  │
 │   playground, recordings, achievements, cheat_sheets,        │
 │   onboarding); styles.css and containers.css                 │
 │ server/app.py        Flask app factory + routes              │
 │ server/security.py   tokens, CSRF, CSP/headers, scope guard  │
 │ server/config.py     runtime settings from KWS_* variables   │
 │ server/commands.py   form fields -> argv list (BUILDERS)     │
 │ server/tools.py      agent transport, run/install/remove     │
 │ server/catalog.py    reads catalog/tools.yaml                │
 │ server/db.py         sqlite: findings, audit, settings       │
 │ server/report.py     escaped HTML / JSON / CSV reports       │
 │ server/ai.py         optional AI: Ollama, OpenAI-compatible, │
 │                      Anthropic, Gemini                       │
 │ server/mcp_server.py MCP server for other AI apps            │
 │ server/ (also)       backup, container_runtime, playground,  │
 │   recordings, achievements, history, notebook, onboarding,   │
 │   cheat_sheets                                               │
 │ kws/paths.py         resource + user-data paths              │
 │ kws/secrets.py       DPAPI-protected secrets                 │
 └────────────────────────────────────────────────────────────┘
                       │ loopback HTTP + bearer token
                       ▼
 Private WSL2 distribution: KaliSubstitute
 ┌────────────────────────────────────────────────────────────┐
 │ runtime/agent/agent.py      stdlib HTTP server (127.0.0.1)   │
 │ /etc/kalisub/tools.json     manifest generated from catalog  │
 │ /etc/kalisub/agent.env      bearer token (chmod 600)         │
 │ /usr/local/bin/kalisub-agent-start                           │
 └────────────────────────────────────────────────────────────┘
```

## Trust boundaries

| Boundary | Control |
| --- | --- |
| Browser/UI to backend | loopback only; HttpOnly session cookie; CSRF token on writes; strict CSP; `X-Frame-Options: DENY` |
| Backend to agent | loopback only inside the distro; bearer token on every request |
| Agent to the operating system | argv list with `shell=False`; `argv[0]` must equal the binary declared for that tool in `tools.json`; argument sanity checks; timeout; output cap |
| Model output to action | the AI can only *propose*; the UI must show a confirm button; the scope guard still applies |
| Report output to a document | every value is HTML-escaped; reports are served as downloads, so they never run in the app's own origin |

## How the window gets its session

The launcher starts the backend on loopback and opens the window at
`/?launch=<code>`, where `<code>` is a one-time launch code generated for that
run. The backend checks the code in constant time, spends it on first use, and
answers with a redirect to a clean `/` that sets two cookies: an HttpOnly
session cookie that the page script cannot read, and a CSRF cookie that the UI
echoes back on every write (double-submit). The session secret therefore never
appears in the address bar, the browser history or a log. The app does not use a
`?token=` URL.

## The scope guard

`server/security.py` classifies a target:

- empty -> allowed;
- `127.0.0.0/8`, `10/8`, `172.16/12`, `192.168/16`, `169.254/16`, `localhost` ->
  allowed;
- anything else, including any hostname -> **refused unless the user ticked the
  confirmation box**, and the confirmation is recorded in the audit log.

The same check runs again inside the agent, so a compromised or buggy backend
cannot skip it.

## Command construction

`server/commands.py` returns an **argv list** or `None`:

```python
build("nmap", {"target": "10.0.0.1", "profile": "service"}, ctx)
# -> ["nmap", "-sV", "-T4", "10.0.0.1"]
```

Because values are list elements and the agent uses `shell=False`, a value like
`10.0.0.1; rm -rf /` is inert data. Tools that cannot be expressed safely return
`None`, and the UI says so instead of pretending to support them.

## Adding a tool

Two files:

1. `catalog/tools.yaml` — the entry (name, package, prerequisites, usage,
   examples). This is enough for the dashboard, the manager and the docs.
2. `server/commands.py` — only if the app should drive the tool with a form.

Then regenerate the docs and the runtime manifest:

```bash
python tools/gen_docs.py
python runtime/tools/make_manifest.py catalog/tools.yaml runtime/rootfs/etc/kalisub/tools.json
```

## Local data

Everything writable lives under `%LOCALAPPDATA%\KaliWindowsSubstitute`:

```
kws.sqlite3     findings, audit log, settings
secrets/        DPAPI-encrypted blobs (one AI key per provider)
evidence/       files you drop in for the forensics tools
work/           generated wordlists/hashes the tools consume
wsl/            the imported distribution's virtual disk
```

This directory is not the repository, and the repository ignores anything that
looks like it (see `.gitignore`).


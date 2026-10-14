# Contributing

Thanks for helping. This project has one organising rule: **`catalog/tools.yaml`
is the single source of truth.** If a fact about a tool is not in the catalog,
the UI, the Tool manager and the docs do not know it.

## Getting set up

```powershell
git clone <your-fork> Kali-Windows-Substitute
cd Kali-Windows-Substitute
python -m pip install -r requirements-dev.txt
pre-commit install          # gitleaks + hygiene checks, optional but recommended
python -m pytest -q
python app/main.py --check
```

## The most common contribution: add a tool

1. Add an entry to `catalog/tools.yaml`:

   ```yaml
   - id: mytool
     name: My Tool
     category: information-gathering
     summary: "One or two sentences, plain English."
     packages: [mytool]
     danger: low            # low | moderate | high
     license: "MIT"
     homepage: "https://example.org/docs"
     prerequisites:
       - "The thing the user must have ready before this works."
     usage: >
       A short walkthrough written for someone who has never used it.
     examples:
       - "mytool --example target"
   ```

2. If the app should drive it with a form, add a builder in
   `server/commands.py` and register it in `BUILDERS`.
3. Regenerate the derived files:

   ```bash
   python tools/gen_docs.py
   python runtime/tools/make_manifest.py catalog/tools.yaml runtime/rootfs/etc/kalisub/tools.json
   ```

4. Add a test if you added a builder (`tests/test_commands.py`).
5. Run `python -m pytest -q` and commit the catalog, the builder, the tests and
   the regenerated docs together.

## Rules we hold to

- **Never build a shell string.** Command builders return an argv list. If a
  tool cannot be expressed that way, do not automate it: say so in the UI.
- **Never run `wsl --shutdown`.** It disrupts other distributions and Docker.
- **Never touch another distribution.** Only `cfg.runtime_distro`.
- **No secrets, no absolute paths, no telemetry.** `.env.example` only.
- **Escape everything** that comes from a tool before it reaches a report.
- **Keep the theme.** The terminal-green look is deliberate.

## Code style

- Python: `ruff` settings in `pyproject.toml`; type hints on public functions;
  `from __future__ import annotations` at the top of modules.
- JavaScript: no framework, no build step; the CSP forbids inline script, so
  everything lives in `ui/app.js`.
- Comments explain *why*, not *what*.

## Commit messages

Short imperative subject, then a body if the reason is not obvious:

```
catalog: add masscan and note the raw-socket requirement

WSL2 allows raw sockets, so masscan works, but OS detection does not.
Documented that in the entry so the panel warns the user.
```

## Pull requests

- One idea per PR where you can.
- Say what you tested: `pytest -q` and what you clicked through.
- Screenshots help for UI changes.
- Do not add a dependency without a reason in the description.

## Code of conduct

Be decent. Assume good faith. Do not use issues or PRs to ask for help attacking
systems you do not own or have permission to test.

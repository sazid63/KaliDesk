"""End-to-end test harness for Kali Linux Windows Substitute (NOT part of the app).

Drives the real app code paths a fresh user would hit:
  status -> ensure (provision) -> run tools via server.tools -> manage tools.

Also asserts the pure-python guards (scope target extraction, required-input
validation) so regressions fail loudly. Run from the repository root.
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import app.runtime as runtime  # noqa: E402
import server.commands as commands  # noqa: E402
import server.config as config  # noqa: E402
import server.tools as tools  # noqa: E402


def show(label, value):
    print(f"\n### {label}\n{value}")


def first_lines(text, n=6):
    lines = [ln for ln in str(text).splitlines() if ln.strip()]
    return "\n".join(lines[:n])


def check_guards():
    """Deterministic, no-runtime checks for the pure-python guards."""
    print("\n### guards")
    ok = True

    # Scope guard must only treat real network fields as targets.
    cases = [
        ({"file": "capture.pcap"}, ""),
        ({"query": "apache 2.4"}, ""),
        ({"hashes": "deadbeef"}, ""),
        ({"target": "10.0.0.5"}, "10.0.0.5"),
        ({"url": "http://10.0.0.5/"}, "http://10.0.0.5/"),
        ({"name": "example.com"}, "example.com"),
    ]
    for payload, expected in cases:
        got = tools._target_of(payload)
        flag = "ok" if got == expected else "FAIL"
        if got != expected:
            ok = False
        print(f"  _target_of({payload}) -> {got!r} ({flag})")

    # Required-input validation.
    req_cases = [
        ("nmap", {}, "target"),
        ("nmap", {"target": "10.0.0.5"}, None),
        ("tshark", {}, "file"),
        ("hydra", {"target": "10.0.0.5"}, "users"),
        ("lynis", {}, None),
        ("tcpdump", {}, None),
    ]
    for tool_id, payload, expected in req_cases:
        got = commands.first_missing(tool_id, payload)
        flag = "ok" if got == expected else "FAIL"
        if got != expected:
            ok = False
        print(f"  first_missing({tool_id}) -> {got!r} ({flag})")

    print("  guards:", "PASS" if ok else "FAIL")
    return ok


def main():
    cfg = config.load()
    guard_ok = check_guards()

    show("status (before)", runtime.status(cfg))
    show("ensure (provision)", runtime.ensure(cfg))
    show("status (after)", runtime.status(cfg))

    tests = [
        ("nmap", {"target": "127.0.0.1", "profile": "tcp-quick"}),
        ("netcat", {"target": "127.0.0.1", "port": "8000"}),
        ("whatweb", {"url": "http://127.0.0.1:8000", "confirm_external": True}),
        ("gobuster", {"url": "http://127.0.0.1:8000", "confirm_external": True}),
        ("ffuf", {"url": "http://127.0.0.1:8000/FUZZ", "confirm_external": True}),
        ("sqlmap", {"url": "http://127.0.0.1:8000/item?id=1", "confirm_external": True}),
        ("hydra", {"target": "127.0.0.1:2222", "users": "admin\nroot",
                   "passwords": "admin\npassword\n123456", "confirm_external": True}),
    ]

    summary = []
    for tool_id, payload in tests:
        t0 = time.time()
        try:
            result, status = tools.run(cfg, tool_id, payload, timeout=120)
        except Exception as exc:  # noqa: BLE001
            result, status = {"error": repr(exc)}, -1
        dt = time.time() - t0
        rc = result.get("rc") if isinstance(result, dict) else None
        err = result.get("error") if isinstance(result, dict) else None
        out = result.get("stdout", "") if isinstance(result, dict) else ""
        errout = result.get("stderr", "") if isinstance(result, dict) else ""
        print(f"\n--- {tool_id} -> HTTP {status} rc={rc} ({dt:.1f}s) err={err}")
        print("stdout:", first_lines(out))
        if errout:
            print("stderr:", first_lines(errout, 3))
        summary.append((tool_id, status, rc))

    # Missing required field must be a clear 400, not a broken tool run.
    r, s = tools.run(cfg, "nmap", {"profile": "tcp-quick"}, timeout=30)
    print(f"\n--- missing input (nmap, no target) -> HTTP {s} "
          f"{r.get('error') if isinstance(result, dict) else r}")
    summary.append(("missing-input", s, None))

    # Scope guard: external target without confirmation must be refused.
    r, s = tools.run(cfg, "nmap", {"target": "8.8.8.8", "profile": "tcp-quick"}, timeout=30)
    err = r.get("error") if isinstance(r, dict) else r
    print(f"--- scope guard (8.8.8.8, unconfirmed) -> HTTP {s} {err}")
    summary.append(("scope-guard", s, None))

    # Not-automated tool must return 501, not pretend.
    r, s = tools.run(cfg, "bettercap", {}, timeout=30)
    print(f"--- not-automated (bettercap) -> HTTP {s}")
    summary.append(("not-automated", s, None))

    # Tool management: install a non-baseline tool, then check presence.
    print("\n--- manage: install nikto")
    res, status = tools.install(cfg, "nikto", timeout=600)
    print("install:", status, (res or {}).get("message") or (res or {}).get("error"))
    manage = tools.manage_list(cfg)
    print("online:", manage["online"])
    nikto = next((t for t in manage["tools"] if t["name"].lower() == "nikto"), None)
    print("nikto entry present:", bool(nikto))

    # Run nikto now that it is installed.
    r, s = tools.run(cfg, "nikto", {"url": "http://127.0.0.1:8000", "confirm_external": True},
                     timeout=180)
    print(f"nikto run -> HTTP {s} rc={r.get('rc') if isinstance(r, dict) else None}")
    print(first_lines(r.get("stdout", "") if isinstance(r, dict) else "", 6))

    # Remove it again.
    res, status = tools.remove(cfg, "nikto", timeout=600)
    print("remove nikto:", status, (res or {}).get("message") or (res or {}).get("error"))

    print("\n=== SUMMARY ===")
    for row in summary:
        print(row)
    print("guards:", "PASS" if guard_ok else "FAIL")


if __name__ == "__main__":
    main()

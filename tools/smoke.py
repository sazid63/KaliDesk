#!/usr/bin/env python3
"""Install every catalog tool and run it through the real in-runtime agent.

Meant to run as root inside a Kali container (see .github/workflows/tools-smoke.yml)
or inside the KaliSubstitute distro. For each tool it:

1. installs the tool's packages through the agent's install job (so the same code
   path the app uses is exercised);
2. runs a cheap "is it really there and does it start" command through the agent;
3. for the tools with a one-click form, builds the argv with ``server.commands``
   and runs it against a local test server on 127.0.0.1.

Exit status is non-zero if anything fails. Requires only the Python standard
library plus PyYAML (``apt-get install python3-yaml``).

    python3 tools/smoke.py                  # everything
    python3 tools/smoke.py --only nmap,john # a subset
    python3 tools/smoke.py --skip-install   # tools are already installed
"""
from __future__ import annotations

import argparse
import http.server
import json
import os
import re
import secrets
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "runtime" / "tools"))

import make_manifest  # noqa: E402

import server.commands as commands  # noqa: E402

PORT = 5099
TOKEN = secrets.token_urlsafe(16)

# Tools whose "--version" does not work. (argv tail, acceptable exit codes)
SMOKE: dict[str, tuple[list[str], tuple[int, ...]]] = {
    "dig": (["-v"], (0,)),
    "whois": (["--version"], (0, 1)),
    "theHarvester": (["-h"], (0,)),
    "lynis": (["show", "version"], (0,)),
    "searchsploit": (["--help"], (0, 1, 2)),
    "gobuster": (["--help"], (0, 1, 2)),
    "ffuf": (["-V"], (0,)),
    "nikto": (["-Version"], (0, 1)),
    "nuclei": (["-version"], (0,)),
    "wapiti": (["--version"], (0,)),
    "wpscan": (["--version"], (0,)),
    "commix": (["--version"], (0,)),
    "hydra": (["-h"], (0, 255)),
    "medusa": (["-V"], (0, 1)),
    "crunch": (["-h"], (0, 1)),
    "cewl": (["--help"], (0,)),
    "aircrack-ng": (["--help"], (0, 1)),
    "bettercap": (["-version"], (0,)),
    "wifite": (["--help"], (0,)),
    "hcxpcapngtool": (["--help"], (0, 1)),
    "msfconsole": (["--version"], (0,)),
    "msfvenom": (["--help"], (0, 1)),
    "tshark": (["--version"], (0,)),
    "responder": (["--help"], (0,)),
    "nc": (["-h"], (0, 1)),
    "socat": (["-V"], (0,)),
    "weevely": (["--help"], (0, 1)),
    "foremost": (["-V"], (0,)),
    "binwalk": (["--help"], (0, 1)),
    "photorec": (["/version"], (0, 1)),
    "exiftool": (["-ver"], (0,)),
    "steghide": (["--version"], (0, 1)),
    "vol": (["--help"], (0,)),
    "fls": (["-V"], (0,)),
    "r2": (["-v"], (0,)),
    "gdb": (["--version"], (0,)),
    "strace": (["-V"], (0,)),
    "tcpdump": (["--version"], (0, 1)),
    "john": (["--version"], (0, 1)),
    "hashcat": (["--version"], (0,)),
    "masscan": (["--version"], (0, 1)),
}


# --- talking to the agent ---------------------------------------------------


def call(method: str, path: str, body: dict | None = None, timeout: int = 30) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", data=data, method=method)
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return {"error": exc.read().decode(errors="replace"), "status": exc.code}


def run_job(body: dict, limit: int) -> dict:
    started = call("POST", "/jobs", body)
    if "job" not in started:
        return {"state": "failed", "rc": None, "output": f"could not start: {started}"}
    since, out, end = 0, "", time.time() + limit
    while time.time() < end:
        snap = call("GET", f"/jobs/{started['job']}?since={since}")
        out += snap.get("output", "")
        since = snap.get("next", since)
        if snap.get("done"):
            snap["output"] = out
            return snap
        time.sleep(0.5)
    call("POST", f"/jobs/{started['job']}/cancel", {})
    return {"state": "timeout", "rc": None, "output": out}


def start_agent(manifest: dict) -> subprocess.Popen:
    # A private config directory: this never touches the real /etc/kalisub of a runtime.
    etc = Path(tempfile.mkdtemp(prefix="kalisub-smoke-"))
    (etc / "tools.json").write_text(json.dumps(manifest), encoding="utf-8")
    (etc / "agent.env").write_text(f"AGENT_TOKEN={TOKEN}\nKALISUB_PORT={PORT}\n", encoding="utf-8")
    env = {
        **os.environ,
        "KALISUB_ENV_FILE": str(etc / "agent.env"),
        "KALISUB_TOOLS_FILE": str(etc / "tools.json"),
        "KALISUB_LOG": str(etc / "agent.log"),
    }
    proc = subprocess.Popen(  # noqa: S603
        [sys.executable, str(ROOT / "runtime" / "agent" / "agent.py")], env=env
    )
    for _ in range(40):
        try:
            if call("GET", "/health").get("ok"):
                return proc
        except OSError:
            pass  # not listening yet
        time.sleep(0.25)
    proc.kill()
    raise SystemExit("the agent did not start")


# --- the checks -------------------------------------------------------------


def smoke_tool(tool: dict, install: bool, results: list) -> None:
    tool_id, binary = tool["id"], tool["binary"]
    if not binary or not tool.get("packages"):
        return
    if install:
        job = run_job({"kind": "install", "tool": tool_id}, 1500)
        if job.get("state") != "done":
            results.append((tool_id, "install", False, (job.get("output") or "")[-300:]))
            return
        results.append((tool_id, "install", True, ""))
    tail, ok_rcs = SMOKE.get(binary, (["--version"], (0,)))
    job = run_job(
        {"kind": "run", "tool": tool_id, "argv": [binary, *tail], "target": "", "timeout": 90}, 120
    )
    ok = job.get("state") in ("done", "failed") and job.get("rc") in ok_rcs
    results.append((tool_id, "starts", ok, "" if ok else (job.get("output") or "")[-300:]))


def serve_local_target() -> tuple[http.server.ThreadingHTTPServer, int]:
    docroot = tempfile.mkdtemp(prefix="smoke-www-")
    (Path(docroot) / "index.html").write_text("<html><title>smoke</title><p>hello</p></html>")

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=docroot, **k)

        def log_message(self, *a):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Quiet)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1]


def smoke_forms(results: list, only: set[str], port: int) -> None:
    work = Path(tempfile.mkdtemp(prefix="smoke-work-"))
    evidence = Path(tempfile.mkdtemp(prefix="smoke-ev-"))
    (evidence / "sample.txt").write_text("hello world\n")
    (evidence / "sample.bin").write_bytes(b"\x7fELF" + b"\x00" * 64)
    # A valid, empty classic pcap (the repo's dummy.pcap is only a text placeholder).
    header = struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 1)
    (evidence / "dummy.pcap").write_bytes(header)
    (work / "hashes.txt").write_text("5f4dcc3b5aa765d61d8327deb882cf99\n")
    (work / "users.txt").write_text("root\n")
    (work / "passwords.txt").write_text("toor\n")
    ctx = {
        "work": str(work),
        "files": {
            "hashes.txt": str(work / "hashes.txt"),
            "users.txt": str(work / "users.txt"),
            "passwords.txt": str(work / "passwords.txt"),
        },
        "evidence": {p.name: str(p) for p in evidence.iterdir()},
    }
    url = f"http://127.0.0.1:{port}/"
    cases = [
        ("nmap", {"target": "127.0.0.1", "profile": "host-discovery"}, "Host is up"),
        ("whatweb", {"url": url}, "smoke"),
        ("netcat", {"target": "127.0.0.1", "port": str(port)}, ""),
        ("socat", {"target": "127.0.0.1", "port": str(port)}, ""),
        ("crunch", {"min": "1", "max": "2", "charset": "ab"}, "ab"),
        ("john", {"hashes": "x"}, ""),
        ("exiftool", {"file": "sample.txt"}, "File Name"),
        ("binwalk", {"file": "sample.bin"}, "DECIMAL"),
        ("tshark", {"file": "dummy.pcap"}, ""),
        ("gobuster", {"url": url}, ""),
        ("searchsploit", {"query": "apache"}, ""),
    ]
    for tool_id, payload, expect in cases:
        if only and tool_id not in only:
            continue
        if tool_id == "tshark" and "dummy.pcap" not in ctx["evidence"]:
            continue
        try:
            argv = commands.build(tool_id, payload, ctx)
        except commands.BadInput as exc:
            results.append((tool_id, "form", False, f"form refused good input: {exc}"))
            continue
        job = run_job(
            {"kind": "run", "tool": tool_id, "argv": argv, "target": "127.0.0.1", "timeout": 120},
            150,
        )
        ok = job.get("state") in ("done", "failed") and expect in (job.get("output") or "")
        # failed (non-zero rc) is acceptable only for tools that exit 1 on "nothing found".
        if job.get("state") == "failed" and tool_id not in ("gobuster", "searchsploit", "john"):
            ok = False
        results.append((tool_id, "form", ok, "" if ok else (job.get("output") or "")[-300:]))

    # john: crack the md5 of "password" with rockyou, end to end.
    if (not only or "john" in only) and not Path(commands.ROCKYOU).exists():
        results.append(("john", "rockyou wordlist", False,
                        f"{commands.ROCKYOU} is missing: run Set up runtime (it installs the "
                        "wordlists package and unpacks rockyou)"))
    elif not only or "john" in only:
        try:
            # A throw-away pot file: each run starts fresh and never touches ~/.john/john.pot.
            argv = commands.build("john", {"hashes": "x"}, ctx) + [
                "--format=raw-md5", f"--pot={work / 'smoke.pot'}"]
            job = run_job(
                {"kind": "run", "tool": "john", "argv": argv, "target": "", "timeout": 120}, 150
            )
            # john prints a cracked hash as "password   (?)"; "Loaded 1 password hash" is not it.
            plain = re.sub(r"\[[0-9;]*m", "", job.get("output") or "")  # john colours its output
            cracked = re.search(r"^password\s+\(", plain, re.M) is not None
            results.append(("john", "cracks md5", cracked,
                            "" if cracked else (job.get("output") or "")[-300:]))
        except commands.BadInput as exc:
            results.append(("john", "cracks md5", False, str(exc)))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", default="", help="comma-separated tool ids")
    parser.add_argument("--skip-install", action="store_true")
    parser.add_argument("--no-forms", action="store_true")
    args = parser.parse_args()
    only = {t for t in args.only.split(",") if t}

    if not args.skip_install and os.geteuid() != 0:
        print("run as root (it installs packages and writes /etc/kalisub)", file=sys.stderr)
        return 2
    manifest = make_manifest.build(ROOT / "catalog" / "tools.yaml")
    agent = start_agent(manifest)
    server, port = serve_local_target()
    results: list[tuple[str, str, bool, str]] = []
    try:
        for tool in manifest["tools"]:
            if only and tool["id"] not in only:
                continue
            smoke_tool(tool, not args.skip_install, results)
        if not args.no_forms:
            smoke_forms(results, only, port)
    finally:
        server.shutdown()
        agent.terminate()

    failed = [r for r in results if not r[2]]
    width = max((len(r[0]) for r in results), default=10)
    for tool_id, step, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {tool_id:<{width}}  {step}")
        if not ok and detail:
            print("      " + detail.strip().replace("\n", "\n      "))
    print(f"\n{len(results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

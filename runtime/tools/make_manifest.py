#!/usr/bin/env python3
"""Generate ``etc/kalisub/tools.json`` from the tool catalog.

This runs on the *build host* (not inside the image) while the rootfs is being
assembled. It reads ``catalog/tools.yaml`` and writes the manifest the in-runtime
agent uses for two things: which binary a tool may execute, and which apt
packages install/remove it.

Requires PyYAML on the build host.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

# Which binary each tool id is allowed to execute. Anything not listed here is
# not runnable through the agent (it can still be installed).
BINARIES = {
    "dns": "dig",
    "whois": "whois",
    "nmap": "nmap",
    "masscan": "masscan",
    "whatweb": "whatweb",
    "dnsrecon": "dnsrecon",
    "theharvester": "theHarvester",
    "nikto": "nikto",
    "nuclei": "nuclei",
    "lynis": "lynis",
    "searchsploit": "searchsploit",
    "sqlmap": "sqlmap",
    "gobuster": "gobuster",
    "ffuf": "ffuf",
    "wpscan": "wpscan",
    "commix": "commix",
    "wapiti": "wapiti",
    "hydra": "hydra",
    "john": "john",
    "hashcat": "hashcat",
    "medusa": "medusa",
    "crunch": "crunch",
    "cewl": "cewl",
    "aircrack-ng": "aircrack-ng",
    "bettercap": "bettercap",
    "wifite": "wifite",
    "hcxtools": "hcxpcapngtool",
    "metasploit": "msfconsole",
    "msfvenom": "msfvenom",
    "tcpdump": "tcpdump",
    "tshark": "tshark",
    "responder": "responder",
    "netcat": "nc",
    "socat": "socat",
    "weevely": "weevely",
    "foremost": "foremost",
    "binwalk": "binwalk",
    "photorec": "photorec",
    "exiftool": "exiftool",
    "steghide": "steghide",
    "volatility3": "vol",
    "sleuthkit": "fls",
    "radare2": "r2",
    "gdb": "gdb",
    "strace": "strace",
}

MAX_ARGS = 48


def build(catalog_path: Path) -> dict:
    data = yaml.safe_load(Path(catalog_path).read_text(encoding="utf-8")) or {}
    tools = []
    for tool in data.get("tools", []):
        tool_id = tool.get("id")
        if not tool_id:
            continue
        packages = [str(p) for p in (tool.get("packages") or [])]
        tools.append({
            "id": tool_id,
            "name": tool.get("name", tool_id),
            "binary": BINARIES.get(tool_id, ""),
            "packages": packages,
            "repo": tool.get("repo", "debian"),
            "baseline": bool(tool.get("baseline")),
            "max_args": 32,
        })
    return {
        "generated_from": "catalog/tools.yaml",
        "tools": sorted(tools, key=lambda entry: entry["id"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    if not args.catalog.exists():
        print(f"catalog not found: {args.catalog}", file=sys.stderr)
        return 1
    manifest = build(args.catalog)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(manifest, indent=2) + "\n")
    runnable = sum(1 for entry in manifest["tools"] if entry["id"] in BINARIES)
    print(f"wrote {args.output} ({len(manifest['tools'])} tools, {runnable} runnable)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

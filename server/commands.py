"""Turn tool form fields into a concrete argv list.

Rules that keep this safe:

* We build an **argv list**, never a shell string. The in-runtime agent runs it
  with ``shell=False``, so metacharacters in a value are data, not code.
* If a tool is not automated here, ``build`` returns ``None`` and the app tells
  the user to run it from the runtime shell instead of pretending it works.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

DIRB_COMMON = "/usr/share/wordlists/dirb/common.txt"
ROCKYOU = "/usr/share/wordlists/rockyou.txt"

Context = dict[str, Any]


def _s(payload: dict[str, Any], key: str, default: str = "") -> str:
    value = payload.get(key)
    return str(value).strip() if value is not None else default


def files_for(tool_id: str, payload: dict[str, Any]) -> dict[str, str]:
    """Return small text files the command needs, as name -> content."""
    if tool_id == "hydra":
        return {
            "users.txt": _s(payload, "users"),
            "passwords.txt": _s(payload, "passwords"),
        }
    if tool_id == "medusa":
        return {"passwords.txt": _s(payload, "passwords")}
    if tool_id == "john":
        return {"hashes.txt": _s(payload, "hashes")}
    if tool_id == "hashcat":
        return {"hash.txt": _s(payload, "hash")}
    return {}


def _f(ctx: Context, name: str) -> str:
    return ctx.get("files", {}).get(name, "")


def _ev(ctx: Context, payload: dict[str, Any], key: str = "file") -> str:
    name = _s(payload, key)
    return ctx.get("evidence", {}).get(name, "")


class MissingInput(ValueError):
    """Raised when a required one-click form field is empty.

    The single argument is the field name; callers turn it into a friendly
    message rather than running the tool with a missing argument.
    """


# Fields a one-click form must fill before a tool can run. Keys match the form
# fields in ui/app.js and the payload the browser posts. Tools whose defaults
# are complete (lynis, crunch, tcpdump) are intentionally absent.
REQUIRED: dict[str, tuple[str, ...]] = {
    "dns": ("name",),
    "whois": ("query",),
    "nmap": ("target",),
    "masscan": ("target",),
    "whatweb": ("url",),
    "dnsrecon": ("target",),
    "theharvester": ("target",),
    "nikto": ("url",),
    "nuclei": ("url",),
    "searchsploit": ("query",),
    "sqlmap": ("url",),
    "gobuster": ("url",),
    "ffuf": ("url",),
    "wpscan": ("url",),
    "commix": ("url",),
    "wapiti": ("url",),
    "hydra": ("target", "users", "passwords"),
    "john": ("hashes",),
    "hashcat": ("hash",),
    "medusa": ("target", "user", "passwords"),
    "cewl": ("url",),
    "metasploit": ("module", "target"),
    "netcat": ("target",),
    "aircrack-ng": ("file",),
    "hcxtools": ("file",),
    "tshark": ("file",),
    "foremost": ("file",),
    "binwalk": ("file",),
    "exiftool": ("file",),
    "steghide": ("file",),
    "volatility3": ("file",),
    "sleuthkit": ("file",),
    "radare2": ("file",),
    "gdb": ("file",),
    "strace": ("file",),
}


def required_for(tool_id: str) -> list[str]:
    """Field names a one-click form must fill for this tool (may be empty)."""
    return list(REQUIRED.get(tool_id, ()))


def first_missing(tool_id: str, payload: dict[str, Any]) -> str | None:
    """Return the first empty required field name, or None if all are filled."""
    for key in REQUIRED.get(tool_id, ()):
        if not _s(payload, key):
            return key
    return None


# --- individual builders --------------------------------------------------

def _dns(p: dict, ctx: Context) -> list[str]:
    tokens = _s(p, "name").split()
    return ["dig", "+short", *tokens[:8]]


def _whois(p: dict, ctx: Context) -> list[str]:
    return ["whois", _s(p, "query")]


def _nmap(p: dict, ctx: Context) -> list[str]:
    profile = _s(p, "profile", "tcp-quick")
    flags = {
        "host-discovery": ["-sn"],
        "tcp-quick": ["-T4", "-F"],
        "service": ["-sV", "-T4"],
        "os": ["-O"],
    }.get(profile, ["-T4", "-F"])
    return ["nmap", *flags, _s(p, "target")]


def _masscan(p: dict, ctx: Context) -> list[str]:
    return ["masscan", _s(p, "target"), "-p1-1000", "--rate", "500"]


def _whatweb(p: dict, ctx: Context) -> list[str]:
    return ["whatweb", _s(p, "url")]


def _dnsrecon(p: dict, ctx: Context) -> list[str]:
    return ["dnsrecon", "-d", _s(p, "target")]


def _theharvester(p: dict, ctx: Context) -> list[str]:
    return ["theHarvester", "-d", _s(p, "target"), "-b", "duckduckgo"]


def _nikto(p: dict, ctx: Context) -> list[str]:
    return ["nikto", "-h", _s(p, "url")]


def _nuclei(p: dict, ctx: Context) -> list[str]:
    return ["nuclei", "-u", _s(p, "url"), "-tags", "cve"]


def _lynis(p: dict, ctx: Context) -> list[str]:
    return ["lynis", "audit", "system"]


def _searchsploit(p: dict, ctx: Context) -> list[str]:
    return ["searchsploit", *_s(p, "query").split()[:6]]


def _sqlmap(p: dict, ctx: Context) -> list[str]:
    argv = ["sqlmap", "-u", _s(p, "url"), "--batch"]
    if p.get("enumerate"):
        argv.append("--dbs")
    return argv


def _gobuster(p: dict, ctx: Context) -> list[str]:
    return ["gobuster", "dir", "-u", _s(p, "url"), "-w", DIRB_COMMON, "-q"]


def _ffuf(p: dict, ctx: Context) -> list[str]:
    return ["ffuf", "-u", _s(p, "url"), "-w", DIRB_COMMON, "-mc", "200,301,302"]


def _wpscan(p: dict, ctx: Context) -> list[str]:
    return ["wpscan", "--url", _s(p, "url"), "--enumerate", "vp"]


def _commix(p: dict, ctx: Context) -> list[str]:
    return ["commix", f"--url={_s(p, 'url')}", "--batch"]


def _wapiti(p: dict, ctx: Context) -> list[str]:
    return ["wapiti", "-u", _s(p, "url")]


def _hydra(p: dict, ctx: Context) -> list[str]:
    target = _s(p, "target")
    service = _s(p, "service", "ssh")
    users = _f(ctx, "users.txt")
    passwords = _f(ctx, "passwords.txt")
    if service == "http-get":
        return ["hydra", "-L", users, "-P", passwords, target, "http-get", "/"]
    if service == "http-post":
        return ["hydra", "-L", users, "-P", passwords, target, "http-post", "/"]
    return ["hydra", "-L", users, "-P", passwords, f"{service}://{target}"]


def _john(p: dict, ctx: Context) -> list[str]:
    return ["john", f"--wordlist={DIRB_COMMON}", _f(ctx, "hashes.txt")]


def _hashcat(p: dict, ctx: Context) -> list[str]:
    mode = _s(p, "mode", "0").split()[0]
    mask = _s(p, "mask")
    target = _f(ctx, "hash.txt")
    if mask:
        return ["hashcat", "-m", mode, "-a", "3", "--quiet", target, mask]
    return ["hashcat", "-m", mode, "-a", "0", "--quiet", target, DIRB_COMMON]


def _medusa(p: dict, ctx: Context) -> list[str]:
    return ["medusa", "-h", _s(p, "target"), "-u", _s(p, "user"),
            "-P", _f(ctx, "passwords.txt"), "-M", _s(p, "service", "ssh")]


def _crunch(p: dict, ctx: Context) -> list[str]:
    return ["crunch", _s(p, "min", "4"), _s(p, "max", "6"), _s(p, "charset", "abc123")]


def _cewl(p: dict, ctx: Context) -> list[str]:
    out = f"{ctx.get('work', '/tmp')}/cewl.txt"
    return ["cewl", _s(p, "url"), "-w", out, "-m", "6", "-d", "2"]


def _aircrack(p: dict, ctx: Context) -> list[str]:
    return ["aircrack-ng", "-w", ROCKYOU, _ev(ctx, p)]


def _hcxtools(p: dict, ctx: Context) -> list[str]:
    out = f"{ctx.get('work', '/tmp')}/out.hc22000"
    return ["hcxpcapngtool", "-o", out, _ev(ctx, p)]


def _metasploit(p: dict, ctx: Context) -> list[str]:
    module = _s(p, "module")
    target = _s(p, "target")
    script = f"use {module}; set RHOSTS {target}; run; exit"
    return ["msfconsole", "-q", "-x", script]


def _tcpdump(p: dict, ctx: Context) -> list[str]:
    expr = _s(p, "filter").split()
    return ["tcpdump", "-i", "any", "-n", "-c", "50", *expr[:6]]


def _tshark(p: dict, ctx: Context) -> list[str]:
    return ["tshark", "-r", _ev(ctx, p), "-q", "-z", "conv,tcp"]


def _netcat(p: dict, ctx: Context) -> list[str]:
    return ["nc", "-vz", _s(p, "target"), _s(p, "port", "22")]


def _foremost(p: dict, ctx: Context) -> list[str]:
    return ["foremost", "-i", _ev(ctx, p), "-o", f"{ctx.get('work', '/tmp')}/foremost"]


def _binwalk(p: dict, ctx: Context) -> list[str]:
    return ["binwalk", _ev(ctx, p)]


def _exiftool(p: dict, ctx: Context) -> list[str]:
    return ["exiftool", _ev(ctx, p)]


def _steghide(p: dict, ctx: Context) -> list[str]:
    return ["steghide", "extract", "-sf", _ev(ctx, p), "-p", _s(p, "passphrase")]


def _volatility(p: dict, ctx: Context) -> list[str]:
    plugin = _s(p, "plugin", "windows.pslist")
    return ["vol", "-f", _ev(ctx, p), plugin]


def _sleuthkit(p: dict, ctx: Context) -> list[str]:
    return ["fls", "-r", "-p", _ev(ctx, p)]


def _radare2(p: dict, ctx: Context) -> list[str]:
    return ["r2", "-q", "-c", "aaa; afl", _ev(ctx, p)]


def _gdb(p: dict, ctx: Context) -> list[str]:
    return ["gdb", "-q", "-batch", "-ex", "run", "-ex", "bt", _ev(ctx, p)]


def _strace(p: dict, ctx: Context) -> list[str]:
    return ["strace", "-f", "-e", "trace=network", _ev(ctx, p)]


def _searchsploit_web(p: dict, ctx: Context) -> list[str]:  # pragma: no cover
    return ["searchsploit", _s(p, "query")]


BUILDERS: dict[str, Callable[[dict[str, Any], Context], list[str]]] = {
    "dns": _dns,
    "whois": _whois,
    "nmap": _nmap,
    "masscan": _masscan,
    "whatweb": _whatweb,
    "dnsrecon": _dnsrecon,
    "theharvester": _theharvester,
    "nikto": _nikto,
    "nuclei": _nuclei,
    "lynis": _lynis,
    "searchsploit": _searchsploit,
    "sqlmap": _sqlmap,
    "gobuster": _gobuster,
    "ffuf": _ffuf,
    "wpscan": _wpscan,
    "commix": _commix,
    "wapiti": _wapiti,
    "hydra": _hydra,
    "john": _john,
    "hashcat": _hashcat,
    "medusa": _medusa,
    "crunch": _crunch,
    "cewl": _cewl,
    "aircrack-ng": _aircrack,
    "hcxtools": _hcxtools,
    "metasploit": _metasploit,
    "tcpdump": _tcpdump,
    "tshark": _tshark,
    "netcat": _netcat,
    "foremost": _foremost,
    "binwalk": _binwalk,
    "exiftool": _exiftool,
    "steghide": _steghide,
    "volatility3": _volatility,
    "sleuthkit": _sleuthkit,
    "radare2": _radare2,
    "gdb": _gdb,
    "strace": _strace,
}


def automated_ids() -> list[str]:
    return sorted(BUILDERS)


def build(tool_id: str, payload: dict[str, Any], ctx: Context) -> list[str] | None:
    fn = BUILDERS.get(tool_id)
    if fn is None:
        return None
    missing = first_missing(tool_id, payload)
    if missing is not None:
        raise MissingInput(missing)
    return [str(part) for part in fn(payload, ctx) if part]

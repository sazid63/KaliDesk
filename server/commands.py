"""Turn tool form fields into a concrete argv list.

Rules that keep this safe:

* We build an **argv list**, never a shell string. The in-runtime agent runs it
  with ``shell=False``, so metacharacters in a value are data, not code.
* A value that a tool could mistake for one of its own options (anything
  starting with ``-``) is refused, so a form field can never switch on a flag
  such as ``nmap --script`` or ``tcpdump -z``.
* Enumerated fields (services, payloads, formats) must match a fixed list.
* If a tool is not automated here, ``build`` returns ``None`` and the app says
  so instead of pretending it works. Interactive tools are opened in a runtime
  terminal instead (see ``TERMINAL_COMMANDS``).
"""

from __future__ import annotations

import ipaddress
import re
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


# Every name files_for() can return. Secret inputs are written only for a validated run,
# deleted when it ends, and swept from old work folders by server/tools.py.
SECRET_FILE_NAMES = ("users.txt", "passwords.txt", "hashes.txt", "hash.txt")


class MissingInput(ValueError):
    """Raised when a required one-click form field is empty.

    The single argument is the field name; callers turn it into a friendly
    message rather than running the tool with a missing argument.
    """


class BadInput(ValueError):
    """Raised when a field is filled but unusable for this tool.

    Unlike :class:`MissingInput`, the message itself is the user-facing
    explanation (no field-name lookup), e.g. masscan cannot resolve
    hostnames.
    """


# --- validation helpers ---------------------------------------------------

# A host, IP, CIDR, bracketed/bare IPv6 or host:port. No spaces, never starts with '-'.
_HOST_RE = re.compile(r"^[A-Za-z0-9_:\[][A-Za-z0-9._:\-\[\]/%]{0,252}$")
# A URL or host/path: starts alphanumeric (so never a flag), no whitespace/control chars.
_URL_RE = re.compile(r"^[A-Za-z0-9][^\s\x00-\x1f\x7f]{0,2047}$")
_WORD_RE = re.compile(r"^[A-Za-z0-9_.@:+=\-/]{1,128}$")
_MODULE_RE = re.compile(r"^auxiliary/(scanner|gather)/[a-z0-9_]+(/[a-z0-9_]+)*$")
_MAC_RE = re.compile(r"^([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$")

HYDRA_SERVICES = {
    "ssh", "ftp", "telnet", "smtp", "pop3", "imap", "mysql", "postgres", "vnc", "smb", "rdp",
    "http-get", "http-post",
}
MEDUSA_SERVICES = {
    "ssh", "ftp", "telnet", "smtp", "pop3", "imap", "mysql", "postgres", "vnc", "smbnt", "http",
}
MSFVENOM_PAYLOADS = {
    "linux/x64/shell_reverse_tcp", "linux/x86/shell_reverse_tcp",
    "windows/x64/shell_reverse_tcp", "windows/shell_reverse_tcp",
    "windows/x64/meterpreter/reverse_tcp", "php/meterpreter_reverse_tcp",
}
MSFVENOM_FORMATS = {"elf", "exe", "raw", "php", "py", "ps1", "asp", "war"}
VOL_PLUGINS = {
    "windows.pslist", "windows.pstree", "windows.netscan", "windows.cmdline",
    "windows.filescan", "windows.info", "linux.pslist", "linux.bash",
}
NMAP_PROFILES = {
    "host-discovery": ["-sn"],
    "tcp-quick": ["-T4", "-F"],
    "service": ["-sV", "-T4"],
    "os": ["-O"],
}


def _host(p: dict, key: str, what: str = "target") -> str:
    value = _s(p, key)
    if not _HOST_RE.match(value):
        raise BadInput(
            f"the {what} must be a host name, IP address or CIDR (no spaces, "
            "and it cannot start with '-')"
        )
    return value


def _is_private_or_local(value: str) -> bool:
    """True for localhost and private, loopback or link-local addresses (or CIDR ranges of them)."""
    if value.lower() in ("localhost", "localhost.localdomain"):
        return True
    try:
        net = ipaddress.ip_network(value, strict=False)
    except ValueError:
        return False
    return net.is_private or net.is_loopback or net.is_link_local


def _public_domain(p: dict, key: str, tool: str) -> str:
    """A domain name for tools that enumerate DNS or public sources. Refuses IPs and localhost."""
    value = _host(p, key, "domain")
    if _is_private_or_local(value) or re.fullmatch(r"[\d.]+", value):
        raise BadInput(
            f"{tool} needs a domain name such as example.com; localhost and IP addresses "
            "have no public DNS records to enumerate"
        )
    return value


def _url(p: dict, key: str = "url") -> str:
    value = _s(p, key)
    if not _URL_RE.match(value):
        raise BadInput("the URL must start with a letter or digit (for example https://example.com)")
    return value


def _word(p: dict, key: str, what: str) -> str:
    value = _s(p, key)
    if not _WORD_RE.match(value):
        raise BadInput(f"the {what} may only use letters, digits and . _ - : @ + = /")
    if value.startswith("-"):
        raise BadInput(f"the {what} cannot start with '-'")
    return value


def _int(p: dict, key: str, default: int, low: int, high: int, what: str) -> str:
    raw = _s(p, key, str(default)) or str(default)
    if not raw.isdigit() or not low <= int(raw) <= high:
        raise BadInput(f"the {what} must be a whole number from {low} to {high}")
    return str(int(raw))


def _choice(p: dict, key: str, allowed, default: str, what: str) -> str:
    value = _s(p, key, default) or default
    if value not in allowed:
        raise BadInput(f"unknown {what} '{value}'")
    return value


def _tokens(value: str, limit: int, what: str, bad_prefix: str = "-") -> list[str]:
    tokens = value.split()
    for token in tokens[:limit]:
        if token.startswith(tuple(bad_prefix)):
            raise BadInput(f"{what} cannot contain words starting with '{token[0]}'")
        if re.search(r"[\x00-\x1f\x7f]", token):
            raise BadInput(f"{what} contains control characters")
    return tokens[:limit]


def _f(ctx: Context, name: str) -> str:
    path = ctx.get("files", {}).get(name, "")
    if not path:
        raise BadInput("the list for this tool is empty - enter at least one line")
    return path


def _ev(ctx: Context, payload: dict[str, Any], key: str = "file") -> str:
    name = _s(payload, key)
    path = ctx.get("evidence", {}).get(name, "")
    if not path:
        raise BadInput(
            "choose a file from the evidence folder "
            "(it may have been removed since you opened this)"
        )
    return path


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
    "socat": ("target", "port"),
    "msfvenom": ("lhost",),
    "weevely": ("password",),
    "photorec": ("file",),
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

# Per-tool run limit in seconds (the default is 180). Tools that never end on
# their own are bounded here; hitting the limit is a normal way for them to stop.
TIMEOUTS: dict[str, int] = {
    "tcpdump": 30,
    "masscan": 300,
    "nuclei": 600,
    "sqlmap": 600,
    "wpscan": 600,
    "wapiti": 600,
    "nikto": 600,
    "hashcat": 600,
    "john": 600,
    "hydra": 600,
    "medusa": 600,
    "volatility3": 600,
    "metasploit": 300,
    "commix": 600,
    "foremost": 600,
    "photorec": 600,
}


def timeout_for(tool_id: str, default: int) -> int:
    return TIMEOUTS.get(tool_id, default)


# Interactive or interface-bound tools have no safe one-click form. They open in
# a real terminal inside the runtime instead, started with a safe passive default.
TERMINAL_COMMANDS: dict[str, list[str]] = {
    "responder": ["responder", "-I", "eth0", "-A"],  # -A = analyse only, poison nothing
    "bettercap": ["bettercap", "-iface", "eth0"],
    "wifite": ["wifite", "--help"],
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
    return ["dig", "+short", *_tokens(_s(p, "name"), 8, "the query", "-+")]


def _whois(p: dict, ctx: Context) -> list[str]:
    value = _word(p, "query", "query")
    if _is_private_or_local(value):
        raise BadInput(
            "whois looks up public domains and IP addresses; localhost and private "
            "addresses have no registry record"
        )
    return ["whois", value]


def _nmap(p: dict, ctx: Context) -> list[str]:
    profile = _s(p, "profile", "tcp-quick")
    return ["nmap", *NMAP_PROFILES.get(profile, NMAP_PROFILES["tcp-quick"]), _host(p, "target")]


def _masscan(p: dict, ctx: Context) -> list[str]:
    target = _s(p, "target")
    if not _ip_target_ok(target):
        raise BadInput(
            "masscan needs an IP address, CIDR or range "
            "(it cannot resolve hostnames — use the target's IP)"
        )
    return ["masscan", target, "-p1-1000", "--rate", "500"]


def _ip_target_ok(value: str) -> bool:
    """True if masscan can parse this target (IP, CIDR or dash range)."""
    text = (value or "").strip()
    if not text:
        return False
    if "/" in text:
        try:
            ipaddress.ip_network(text, strict=False)
            return True
        except ValueError:
            return False
    if "-" in text:
        return re.fullmatch(r"[0-9a-fA-F.:]+-[0-9a-fA-F.:]+", text) is not None
    try:
        ipaddress.ip_address(text)
        return True
    except ValueError:
        return False


def _whatweb(p: dict, ctx: Context) -> list[str]:
    return ["whatweb", _url(p)]


def _dnsrecon(p: dict, ctx: Context) -> list[str]:
    return ["dnsrecon", "-d", _public_domain(p, "target", "dnsrecon")]


def _theharvester(p: dict, ctx: Context) -> list[str]:
    return ["theHarvester", "-d", _public_domain(p, "target", "theHarvester"), "-b", "duckduckgo"]


def _nikto(p: dict, ctx: Context) -> list[str]:
    return ["nikto", "-h", _url(p)]


def _nuclei(p: dict, ctx: Context) -> list[str]:
    return ["nuclei", "-u", _url(p), "-tags", "cve", "-silent"]


def _lynis(p: dict, ctx: Context) -> list[str]:
    # Audits the Linux runtime itself, not your Windows machine.
    return ["lynis", "audit", "system", "--quick", "--no-colors"]


def _searchsploit(p: dict, ctx: Context) -> list[str]:
    terms = _tokens(_s(p, "query"), 6, "the search terms")
    return ["searchsploit", *terms]


def _sqlmap(p: dict, ctx: Context) -> list[str]:
    argv = ["sqlmap", "-u", _url(p), "--batch"]
    if p.get("enumerate"):
        argv.append("--dbs")
    return argv


def _gobuster(p: dict, ctx: Context) -> list[str]:
    return ["gobuster", "dir", "-u", _url(p), "-w", DIRB_COMMON, "-q"]


def _ffuf(p: dict, ctx: Context) -> list[str]:
    url = _url(p)
    if "FUZZ" not in url:
        raise BadInput("ffuf needs the word FUZZ in the URL, e.g. https://example.com/FUZZ")
    return ["ffuf", "-u", url, "-w", DIRB_COMMON, "-mc", "200,301,302"]


def _wpscan(p: dict, ctx: Context) -> list[str]:
    return ["wpscan", "--url", _url(p), "--enumerate", "vp", "--no-banner"]


def _commix(p: dict, ctx: Context) -> list[str]:
    return ["commix", f"--url={_url(p)}", "--batch"]


def _wapiti(p: dict, ctx: Context) -> list[str]:
    return ["wapiti", "-u", _url(p), "--flush-session"]


def _hydra(p: dict, ctx: Context) -> list[str]:
    target = _host(p, "target")
    service = _choice(p, "service", HYDRA_SERVICES, "ssh", "service")
    users = _f(ctx, "users.txt")
    passwords = _f(ctx, "passwords.txt")
    base = ["hydra", "-t", "4", "-f", "-L", users, "-P", passwords]
    if service in ("http-get", "http-post"):
        return [*base, target, service, "/"]
    return [*base, f"{service}://{target}"]


def _john(p: dict, ctx: Context) -> list[str]:
    return ["john", f"--wordlist={ROCKYOU}", _f(ctx, "hashes.txt")]


def _hashcat(p: dict, ctx: Context) -> list[str]:
    mode = _int(p, "mode", 0, 0, 99999, "hash type (-m)")
    mask = _s(p, "mask")
    target = _f(ctx, "hash.txt")
    base = ["hashcat", "-m", mode, "--quiet", "--potfile-disable", "--force"]
    if mask:
        if not re.fullmatch(r"[?\w]{1,64}", mask) or mask.startswith("-"):
            raise BadInput("the mask may only use ?d ?l ?u ?s ?a and literal characters")
        return [*base, "-a", "3", target, mask]
    return [*base, "-a", "0", target, ROCKYOU]


def _medusa(p: dict, ctx: Context) -> list[str]:
    return [
        "medusa",
        "-h", _host(p, "target"),
        "-u", _word(p, "user", "username"),
        "-P", _f(ctx, "passwords.txt"),
        "-M", _choice(p, "service", MEDUSA_SERVICES, "ssh", "service"),
    ]


def _crunch(p: dict, ctx: Context) -> list[str]:
    low = _int(p, "min", 4, 1, 12, "minimum length")
    high = _int(p, "max", 6, int(low), 12, "maximum length")
    charset = _s(p, "charset", "abc123") or "abc123"
    if not re.fullmatch(r"[A-Za-z0-9]{1,36}", charset):
        raise BadInput("the characters may only be letters and digits")
    if len(charset) ** int(high) > 20_000_000:
        raise BadInput("that would generate too many words - use fewer characters or a shorter max")
    return ["crunch", low, high, charset]


def _cewl(p: dict, ctx: Context) -> list[str]:
    out = f"{ctx.get('work', '/tmp')}/cewl.txt"
    return ["cewl", _url(p), "-w", out, "-m", "6", "-d", "2"]


def _aircrack(p: dict, ctx: Context) -> list[str]:
    argv = ["aircrack-ng", "-w", ROCKYOU]
    bssid = _s(p, "bssid")
    essid = _s(p, "essid")
    if bssid:
        if not _MAC_RE.match(bssid):
            raise BadInput("the BSSID must look like AA:BB:CC:DD:EE:FF")
        argv += ["-b", bssid]
    elif essid:
        argv += ["-e", _word(p, "essid", "network name")]
    return [*argv, _ev(ctx, p)]


def _hcxtools(p: dict, ctx: Context) -> list[str]:
    out = f"{ctx.get('work', '/tmp')}/out.hc22000"
    return ["hcxpcapngtool", "-o", out, _ev(ctx, p)]


def _metasploit(p: dict, ctx: Context) -> list[str]:
    module = _s(p, "module")
    if not _MODULE_RE.match(module):
        raise BadInput(
            "only auxiliary scanner/gather modules can be run from the form, e.g. "
            "auxiliary/scanner/http/http_version. Exploit modules are run in the terminal."
        )
    target = _host(p, "target", "target")
    script = f"use {module}; set RHOSTS {target}; run; exit"
    return ["msfconsole", "-q", "-x", script]


def _tcpdump(p: dict, ctx: Context) -> list[str]:
    expr = _tokens(_s(p, "filter"), 6, "the capture filter")
    count = _int(p, "count", 20, 1, 500, "packet count")
    return ["tcpdump", "-i", "any", "-n", "-c", count, *expr]


def _tshark(p: dict, ctx: Context) -> list[str]:
    return ["tshark", "-r", _ev(ctx, p), "-q", "-z", "conv,tcp"]


def _netcat(p: dict, ctx: Context) -> list[str]:
    port = _int(p, "port", 22, 1, 65535, "port")
    return ["nc", "-vz", "-w", "5", _host(p, "target"), port]


def _socat(p: dict, ctx: Context) -> list[str]:
    # Open a TCP connection, print what the service sends first (its banner), then close.
    port = _int(p, "port", 22, 1, 65535, "port")
    host = _host(p, "target")
    return ["socat", "-T", "5", "-", f"TCP:{host}:{port},connect-timeout=5"]


def _msfvenom(p: dict, ctx: Context) -> list[str]:
    payload = _choice(p, "payload", MSFVENOM_PAYLOADS, "linux/x64/shell_reverse_tcp", "payload")
    fmt = _choice(p, "format", MSFVENOM_FORMATS, "elf", "format")
    lhost = _host(p, "lhost", "listener host (LHOST)")
    lport = _int(p, "lport", 4444, 1, 65535, "listener port (LPORT)")
    out = f"{ctx.get('work', '/tmp')}/payload.{fmt}"
    return ["msfvenom", "-p", payload, f"LHOST={lhost}", f"LPORT={lport}", "-f", fmt, "-o", out]


def _weevely(p: dict, ctx: Context) -> list[str]:
    password = _word(p, "password", "password")
    return ["weevely", "generate", password, f"{ctx.get('work', '/tmp')}/agent.php"]


def _photorec(p: dict, ctx: Context) -> list[str]:
    out = f"{ctx.get('work', '/tmp')}/photorec"
    return [
        "photorec", "/d", f"{out}/", "/cmd", _ev(ctx, p),
        "partition_none,fileopt,everything,enable,search",
    ]


def _foremost(p: dict, ctx: Context) -> list[str]:
    # Foremost refuses to write into a directory that already exists, so give
    # every run its own subdirectory under the shared work dir.
    return ["foremost", "-i", _ev(ctx, p), "-o", f"{ctx.get('work', '/tmp')}/foremost"]


def _binwalk(p: dict, ctx: Context) -> list[str]:
    return ["binwalk", _ev(ctx, p)]


def _exiftool(p: dict, ctx: Context) -> list[str]:
    return ["exiftool", _ev(ctx, p)]


def _steghide(p: dict, ctx: Context) -> list[str]:
    # An explicit (possibly empty) passphrase stops steghide from prompting on stdin.
    out = f"{ctx.get('work', '/tmp')}/steghide-extracted"
    return ["steghide", "extract", "-sf", _ev(ctx, p), "-p", _s(p, "passphrase"), "-xf", out, "-f"]


def _volatility(p: dict, ctx: Context) -> list[str]:
    plugin = _choice(p, "plugin", VOL_PLUGINS, "windows.pslist", "plugin")
    return ["vol", "-f", _ev(ctx, p), plugin]


def _sleuthkit(p: dict, ctx: Context) -> list[str]:
    return ["fls", "-r", "-p", _ev(ctx, p)]


def _radare2(p: dict, ctx: Context) -> list[str]:
    return ["r2", "-q", "-c", "aaa; afl", _ev(ctx, p)]


def _gdb(p: dict, ctx: Context) -> list[str]:
    return ["gdb", "-q", "-batch", "-ex", "run", "-ex", "bt", _ev(ctx, p)]


def _strace(p: dict, ctx: Context) -> list[str]:
    return ["strace", "-f", "-e", "trace=network", _ev(ctx, p)]


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
    "socat": _socat,
    "msfvenom": _msfvenom,
    "weevely": _weevely,
    "photorec": _photorec,
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
    return [str(part) for part in fn(payload, ctx)]

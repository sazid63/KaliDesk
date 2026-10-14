# Online test dummies

Public internet targets used to verify the app's tools with real online
access. Every host below **explicitly invites** this kind of traffic. Do NOT
swap in other internet hosts — scanning anything else without written
permission is out of scope (see `docs/ACCEPTABLE_USE.md`).

| URL / host | Run by | Authorised for |
|---|---|---|
| `https://scanme.nmap.org` (45.33.32.156) | Nmap Project | Port/address scans (`nmap`, plus `masscan` by IP — masscan cannot resolve hostnames). Policy: scan it gently, do not DoS, do not scan other hosts on that network. See `https://nmap.org/book/man.html`. |
| `http://demo.testfire.net` | IBM / Altoro Mutual | Deliberately vulnerable demo bank; primary target for `gobuster`, `ffuf`, `sqlmap`, `wapiti`, `nuclei`, `whatweb`. Built to be scanned; still keep runs light and sequential. |
| `https://demo.owasp-juice.shop` | OWASP | Vulnerable-by-design demo shop (backup target for scanner checks). |
| `https://testphp.vulnweb.com` | Acunetix | Deliberately vulnerable demo shop — **currently down** (unreachable since at least 2026-10-14; the whole vulnweb family including `testhtml5` is dark). Keep as fallback if it returns. |
| `https://httpbin.org` | Runscope/ community | Plain HTTP-method testing (`whatweb`, light `ffuf`). A debugging echo service, not a scan target — keep it to single requests. |
| `https://example.com` | IANA (RFC 2606) | Reserved documentation domain. Safe for single passive fetches and DNS/WHOIS lookups (`dns`, `whois`, `whatweb`, `cewl`). Not a scan target — no directory fuzzing or vuln scans against it. |

## Verified online runs (2026-10-14)

Each run went through the real backend (`tools.run` with explicit
`confirm_external: true`), one tool at a time. On-demand tools were installed
first via the Tool manager path and removed afterwards.

| Tool | Target | Result |
|---|---|---|
| `dns` | example.com | OK (resolved) |
| `whois` | example.com | OK |
| `nmap` tcp-quick | scanme.nmap.org | OK |
| `masscan` | 45.33.32.156 | OK (port 80 found). Hostnames are refused with a clear message — masscan cannot resolve them. |
| `netcat` | scanme.nmap.org:80 | OK (open) |
| `whatweb` | example.com, testfire | OK (fingerprinted) |
| `dnsrecon` | example.com | OK |
| `theharvester` | example.com | OK |
| `cewl` | example.com | OK |
| `gobuster` | demo.testfire.net | OK (full wordlist, found `admin → /login.jsp`) |
| `ffuf` | demo.testfire.net | OK (full wordlist) |
| `sqlmap --batch` | demo.testfire.net | OK (ran to completion) |
| `nuclei -tags cve` | demo.testfire.net | OK (templates fetched, ran to completion) |
| `wapiti` | demo.testfire.net | Runs correctly but its crawl exceeds a 300 s polite budget (killed by timeout, rc=124). Retest with a longer window if a full report is needed. |
| `commix` | — | Cannot be installed in this image snapshot: it pulls `metasploit-framework`, whose `oracle-instantclient-basic` dependency has no installable candidate. Correctly refused (409) when run while absent. |

## Deliberately NOT tested online

- `hydra`, `medusa` — login brute-forcers. There is no public host that
  authorises password guessing; these are verified against local dummy
  listeners only.
- `masscan` — an internet-scale scanner; running it at full speed at anything
  is indistinguishable from an attack. Verified locally only.
- Offline tools (`john`, `hashcat`, `crunch`, `binwalk`, `exiftool`,
  `foremost`, `steghide`, `tshark`, `aircrack-ng`, `hcxtools`, `volatility3`,
  `sleuthkit`, `radare2`, `gdb`, `strace`, `tcpdump`, `lynis`,
  `searchsploit`) — no network target exists by design; verified with the
  local files in this folder.
- `nikto` — currently has no install candidate in the Kali rolling snapshot
  used by the runtime image, so it cannot be installed or tested yet.
- `wpscan` — needs an authorised WordPress target; none on this list, so it
  stays untested online until one is added here with its policy.
- `nuclei` — needs its template collection (large first-time download); tested
  only if templates are already present in the image.
- `metasploit` — only light auxiliary banner modules against `scanme.nmap.org`
  and only if the framework is already installed (it is hundreds of MB).

## Rules for online runs

1. One tool at a time, short timeouts (60–180 s), light profiles.
2. Every external target passes with `confirm_external: true` — the scope
   guard must see explicit confirmation for anything off-loopback.
3. If a host stops responding, stop the run. Being invited to scan is not
   permission to hammer.

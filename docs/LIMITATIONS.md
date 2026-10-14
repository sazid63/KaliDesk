# Limitations

Being honest about what this is and is not.

## WSL2 networking

WSL2 puts the Linux side behind a NAT. That has consequences:

- **Inbound connections to the Linux side need a port proxy.** A listener you
  start with `netcat` inside the runtime is not reachable from your LAN without
  `netsh interface portproxy` and a firewall rule.
- **A "scan" of your LAN reaches the LAN through the WSL NAT.** It works
  (`nmap -sn 192.168.1.0/24` sees your devices), but packets are rewritten, so
  tools that depend on seeing their own source address, or on receiving
  unsolicited traffic, may behave differently than on a native Kali host.
- **Passive capture sees the WSL interface, not your Wi-Fi card.** `tcpdump` and
  `tshark` capture traffic that reaches the WSL VM. To capture your real Wi-Fi or
  Ethernet traffic you need `pktmon`/`netsh trace` on Windows and to analyse the
  capture in the runtime.

## Raw sockets

`nmap -sS`, `masscan` and ARP-level tools want raw sockets. WSL2 generally allows
this because it runs a real kernel, but:

- some modes need `CAP_NET_RAW` (the app runs the agent as root, so this is fine);
- OS fingerprinting (`-O`) is unreliable through the NAT;
- ARP scanning sees the WSL virtual gateway, not your LAN's real ARP table.

## Wireless

WSL2 has no direct access to your Wi-Fi hardware. Passive wireless tooling that
needs a monitor-mode interface (`aircrack-ng` capture, `bettercap` Wi-Fi modules,
`wifite`, `hcxpcapngtool`) cannot see your radio from inside WSL2.

Workarounds, in order of honesty:

1. Capture on Windows, then analyse the file in the runtime (the catalog's
   `aircrack-ng`, `hcxtools` and `tshark` entries take an evidence file for
   exactly this);
2. pass a USB Wi-Fi adapter through to WSL2 with `usbipd-win`
   (<https://github.com/dorssel/usbipd-win>) — support is limited and kernel
   driver dependent;
3. use a native Kali install for wireless work. The app does not pretend to
   solve this.

## Imported, not installed to the system

The distribution lives in `%LOCALAPPDATA%`. If you delete that folder you lose
the runtime and the app's database. The uninstaller asks before removing it.

## Tool coverage

`catalog/tools.yaml` documents every tool the app knows about, but only a subset
has a one-click form. For the rest the app installs the tool and gets out of the
way: its prerequisites and usage are in the panel, and you run it from the
runtime shell. It will tell you this rather than fail silently.

## Reporting

The built-in report is a findings/audit export (HTML, JSON, CSV). It is not a
Dradis or a full engagement report template.

## Platforms

Windows only. macOS and Linux are not supported targets, and the secrets layer
uses the Windows DPAPI.

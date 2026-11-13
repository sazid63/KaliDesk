# Third-party notices

This project is MIT-licensed (see [LICENSE](LICENSE)). It does **not** vendor the
tools it runs. Instead, the runtime image is built from distribution packages,
and each tool keeps its own licence. This file summarises them and points at the
per-tool pages under [docs/tools/](docs/tools/) for details.

## Names and trademarks

"Kali Linux" and the Kali logo are trademarks of OffSec Services Limited. This
project is **not affiliated with, endorsed by or connected to** OffSec or the
Kali Linux project. It is an independent workbench that installs Debian/Kali
packages into a private WSL2 distribution.

The project's own name ("Kali Linux Windows Substitute") is descriptive and is
not a claim of any relationship with OffSec.

## Licences of the tools the catalog can install

The table below is generated from the `license` field of each entry in
`catalog/tools.yaml` by `tools/gen_docs.py`. Do not edit it by hand: change the
catalog entry and re-run the generator. The built-in report is this project's
own code and is left out.

<!-- BEGIN GENERATED: tool licences -->
| Tool | Catalog id | Licence (from `catalog/tools.yaml`) |
| --- | --- | --- |
| DNS Lookup (dig) | `dns` | ISC |
| WHOIS Lookup | `whois` | GPL-2.0 |
| Nmap | `nmap` | NPSL (not OSI-approved; bundled with the runtime for convenience) |
| Masscan | `masscan` | AGPL-3.0 |
| WhatWeb | `whatweb` | GPL-2.0 |
| DNSRecon | `dnsrecon` | GPL-2.0 |
| theHarvester | `theharvester` | GPL-2.0 |
| Nikto | `nikto` | GPL-2.0 |
| Nuclei | `nuclei` | MIT |
| Lynis | `lynis` | GPL-3.0 |
| SearchSploit | `searchsploit` | GPL-2.0 |
| SQLMap | `sqlmap` | GPL-2.0 |
| Gobuster | `gobuster` | Apache-2.0 |
| ffuf | `ffuf` | MIT |
| WPScan | `wpscan` | WPScan licence (source-available; see upstream) |
| Commix | `commix` | GPL-3.0 |
| Wapiti | `wapiti` | GPL-2.0 |
| Hydra | `hydra` | GPL-3.0 |
| John the Ripper | `john` | GPL-2.0 |
| Hashcat | `hashcat` | MIT |
| Medusa | `medusa` | GPL-2.0 |
| Crunch | `crunch` | GPL-2.0 |
| CeWL | `cewl` | GPL-2.0 |
| Aircrack-ng | `aircrack-ng` | GPL-2.0 |
| Bettercap | `bettercap` | GPL-3.0 |
| Wifite | `wifite` | GPL-2.0 |
| hcxtools | `hcxtools` | MIT |
| Metasploit Framework | `metasploit` | BSD-3-Clause (plus module licences) |
| msfvenom | `msfvenom` | BSD-3-Clause |
| tcpdump | `tcpdump` | BSD-3-Clause |
| Packet Analysis (tshark) | `tshark` | GPL-2.0 |
| Responder | `responder` | GPL-3.0 |
| Netcat | `netcat` | GPL-2.0 |
| Socat | `socat` | GPL-2.0 |
| Weevely | `weevely` | GPL-3.0 |
| Foremost | `foremost` | Public domain (US Air Force) |
| Binwalk | `binwalk` | MIT |
| PhotoRec | `photorec` | GPL-2.0 |
| ExifTool | `exiftool` | Perl Artistic / GPL |
| Steghide | `steghide` | GPL-2.0 |
| Volatility 3 | `volatility3` | GPL-2.0 |
| The Sleuth Kit | `sleuthkit` | CPL / IBM Public License |
| Radare2 | `radare2` | LGPL-3.0 |
| GDB | `gdb` | GPL-3.0 |
| strace | `strace` | GPL-2.0 |
<!-- END GENERATED: tool licences -->

Notes on the table:

- The catalog licence is a summary of each upstream project's licence, recorded
  for orientation. Read the upstream licence before you redistribute a tool.
- **nmap** is under the Nmap Public Source License, which is not OSI-approved.
  See the nmap section below.
- **WPScan** is source-available under its own licence with usage terms. Read it
  before using it against anything.
- Volatility 3 is listed under its catalog licence. The memory *samples* you
  might analyse are not part of this project.

## nmap

nmap ships under the **Nmap Public Source License (NPSL)**, which is *not*
OSI-approved. It is included in the runtime image for convenience only, on the
same terms as the Kali/Debian package. If you redistribute nmap, read the NPSL
and the "nmap Public Source License" FAQ:

- <https://nmap.org/npsl/>
- <https://nmap.org/book/man-legal.html>

Some features (the Nmap Scripting Engine, `nmap -oX` output combined with the
Windows GUI) have their own conditions. If you redistribute this project *with*
an image containing nmap, you must pass those conditions through.

## Other components

These are the Python packages and runtimes that the app itself needs, either
directly (`requirements.txt`) or as dependencies of those packages, when it is
run from source or bundled as the Windows installer. Licences were checked
against the package metadata in the build environment.

| Component | Licence |
| --- | --- |
| Python (CPython) | PSF-2.0 |
| Flask | BSD-3-Clause |
| Werkzeug | BSD-3-Clause |
| Jinja2 | BSD-3-Clause |
| MarkupSafe | BSD-3-Clause |
| click | BSD-3-Clause |
| itsdangerous | BSD-3-Clause |
| blinker | MIT |
| PyYAML | MIT |
| pywebview | BSD-3-Clause |
| pythonnet | MIT |
| clr_loader | MIT |
| cffi | MIT |
| bottle | MIT |
| proxy_tools | MIT |
| setuptools | MIT |
| WSL2 | Microsoft's terms (Windows component; not redistributed here) |
| Kali / Debian base packages in the image | each package's own licence |

The rootfs image is built from distribution packages with `debootstrap`. If you
redistribute a built image, you are redistributing hundreds of packages, and you
should include their licences (most distros ship them under
`/usr/share/doc/<package>/copyright`) in the same way the distribution does.

## Original code

The application code, the catalog, the agent, the installer scripts and the
documentation in this repository are original work under the MIT licence.

---

If you believe something here is inaccurate, please open an issue — getting
licensing right matters more than being tidy.

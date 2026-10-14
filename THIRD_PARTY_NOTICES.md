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

The catalog records a licence for every entry. Grouped by licence family:

| Licence | Tools |
| --- | --- |
| MIT | nuclei, ffuf, binwalk, hcxtools, volatility3(1) |
| Apache-2.0 | gobuster |
| BSD-3-Clause | metasploit (plus module licences), msfvenom, tcpdump |
| ISC | dns (dig / BIND) |
| GPL-2.0 | whois, whatweb, dnsrecon, theharvester, nikto, searchsploit, sqlmap, hashcat, medusa, crunch, cewl, aircrack-ng, wifite, tshark, netcat, foremost, photorec, steghide, strace |
| GPL-3.0 | lynis, wpscan(2), commix, wapiti, hydra, john, bettercap, responder, socat, weevely, gdb |
| AGPL-3.0 | masscan |
| LGPL-3.0 | radare2 |
| CPL / IBM Public License | sleuthkit |
| Public domain (US Air Force) | exiftool(3) |
| Perl Artistic / GPL | exiftool |
| Source-available | wpscan (WPScan licence) |

Notes:

1. Volatility 3 is MIT; the memory *samples* you might analyse are not part of
   this project.
2. WPScan is source-available under its own licence with usage terms. Read it
   before using it against anything.
| NPSL | nmap — **not OSI-approved**. See below. |

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

| Component | Licence |
| --- | --- |
| Python | PSF-2.0 |
| Flask | BSD-3-Clause |
| PyYAML | MIT |
| pywebview | BSD-3-Clause |
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

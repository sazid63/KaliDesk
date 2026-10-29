/* 
 * Kali Linux Windows Substitute - Cheat Sheets Panel
 */

const CHEAT_SHEETS = {
  "nmap": {
    title: "Nmap",
    sections: [
      { heading: "Quick Scans", content_md: "-sS  (SYN scan)
-sV  (service detection)
-O  (OS detection)
-p<port>  (skip host discovery)" },
      { heading: "Full Scan", content_md: "-A  (Aggressive scan including OS, version, scripts)
-T4  (Timing template: faster)" },
      { heading: "Version Detection", content_md: "-sV
--version-light  (light)" },
      { heading: "Scripts", content_md: "-sC  (default scripts)
--script vuln  (vulnerability scripts)" },
    ]
  },
  "sqlmap": {
    title: "SQLMap",
    sections: [
      { heading: "Basic Injection", content_md: "--url "http://example.com/page?id=1"
--dump  (extract databases)
--tables  (list tables)
--columns  (list columns)" },
      { heading: "Advanced", content_md: "--tamper  (bypass WAF)
--batch  (non-interactive)
--level 5  (level 5 tests)
--risk 3  (risk level 3)" },
    ]
  },
  "john": {
    title: "John the Ripper",
    sections: [
      { heading: "Wordlist Mode", content_md: "john --wordlist=passwords.txt hashes.txt
--rules  (apply rules)" },
      { heading: "Incremental Mode", content_md: "john --incremental hashes.txt
--fork  (parallel processes)" },
    ]
  },
  "hashcat": {
    title: "Hashcat",
    sections: [
      { heading: "Basic Usage", content_md: "hashcat -m 0 -a 0 hashes.txt rockyou.txt
-m 0  (MD5)
-a 0  (brute force)" },
      { heading: "Options", content_md: "--optimize  (GPU optimization)
--quiet  (suppress output)
--status  (periodic status)" },
    ]
  },
  "tcpdump": {
    title: "Tcpdump",
    sections: [
      { heading: "Basic Capture", content_md: "tcpdump -i eth0 -w capture.pcap
-n  (skip name resolution)
-Q  (QoS)" },
      { heading: "Filtering", content_md: "tcp port 80
host 10.0.0.1
port 443 and src 192.168.1.1" },
    ]
  },
  "volatility3": {
    title: "Volatility3",
    sections: [
      { heading: "Basic Commands", content_md: "volatility3 --info
--profile=Win7SP1 image.mem --list-modules
--hashdump  (dump LSASS hashes)
--netscan  (discover hosts)" },
      { heading: "Memory analysis", content_md: "--dumpfiles  (save to disk)
--context  (system context)" },
    ]
  },
  "sleuthkit": {
    title: "Sleuthkit/Autopsy",
    sections: [
      { heading: "Commands", content_md: "fsck -v /dev/sda1
fls /dev/sda1
lns /dev/sda1
icat /dev/sda1 1 copy.txt
img_info /dev/sda1" },
      { heading: "Autopsy", content_md: "GUI-based forensic browser
opens with: autopsy /dev/sda1" },
    ]
  },
  "nikto": {
    title: "Nikto",
    sections: [
      { heading: "Basic Scan", content_md: "nikto -h http://example.com
-update  (update plugins)
-host  (single host)" },
      { heading: "SSL", content_md: "-ssl  (HTTPS)
-port 443" },
    ]
  },
  "aircrack-ng": {
    title: "Aircrack-ng",
    sections: [
      { heading: "Capture Handshake", content_md: "airodump-ng -i wlan0 --bssid AA:BB:CC:DD:EE:FF -w capture.cap
-a  (handshake accepted)" },
      { heading: "Crack", content_md: "aircrack-ng capture.cap -w wordlist.txt" },
    ]
  },
};

let currentTool = null;

async function initCheatSheets() {
  await loadToolList();
}

async function loadToolList() {
  const select = $("#cheat-sheets-tool-select");
  select.innerHTML = '<option value="">— Select a tool —</option>';
  
  Object.keys(CHEAT_SHEETS).forEach((tool) => {
    const opt = document.createElement("option");
    opt.value = tool;
    opt.textContent = tool;
    select.appendChild(opt);
  });
}

function loadCheatSheet(toolId) {
  const sheet = CHEAT_SHEETS[toolId];
  if (!sheet) return;
  
  currentTool = toolId;
  const content = $("#cheat-sheets-content");
  content.innerHTML = "";
  
  const title = document.createElement("h3");
  title.textContent = sheet.title;
  content.appendChild(title);
  
  sheet.sections.forEach((section) => {
    const sectionDiv = document.createElement("div");
    sectionDiv.className = "section";
    
    const heading = document.createElement("h4");
    heading.textContent = section.heading;
    sectionDiv.appendChild(heading);
    
    const pre = document.createElement("pre");
    pre.textContent = section.content_md;
    sectionDiv.appendChild(pre);
    
    content.appendChild(sectionDiv);
  });
}

async function wire() {
  const select = $("#cheat-sheets-tool-select");
  select.addEventListener("change", (e) => {
    loadCheatSheet(e.target.value);
  });
}

function esc(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
}

function toast(message, isError) {
  const el = $("#toast");
  el.textContent = message;
  el.classList.toggle("error", !!isError);
  el.classList.remove("hidden");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.add("hidden"), 4500);
}

function wire() {
}

wire();
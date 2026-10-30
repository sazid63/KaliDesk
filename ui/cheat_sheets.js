/* 
 * Kali Linux Windows Substitute - Cheat Sheets Panel
 */

const CHEAT_SHEETS = {
  "nmap": {
    title: "Nmap",
    sections: [
      { heading: "Quick Scans", content_md: "-sS  (SYN scan)\n-sV  (service detection)\n-O  (OS detection)\n-p<port>  (skip host discovery)" },
      { heading: "Full Scan", content_md: "-A  (Aggressive scan including OS, version, scripts)\n-T4  (Timing template: faster)" },
      { heading: "Version Detection", content_md: "-sV\n--version-light  (light)" },
      { heading: "Scripts", content_md: "-sC  (default scripts)\n--script vuln  (vulnerability scripts)" },
    ]
  },
  "sqlmap": {
    title: "SQLMap",
    sections: [
      { heading: "Basic Injection", content_md: "--url 'http://example.com/page?id=1'\n--dump  (extract databases)\n--tables  (list tables)\n--columns  (list columns)" },
      { heading: "Advanced", content_md: "--tamper  (bypass WAF)\n--batch  (non-interactive)\n--level 5  (level 5 tests)\n--risk 3  (risk level 3)" },
    ]
  },
  "john": {
    title: "John the Ripper",
    sections: [
      { heading: "Wordlist Mode", content_md: "john --wordlist=passwords.txt hashes.txt\n--rules  (apply rules)" },
      { heading: "Incremental Mode", content_md: "john --incremental hashes.txt\n--fork  (parallel processes)" },
    ]
  },
  "hashcat": {
    title: "Hashcat",
    sections: [
      { heading: "Basic Usage", content_md: "hashcat -m 0 -a 0 hashes.txt rockyou.txt\n-m 0  (MD5)\n-a 0  (brute force)" },
      { heading: "Options", content_md: "--optimize  (GPU optimization)\n--quiet  (suppress output)\n--status  (periodic status)" },
    ]
  },
  "tcpdump": {
    title: "Tcpdump",
    sections: [
      { heading: "Basic Capture", content_md: "tcpdump -i eth0 -w capture.pcap\n-n  (skip name resolution)\n-Q  (QoS)" },
      { heading: "Filtering", content_md: "tcp port 80\nhost 10.0.0.1\nport 443 and src 192.168.1.1" },
    ]
  },
  "volatility3": {
    title: "Volatility3",
    sections: [
      { heading: "Basic Commands", content_md: "volatility3 --info\n--profile=Win7SP1 image.mem --list-modules\n--hashdump  (dump LSASS hashes)\n--netscan  (discover hosts)" },
      { heading: "Memory analysis", content_md: "--dumpfiles  (save to disk)\n--context  (system context)" },
    ]
  },
  "sleuthkit": {
    title: "Sleuthkit/Autopsy",
    sections: [
      { heading: "Commands", content_md: "fsck -v /dev/sda1\nfls /dev/sda1\nlns /dev/sda1\nicat /dev/sda1 1 copy.txt\nimg_info /dev/sda1" },
      { heading: "Autopsy", content_md: "GUI-based forensic browser\nopens with: autopsy /dev/sda1" },
    ]
  },
  "nikto": {
    title: "Nikto",
    sections: [
      { heading: "Basic Scan", content_md: "nikto -h http://example.com\n-update  (update plugins)\n-host  (single host)" },
      { heading: "SSL", content_md: "-ssl  (HTTPS)\n-port 443" },
    ]
  },
  "aircrack-ng": {
    title: "Aircrack-ng",
    sections: [
      { heading: "Capture Handshake", content_md: "airodump-ng -i wlan0 --bssid AA:BB:CC:DD:EE:FF -w capture.cap\n-a  (handshake accepted)" },
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

/* $, $$, esc, toast, api provided globally by utils.js */

function wire() {
  const select = $("#cheat-sheets-tool-select");
  select.addEventListener("change", (e) => {
    loadCheatSheet(e.target.value);
  });
}

wire();
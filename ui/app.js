/* Kali Linux Windows Substitute - UI logic.
 *
 * Talks only to the loopback backend. The CSRF token is read from a cookie the
 * backend sets when the launcher opens the page and echoed in a header on every
 * write. No remote origins and no inline handlers: the CSP forbids both.
 */
"use strict";

const state = {
  catalog: null,
  tools: [],
  categories: [],
  automated: [],
  terminal: {},
  present: {},
  currentTool: null,
  evidence: [],
  manager: [],
  chat: [],
};

/* --- helpers ------------------------------------------------------------- */
/* $, $$, esc, toast, csrf, api are provided globally by utils.js (loaded first). */

/* --- form specifications -------------------------------------------------
 * Only the tools the backend can build a safe argv for appear here. Any other
 * tool still opens, explains itself, and can be installed - it just says so.
 */
const FORM_SPECS = {
  dns: [{ k: "name", label: "Domain (optionally 'MX example.com')", type: "text", placeholder: "example.com" }],
  whois: [{ k: "query", label: "Domain or IP address", type: "text", placeholder: "example.com" }],
  nmap: [
    { k: "target", label: "Target (host or CIDR)", type: "text", placeholder: "192.168.1.10" },
    { k: "profile", label: "Profile", type: "select", options: [["host-discovery", "Host discovery (ping sweep)"], ["tcp-quick", "TCP quick scan"], ["service", "Service / version scan"], ["os", "OS detection"]] },
  ],
  masscan: [{ k: "target", label: "Target range", type: "text", placeholder: "192.168.1.0/24" }],
  whatweb: [{ k: "url", label: "URL", type: "text", placeholder: "https://example.com" }],
  dnsrecon: [{ k: "target", label: "Domain", type: "text", placeholder: "example.com" }],
  theharvester: [{ k: "target", label: "Domain", type: "text", placeholder: "example.com" }],
  nikto: [{ k: "url", label: "URL", type: "text", placeholder: "https://example.com" }],
  nuclei: [{ k: "url", label: "URL", type: "text", placeholder: "https://example.com" }],
  lynis: [],
  searchsploit: [{ k: "query", label: "Search terms", type: "text", placeholder: "apache 2.4" }],
  sqlmap: [
    { k: "url", label: "URL containing a parameter", type: "text", placeholder: "https://example.com/item?id=1" },
    { k: "enumerate", label: "Also enumerate databases (--dbs)", type: "checkbox" },
  ],
  gobuster: [{ k: "url", label: "Base URL", type: "text", placeholder: "https://example.com" }],
  ffuf: [{ k: "url", label: "URL containing the word FUZZ", type: "text", value: "https://example.com/FUZZ" }],
  wpscan: [{ k: "url", label: "WordPress URL", type: "text", placeholder: "https://example.com" }],
  commix: [{ k: "url", label: "URL containing a parameter", type: "text", placeholder: "https://example.com/ping?host=127.0.0.1" }],
  wapiti: [{ k: "url", label: "URL", type: "text", placeholder: "https://example.com" }],
  hydra: [
    { k: "target", label: "Target host", type: "text", placeholder: "192.168.1.10" },
    { k: "service", label: "Service", type: "select", options: [["ssh", "SSH"], ["ftp", "FTP"], ["telnet", "Telnet"], ["smtp", "SMTP"], ["pop3", "POP3"], ["imap", "IMAP"], ["mysql", "MySQL"], ["postgres", "PostgreSQL"], ["vnc", "VNC"], ["smb", "SMB"], ["rdp", "RDP"], ["http-get", "HTTP GET"], ["http-post", "HTTP POST"]] },
    { k: "users", label: "Usernames (one per line)", type: "textarea", placeholder: "admin\nroot" },
    { k: "passwords", label: "Passwords (one per line)", type: "textarea", placeholder: "password\n123456" },
  ],
  john: [{ k: "hashes", label: "Hashes (one per line)", type: "textarea", placeholder: "5f4dcc3b5aa765d61d8327deb882cf99" }],
  hashcat: [
    { k: "hash", label: "Hash", type: "text", placeholder: "5f4dcc3b5aa765d61d8327deb882cf99" },
    { k: "mode", label: "Hash type (-m)", type: "text", value: "0" },
    { k: "mask", label: "Mask (empty = use a wordlist)", type: "text", placeholder: "?d?d?d?d" },
  ],
  medusa: [
    { k: "target", label: "Target host", type: "text", placeholder: "192.168.1.10" },
    { k: "user", label: "Username", type: "text", placeholder: "admin" },
    { k: "passwords", label: "Passwords (one per line)", type: "textarea" },
    { k: "service", label: "Service", type: "select", options: [["ssh", "SSH"], ["ftp", "FTP"], ["telnet", "Telnet"], ["smtp", "SMTP"], ["pop3", "POP3"], ["imap", "IMAP"], ["mysql", "MySQL"], ["postgres", "PostgreSQL"], ["vnc", "VNC"], ["smbnt", "SMB"], ["http", "HTTP"]] },
  ],
  crunch: [
    { k: "min", label: "Minimum length", type: "text", value: "6" },
    { k: "max", label: "Maximum length", type: "text", value: "8" },
    { k: "charset", label: "Characters to use", type: "text", value: "abc123" },
  ],
  cewl: [{ k: "url", label: "URL to crawl", type: "text", placeholder: "https://example.com" }],
  "aircrack-ng": [
    { k: "file", label: "Capture file (.cap) from the evidence folder", type: "evidence" },
    { k: "essid", label: "Network name (ESSID), needed if the capture has several networks", type: "text" },
    { k: "bssid", label: "or its BSSID (AA:BB:CC:DD:EE:FF)", type: "text" },
  ],
  hcxtools: [{ k: "file", label: "Capture file (.cap/.pcapng)", type: "evidence" }],
  metasploit: [
    { k: "module", label: "Auxiliary module", type: "text", placeholder: "auxiliary/scanner/http/http_version" },
    { k: "target", label: "Target host(s)", type: "text", placeholder: "192.168.1.10" },
  ],
  tcpdump: [
    { k: "filter", label: "Capture filter, e.g. 'port 53' (optional)", type: "text", placeholder: "port 53" },
    { k: "count", label: "Stop after this many packets (max 500; also stops after 30 s)", type: "text", value: "20" },
  ],
  socat: [
    { k: "target", label: "Target host", type: "text", placeholder: "192.168.1.10" },
    { k: "port", label: "Port", type: "text", value: "22" },
  ],
  msfvenom: [
    { k: "payload", label: "Payload", type: "select", options: [["linux/x64/shell_reverse_tcp", "Linux x64 reverse shell"], ["linux/x86/shell_reverse_tcp", "Linux x86 reverse shell"], ["windows/x64/shell_reverse_tcp", "Windows x64 reverse shell"], ["windows/shell_reverse_tcp", "Windows x86 reverse shell"], ["windows/x64/meterpreter/reverse_tcp", "Windows x64 Meterpreter"], ["php/meterpreter_reverse_tcp", "PHP Meterpreter"]] },
    { k: "format", label: "Output format", type: "select", options: [["elf", "elf"], ["exe", "exe"], ["raw", "raw"], ["php", "php"], ["py", "py"], ["ps1", "ps1"], ["asp", "asp"], ["war", "war"]] },
    { k: "lhost", label: "Listener host (LHOST)", type: "text", placeholder: "192.168.1.5" },
    { k: "lport", label: "Listener port (LPORT)", type: "text", value: "4444" },
  ],
  weevely: [{ k: "password", label: "Agent password", type: "text", placeholder: "choose-a-password" }],
  photorec: [{ k: "file", label: "Disk image to recover files from", type: "evidence" }],
  tshark: [{ k: "file", label: "Capture file from the evidence folder", type: "evidence" }],
  netcat: [
    { k: "target", label: "Target host", type: "text", placeholder: "192.168.1.10" },
    { k: "port", label: "Port", type: "text", value: "22" },
  ],
  foremost: [{ k: "file", label: "Disk image or binary", type: "evidence" }],
  binwalk: [{ k: "file", label: "Firmware or binary", type: "evidence" }],
  exiftool: [{ k: "file", label: "Image or document", type: "evidence" }],
  steghide: [
    { k: "file", label: "Suspect file", type: "evidence" },
    { k: "passphrase", label: "Passphrase (leave empty to try none)", type: "text" },
  ],
  volatility3: [
    { k: "file", label: "Memory image", type: "evidence" },
    { k: "plugin", label: "Plugin", type: "select", options: [["windows.pslist", "Windows: process list"], ["windows.pstree", "Windows: process tree"], ["windows.netscan", "Windows: network connections"], ["windows.cmdline", "Windows: command lines"], ["windows.filescan", "Windows: file scan"], ["windows.info", "Windows: image info"], ["linux.pslist", "Linux: process list"], ["linux.bash", "Linux: bash history"]] },
  ],
  sleuthkit: [{ k: "file", label: "Disk image", type: "evidence" }],
  radare2: [{ k: "file", label: "Binary", type: "evidence" }],
  gdb: [{ k: "file", label: "Program", type: "evidence" }],
  strace: [{ k: "file", label: "Program", type: "evidence" }],
};

/* --- runtime ------------------------------------------------------------- */
// Last time we asked the backend to start the agent; a start is requested at most once per 60 s.
let lastRuntimeStart = 0;

async function refreshRuntime() {
  const { data } = await api("GET", "/api/runtime", undefined, { timeout: 30000 });
  // If the distro is installed but its agent is down, ask for a start (POST), but only when
  // nothing is already provisioning and we have not asked within the last minute.
  if (data && data.installed && !data.agent) {
    const provisioning = !!(data.provisioning && !data.provisioning.done);
    if (!provisioning && Date.now() - lastRuntimeStart >= 60000) {
      lastRuntimeStart = Date.now();
      api("POST", "/api/runtime/start", {});
    }
  }
  const dot = $("#runtime-dot");
  const text = $("#runtime-text");
  const banner = $("#setup-banner");
  dot.className = "dot";
  if (!data || data.error) {
    dot.classList.add("bad");
    text.textContent = "runtime check failed";
    banner.classList.remove("hidden");
    banner.classList.add("bad");
    $("#setup-message").textContent = (data && data.error) || "Could not check the runtime.";
    return;
  }
  const prov = data.provisioning;
  const btn = $("#setup-ensure");
  if (prov && !prov.done) {
    // Setup is running: show live progress instead of the generic offline message.
    dot.classList.add("warn");
    text.textContent = "setting up…";
    banner.classList.remove("hidden", "bad");
    $("#setup-message").textContent = provisionText(prov);
    if (btn) { btn.disabled = true; btn.textContent = "Setting up…"; }
    scheduleProvisionPoll();
  } else if (data.agent) {
    dot.classList.add("ok");
    text.textContent = "runtime online";
    banner.classList.add("hidden");
    banner.classList.remove("bad");
    if (btn) { btn.disabled = false; btn.textContent = "Set up runtime"; }
  } else {
    if (!data.wsl) dot.classList.add("bad");
    text.textContent = data.wsl ? "runtime offline" : "WSL2 missing";
    banner.classList.remove("hidden");
    const failed = !!(prov && prov.error);
    banner.classList.toggle("bad", !data.wsl || failed);
    $("#setup-message").textContent = failed ? prov.message : (data.message || "Runtime is not ready.");
    if (btn) { btn.disabled = false; btn.textContent = failed ? "Try again" : "Set up runtime"; }
  }
  $("#set-wsl").textContent = data.wsl ? "yes" : "no";
  $("#set-installed").textContent = data.installed ? "yes" : "no";
  $("#set-agent").textContent = data.agent ? "online" : "offline";
  $("#set-message").textContent = data.message || "\u2014";
}

function provisionText(prov) {
  let msg = prov.message || "Working…";
  const pr = prov.progress;
  if (pr && pr.total > 0) {
    const pct = Math.min(100, Math.round((pr.done / pr.total) * 100));
    msg += " " + pct + "% (" + Math.round(pr.done / 1048576) + " of " + Math.round(pr.total / 1048576) + " MB)";
  }
  return msg;
}

let provisionTimer = null;
function scheduleProvisionPoll() {
  if (provisionTimer) return;
  provisionTimer = setTimeout(async () => {
    provisionTimer = null;
    await refreshRuntime();
  }, 2000);
}

async function ensureRuntime() {
  const btn = $("#setup-ensure");
  btn.disabled = true;
  btn.textContent = "Setting up…";
  const { data } = await api("POST", "/api/runtime/ensure", {});
  if (!data || data.error) {
    btn.disabled = false;
    btn.textContent = "Set up runtime";
    toast((data && data.error) || "setup failed", true);
  }
  // refreshRuntime keeps polling every 2 s while setup is running.
  refreshRuntime();
}

/* --- catalog ------------------------------------------------------------- */
async function loadCatalog() {
  const { data } = await api("GET", "/api/catalog");
  if (!data || data.error) { toast(data.error || "could not load catalog", true); return; }
  state.catalog = data.app || {};
  state.tools = data.tools || [];
  state.categories = data.categories || [];
  state.automated = data.automated || [];
  state.required = data.required || {};
  state.terminal = data.terminal || {};
  renderCategories();
  renderTiles();
  loadInstalled();
}

/* Which tools are installed in the runtime (absent = unknown, e.g. runtime offline). */
async function loadInstalled() {
  const { ok, data } = await api("GET", "/api/tools/manage");
  if (!ok || !data || !data.online) { state.present = {}; renderTiles(); return; }
  state.present = {};
  (data.tools || []).forEach((t) => { state.present[t.id] = t.present; });
  renderTiles();
  if (state.currentTool) renderToolForm(state.currentTool);
}

function categoryName(id) {
  const found = state.categories.find((c) => c.id === id);
  return found ? found.name : id;
}

function renderCategories() {
  const list = $("#cat-list");
  const select = $("#cat-filter");
  const previous = select.value;
  list.innerHTML = "";
  // Rebuild from scratch so repeated loads do not stack duplicate options.
  select.textContent = "";
  const all = document.createElement("option");
  all.value = "";
  all.textContent = "All categories";
  select.appendChild(all);
  state.categories.forEach((cat) => {
    const count = state.tools.filter((t) => t.category === cat.id).length;
    if (!count) return;
    const li = document.createElement("li");
    li.textContent = cat.name + "  (" + count + ")";
    li.addEventListener("click", () => {
      select.value = cat.id;
      renderTiles();
    });
    list.appendChild(li);

    const option = document.createElement("option");
    option.value = cat.id;
    option.textContent = cat.name;
    select.appendChild(option);
  });
  if (Array.from(select.options).some((o) => o.value === previous)) select.value = previous;
}

function renderTiles() {
  const query = ($("#search").value || "").toLowerCase();
  const cat = $("#cat-filter").value || "";
  const grid = $("#tiles");
  grid.innerHTML = "";

  const matches = state.tools.filter((tool) => {
    if (cat && tool.category !== cat) return false;
    if (!query) return true;
    const hay = (tool.name + " " + tool.id + " " + (tool.summary || "")).toLowerCase();
    return hay.indexOf(query) >= 0;
  });

  if (!matches.length) {
    grid.innerHTML = '<p class="muted">No tools match that filter.</p>';
    return;
  }

  matches.forEach((tool) => {
    const card = document.createElement("div");
    card.className = "card tile";
    const automated = state.automated.indexOf(tool.id) >= 0;
    const known = Object.prototype.hasOwnProperty.call(state.present, tool.id);
    let kind = tool.builtin ? "built-in" : (tool.baseline ? "preinstalled" : "on demand");
    if (!tool.builtin && known) kind = state.present[tool.id] ? "installed" : "not installed";
    card.classList.toggle("not-installed", !tool.builtin && known && !state.present[tool.id]);
    card.tabIndex = 0;
    card.setAttribute("role", "button");
    card.innerHTML =
      '<span class="badge">' + kind + "</span>" +
      "<h3>" + esc(tool.name) + "</h3>" +
      '<div class="cat">' + esc(categoryName(tool.category)) + "</div>" +
      "<p>" + esc(tool.summary || "") + "</p>" +
      '<p class="muted mode">' +
      (automated ? "one-click form" : (state.terminal[tool.id] ? "opens a terminal" : "built in")) + "</p>";
    card.addEventListener("click", () => openTool(tool.id));
    card.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openTool(tool.id); }
    });
    grid.appendChild(card);
  });
}

/* --- tool panel ---------------------------------------------------------- */
function closeTool() {
  state.currentTool = null;
  $("#tool-panel").classList.add("hidden");
}

async function refreshEvidence() {
  const { data } = await api("GET", "/api/evidence");
  if (!data || data.error) return;
  state.evidence = data.files || [];
}

// "Add file" control next to an evidence picker: uploads a file from the user's
// computer into the evidence folder and selects it. The file name goes in a header,
// URL-encoded, so it never appears in a URL.
function evidenceUploader(select) {
  const wrap = document.createElement("div");
  wrap.className = "evidence-add";
  const button = document.createElement("button");
  button.type = "button";
  button.className = "ghost";
  button.textContent = "Add file from my computer…";
  const picker = document.createElement("input");
  picker.type = "file";
  picker.hidden = true;
  const note = document.createElement("span");
  note.className = "muted";
  button.addEventListener("click", () => picker.click());
  picker.addEventListener("change", async () => {
    const file = picker.files && picker.files[0];
    picker.value = "";
    if (!file) return;
    note.textContent = "Uploading " + file.name + "…";
    try {
      const resp = await fetch("/api/evidence/upload", {
        method: "POST", credentials: "include",
        headers: {
          "Content-Type": "application/octet-stream",
          "X-KWS-CSRF": csrf(),
          "X-KWS-Filename": encodeURIComponent(file.name),
        },
        body: file,
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok || !data.ok) throw new Error(data.error || "upload failed (" + resp.status + ")");
      state.evidence = data.files || [];
      select.innerHTML = "";
      state.evidence.forEach((name) => {
        const opt = document.createElement("option");
        opt.value = name;
        opt.textContent = name;
        select.appendChild(opt);
      });
      select.value = data.name;
      note.textContent = "Added " + data.name + ".";
      toast("Added " + data.name);
    } catch (err) {
      note.textContent = err.message || "Upload failed";
      toast(note.textContent, true);
    }
  });
  wrap.append(button, picker, note);
  return wrap;
}

async function openTool(id) {
  const tool = state.tools.find((t) => t.id === id);
  if (!tool) return;
  state.currentTool = tool;

  $("#tool-title").textContent = tool.name;
  $("#tool-summary").textContent = tool.summary || "";

  const prereqs = $("#tool-prereqs");
  prereqs.innerHTML = "";
  const items = tool.prerequisites || ["Nothing special."];
  items.forEach((p) => {
    const li = document.createElement("li");
    li.textContent = p;
    prereqs.appendChild(li);
  });
  // Every tool runs inside the Linux runtime, not on Windows. Say so once, here.
  const where = document.createElement("li");
  where.className = "muted";
  where.textContent = "Runs inside the Linux runtime: 127.0.0.1 and localhost mean the runtime, " +
    "not Windows, so a service running on this PC is not reachable at those addresses. " +
    "Output files are saved in the run's work folder.";
  prereqs.appendChild(where);

  const usage = $("#tool-usage");
  usage.innerHTML = "";
  if (tool.usage) {
    const block = document.createElement("div");
    block.className = "needs";
    block.innerHTML = "<h3>How to use it</h3><p class=\"summary\">" + esc(tool.usage) + "</p>";
    usage.appendChild(block);
  }
  if (tool.examples && tool.examples.length) {
    const ex = document.createElement("div");
    ex.className = "examples";
    ex.innerHTML = "<h3>Examples (click to copy)</h3>";
    tool.examples.forEach((cmd) => {
      const code = document.createElement("code");
      code.textContent = cmd;
      code.title = "Click to copy";
      code.addEventListener("click", () => {
        navigator.clipboard && navigator.clipboard.writeText(cmd);
        toast("Copied: " + cmd);
      });
      ex.appendChild(code);
    });
    usage.appendChild(ex);
  }

  await refreshEvidence();
  renderToolForm(tool);

  $("#tool-output").classList.add("hidden");
  $("#tool-output").textContent = "";
  $("#tool-ai-out").textContent = "";
  $("#tool-panel").classList.remove("hidden");
}

function renderToolForm(tool) {
  const form = $("#tool-form");
  // Keep what the user typed when the same tool's form is rebuilt (e.g. after the tool list reloads).
  const sameTool = form.dataset.tool === tool.id;
  const kept = {};
  if (sameTool) {
    $$("#tool-form [data-key]").forEach((el) => {
      kept[el.dataset.key] = el.dataset.type === "checkbox" ? el.checked : el.value;
    });
  }
  const keptConfirm = sameTool && $("#f-confirm_external") ? $("#f-confirm_external").checked : false;
  form.innerHTML = "";
  form.dataset.tool = tool.id;
  const spec = FORM_SPECS[tool.id];
  const automated = state.automated.indexOf(tool.id) >= 0;

  const known = Object.prototype.hasOwnProperty.call(state.present, tool.id);
  const missingTool = !tool.builtin && known && !state.present[tool.id] && (tool.packages || []).length;
  if (missingTool) {
    const bar = document.createElement("div");
    bar.className = "needs";
    bar.innerHTML = '<p class="summary">This tool is not installed in the runtime yet.</p>';
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "primary";
    btn.textContent = "Install " + tool.name;
    btn.addEventListener("click", async () => { btn.disabled = true; await installTool(tool.id); loadInstalled(); });
    bar.appendChild(btn);
    form.appendChild(bar);
  }

  if (tool.id === "report") {
    const note = document.createElement("p");
    note.className = "muted";
    note.textContent = "The report builder turns your saved findings into an HTML, JSON or CSV report.";
    const go = document.createElement("button");
    go.type = "button";
    go.className = "primary";
    go.textContent = "Open Findings and reports";
    go.addEventListener("click", () => { closeTool(); showPanel("findings-panel"); });
    form.appendChild(note);
    form.appendChild(go);
    $("#tool-run").disabled = true;
    $("#tool-preview").disabled = true;
    return;
  }

  if (state.terminal[tool.id]) {
    const note = document.createElement("p");
    note.className = "muted";
    note.textContent =
      "This tool is interactive, so it runs in a terminal window inside the runtime. " +
      "It will start with: " + state.terminal[tool.id].join(" ");
    const go = document.createElement("button");
    go.type = "button";
    go.className = "primary";
    go.textContent = "Open in runtime terminal";
    go.addEventListener("click", async () => {
      const { data } = await api("POST", "/api/tool/" + encodeURIComponent(tool.id) + "/terminal", {});
      toast(data.message || data.error || "done", !!data.error || data.ok === false);
    });
    form.appendChild(note);
    form.appendChild(go);
    $("#tool-run").disabled = true;
    $("#tool-preview").disabled = true;
    return;
  }

  if (!spec || !automated) {
    const note = document.createElement("p");
    note.className = "muted";
    note.textContent =
      "This tool has no one-click form. Install it here, then open a shell in the runtime " +
      "(Settings, or run: wsl -d KaliSubstitute).";
    form.appendChild(note);
    $("#tool-run").disabled = true;
    $("#tool-preview").disabled = true;
    return;
  }

  // Never re-enable Run while a job for this tool is still going.
  $("#tool-run").disabled = !!activeJob;
  $("#tool-preview").disabled = false;

  const required = state.required[tool.id] || [];
  spec.forEach((field) => {
    const isRequired = required.indexOf(field.k) >= 0;
    const label = document.createElement("label");
    label.textContent = isRequired ? field.label + " *" : field.label;
    label.setAttribute("for", "f-" + field.k);
    form.appendChild(label);

    let input;
    if (field.type === "textarea") {
      input = document.createElement("textarea");
    } else if (field.type === "select") {
      input = document.createElement("select");
      (field.options || []).forEach((pair) => {
        const opt = document.createElement("option");
        opt.value = pair[0];
        opt.textContent = pair[1];
        input.appendChild(opt);
      });
    } else if (field.type === "evidence") {
      input = document.createElement("select");
      if (!state.evidence.length) {
        const opt = document.createElement("option");
        opt.value = "";
        opt.textContent = "(no files in the evidence folder yet)";
        input.appendChild(opt);
      }
      state.evidence.forEach((name) => {
        const opt = document.createElement("option");
        opt.value = name;
        opt.textContent = name;
        input.appendChild(opt);
      });
    } else if (field.type === "checkbox") {
      input = document.createElement("input");
      input.type = "checkbox";
    } else {
      input = document.createElement("input");
      input.type = "text";
      if (field.placeholder) input.placeholder = field.placeholder;
      if (field.value) input.value = field.value;
    }
    input.id = "f-" + field.k;
    input.dataset.key = field.k;
    input.dataset.type = field.type || "text";
    if (isRequired) input.required = true;
    if (Object.prototype.hasOwnProperty.call(kept, field.k)) {
      if (input.type === "checkbox") input.checked = !!kept[field.k];
      else input.value = kept[field.k];
    }
    form.appendChild(input);
    if (field.type === "evidence") form.appendChild(evidenceUploader(input));
  });

  const confirmWrap = document.createElement("div");
  confirmWrap.className = "check";
  confirmWrap.innerHTML =
    '<input type="checkbox" id="f-confirm_external">' +
    "<span>I confirm I own or am authorised to test any non-private target above.</span>";
  form.appendChild(confirmWrap);
  $("#f-confirm_external").checked = keptConfirm;
}

function collectPayload() {
  const payload = {};
  $$("#tool-form [data-key]").forEach((el) => {
    const key = el.dataset.key;
    if (el.dataset.type === "checkbox") payload[key] = el.checked;
    else payload[key] = el.value;
  });
  const confirm = $("#f-confirm_external");
  if (confirm) payload.confirm_external = confirm.checked;
  return payload;
}

function showOutput(result) {
  const out = $("#tool-output");
  out.classList.remove("hidden");
  if (result.error) {
    out.textContent = "Error: " + result.error + (result.detail ? "\n\n" + result.detail : "");
    return;
  }
  const argv = result.argv ? result.argv.join(" ") : "\u2026";
  const rc = result.rc != null ? result.rc
    : (result.returncode != null ? result.returncode : "?");
  let text = "$ " + argv + "\n(exit " + rc + ")\n\n" + (result.stdout || "");
  if (result.stderr) text += "\n[stderr]\n" + result.stderr;
  if (result.truncated) text += "\n\n[output truncated]";
  out.textContent = text;
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/* Poll a runtime job until it finishes, streaming new output to onOutput(text).
   Returns the final snapshot. Gives up after several failed polls in a row. */
async function pollJob(jobId, { onOutput, onTick, isCancelled } = {}) {
  let since = 0;
  let failures = 0;
  for (;;) {
    const { ok, data } = await api("GET", "/api/jobs/" + jobId + "?since=" + since, undefined,
      { timeout: 15000 });
    if (!ok) {
      if (++failures >= 5) return { state: "failed", done: true, rc: null, error: data.error || "lost contact with the runtime" };
      await sleep(1000);
      continue;
    }
    failures = 0;
    if (data.output && onOutput) onOutput(data.output);
    since = data.next != null ? data.next : since;
    if (onTick) onTick(data);
    if (data.done) return data;
    await sleep(700);
  }
}

let activeJob = null;

function setRunning(running) {
  $("#tool-run").disabled = running;
  $("#tool-cancel").classList.toggle("hidden", !running);
  if (!running) activeJob = null;
}

async function cancelRun() {
  if (!activeJob) return;
  $("#tool-cancel").disabled = true;
  await api("POST", "/api/jobs/" + activeJob + "/cancel", {});
}

const JOB_LABEL = { done: "Finished", failed: "Failed", cancelled: "Stopped", timeout: "Timed out" };

async function runTool(id, payload) {
  const out = $("#tool-output");
  const status = $("#tool-status");
  out.classList.remove("hidden");
  out.textContent = "Starting…";
  const started = await api("POST", "/api/tool/" + encodeURIComponent(id) + "/start", payload || {});
  if (!started.ok || started.data.error) {
    showOutput(started.data);
    toast(started.data.error || "could not start", true);
    return started.data;
  }
  activeJob = started.data.job;
  $("#tool-cancel").disabled = false;
  setRunning(true);
  activeJob = started.data.job;
  let text = "$ " + (started.data.argv || []).join(" ") + "\n\n";
  out.textContent = text;
  const final = await pollJob(started.data.job, {
    onOutput: (chunk) => {
      const stick = out.scrollTop + out.clientHeight >= out.scrollHeight - 20;
      text += chunk;
      out.textContent = text;
      if (stick) out.scrollTop = out.scrollHeight;
    },
    onTick: (snap) => { status.textContent = "Running… " + Math.round(snap.elapsed) + " s"; },
  });
  setRunning(false);
  const label = JOB_LABEL[final.state] || "Finished";
  (final.achievements || []).forEach((name) => toast("Achievement unlocked: " + name));
  status.textContent = label + " in " + Math.round(final.elapsed || 0) + " s" +
    (final.rc != null ? " (exit " + final.rc + ")" : "");
  if (final.truncated) out.textContent += "\n\n[output truncated]";
  if (final.error) out.textContent += "\n\n" + final.error;
  toast(label, final.state !== "done");
  return final;
}

function missingRequired(toolId) {
  const required = state.required[toolId] || [];
  for (const key of required) {
    const el = document.getElementById("f-" + key);
    if (!el) continue;
    const value = el.type === "checkbox" ? el.checked : (el.value || "").trim();
    if (!value) {
      const label = document.querySelector('label[for="f-' + key + '"]');
      const text = label ? label.textContent.replace(/\s*\*$/, "") : key;
      return { key, label: text, el };
    }
  }
  return null;
}

function requireInputs(toolId) {
  const miss = missingRequired(toolId);
  if (miss) {
    toast("Please fill in: " + miss.label, true);
    if (miss.el && miss.el.focus) miss.el.focus();
    return false;
  }
  return true;
}

async function previewCommand() {
  if (!state.currentTool) return;
  if (!requireInputs(state.currentTool.id)) return;
  const payload = collectPayload();
  const { data } = await api("POST", "/api/tool/" + state.currentTool.id + "/preview", payload);
  const out = $("#tool-output");
  out.classList.remove("hidden");
  if (data.error) {
    out.textContent = "Error: " + data.error + (data.detail ? "\n" + data.detail : "");
    return;
  }
  out.textContent = "Command that will run (argv, no shell):\n\n" + (data.argv || []).join(" ");
}

async function explainOutput() {
  if (!state.currentTool) return;
  const extra = $("#ai-explain-input").value;
  const output = $("#tool-output").textContent + (extra ? "\n\nQuestion: " + extra : "");
  const box = $("#tool-ai-out");
  box.textContent = "Asking the AI\u2026";
  // The model can be slow on a long transcript, so allow longer than the default 10 s.
  const { data } = await api("POST", "/api/ai/explain", {
    tool: state.currentTool.name,
    output: output,
  }, { timeout: 130000 });
  box.textContent = data.text || data.error || "No response.";
}

/* --- tool manager -------------------------------------------------------- */
async function loadManager() {
  const { data } = await api("GET", "/api/tools/manage");
  if (!data || data.error) {
    state.manager = [];
    state.managerOnline = false;
    $("#manager-list").innerHTML =
      '<p class="muted">Could not load the tool manager: ' +
      esc((data && data.error) || "request failed") + "</p>";
    return;
  }
  state.manager = data.tools || [];
  state.managerOnline = !!data.online;
  renderManager();
}

function renderManager() {
  const list = $("#manager-list");
  const query = ($("#manager-search").value || "").toLowerCase();
  const installedOnly = $("#manager-installed").checked;
  list.innerHTML = "";

  if (!state.managerOnline) {
    list.innerHTML = '<p class="muted">The runtime is offline. Set it up first, then manage tools.</p>';
    return;
  }

  const rows = state.manager.filter((t) => {
    if (installedOnly && !t.present) return false;
    if (!query) return true;
    return (t.name + " " + t.id).toLowerCase().indexOf(query) >= 0;
  });

  rows.forEach((tool) => {
    const row = document.createElement("div");
    row.className = "manager-row";
    const badge = tool.present
      ? '<span class="badge on">installed</span>'
      : '<span class="badge off">not installed</span>';
    const prereq = (tool.prerequisites || []).map((p) => "\u2022 " + esc(p)).join("<br>");
    row.innerHTML =
      '<div class="manager-info">' +
      "<h3>" + esc(tool.name) + " " + badge + "</h3>" +
      '<p>' + esc(tool.summary) + "</p>" +
      (prereq ? '<p class="muted">' + prereq + "</p>" : "") +
      '<p class="muted">Packages: ' + esc((tool.packages || []).join(", ")) + "</p>" +
      "</div>" +
      '<div class="manager-actions"></div>';
    const actions = row.querySelector(".manager-actions");
    if (tool.present) {
      const remove = document.createElement("button");
      remove.className = "ghost";
      remove.textContent = "Uninstall";
      remove.addEventListener("click", () => removeTool(tool.id));
      actions.appendChild(remove);
    } else {
      const install = document.createElement("button");
      install.className = "primary";
      install.textContent = tool.baseline ? "Reinstall" : "Install";
      install.addEventListener("click", () => installTool(tool.id));
      actions.appendChild(install);
    }
    list.appendChild(row);
  });

  if (!rows.length) list.innerHTML = '<p class="muted">Nothing to show.</p>';
}

async function manageTool(id, action) {
  const started = await api("POST", "/api/tools/" + encodeURIComponent(id) + "/" + action + "-job", {});
  if (!started.ok || started.data.error) {
    toast(started.data.error || action + " failed", true);
    return;
  }
  const verb = action === "install" ? "Installing" : "Removing";
  toast(verb + " " + id + "… this can take a few minutes");
  let tail = "";
  const final = await pollJob(started.data.job, {
    onOutput: (chunk) => { tail = (tail + chunk).slice(-400); },
    onTick: (snap) => {
      const el = document.getElementById("manager-status");
      if (el) el.textContent = verb + " " + id + "… " + Math.round(snap.elapsed) + " s";
    },
  });
  const el = document.getElementById("manager-status");
  if (el) el.textContent = "";
  if (final.state === "done") toast(id + (action === "install" ? " installed" : " removed"));
  else toast(id + ": " + (JOB_LABEL[final.state] || "failed") + (tail ? " - " + tail.trim().split("\n").pop() : ""), true);
  loadManager();
  loadCatalog();
}

const installTool = (id) => manageTool(id, "install");
const removeTool = (id) => manageTool(id, "remove");

/* --- findings, audit, report -------------------------------------------- */
async function loadFindings() {
  const { data } = await api("GET", "/api/findings");
  const body = $("#findings-body");
  if (!data || data.error) {
    body.innerHTML = '<tr><td colspan="5" class="muted">Could not load findings.</td></tr>';
    return;
  }
  body.innerHTML = "";
  (data.findings || []).forEach((f) => {
    const tr = document.createElement("tr");
    tr.innerHTML =
      '<td class="sev-' + esc(f.severity) + '">' + esc(f.severity) + "</td>" +
      "<td>" + esc(f.tool) + "</td>" +
      "<td>" + esc(f.target) + "</td>" +
      "<td>" + esc(f.title) + "</td>" +
      "<td>" + esc(f.created) + "</td>";
    body.appendChild(tr);
  });
  if (!(data.findings || []).length) {
    body.innerHTML = '<tr><td colspan="5" class="muted">No findings yet.</td></tr>';
  }
}

function toggleFindingForm() {
  let form = $("#finding-form");
  if (form) { form.remove(); $("#finding-new").textContent = "Add finding"; return; }
  form = document.createElement("div");
  form.id = "finding-form";
  form.className = "panel finding-form";
  form.innerHTML =
    '<label for="nf-sev">Severity</label>' +
    '<select id="nf-sev"><option>critical</option><option>high</option>' +
    '<option selected>medium</option><option>low</option><option>info</option></select>' +
    '<label for="nf-tool">Tool</label><input id="nf-tool" placeholder="nmap">' +
    '<label for="nf-target">Target</label><input id="nf-target" placeholder="192.168.1.10">' +
    '<label for="nf-title">Title</label><input id="nf-title" placeholder="Open SSH on the router">' +
    '<label for="nf-detail">Detail</label><textarea id="nf-detail"></textarea>' +
    '<div class="actions"><button type="button" class="primary" id="nf-save">Save finding</button></div>';
  $("#finding-new").textContent = "Cancel";
  $("#findings-panel").appendChild(form);
  $("#nf-save").addEventListener("click", async () => {
    const payload = {
      severity: $("#nf-sev").value,
      tool: $("#nf-tool").value,
      target: $("#nf-target").value,
      title: $("#nf-title").value,
      detail: $("#nf-detail").value,
    };
    if (!payload.title) { toast("A title is required", true); return; }
    const { ok, data } = await api("POST", "/api/findings", payload);
    if (!ok || !data || data.error) {
      // Keep the form and its content so the user can fix it and try again.
      toast((data && data.error) || "Could not save the finding", true);
      return;
    }
    toast("Finding saved");
    form.remove();
    $("#finding-new").textContent = "Add finding";
    loadFindings();
  });
}

async function downloadReport(fmt) {
  try {
    const resp = await fetch("/api/report?format=" + encodeURIComponent(fmt), { credentials: "same-origin" });
    if (!resp.ok) {
      toast("Report download failed (" + resp.status + ")", true);
      return;
    }
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "kws-report." + fmt;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } catch (err) {
    toast("Report download failed: " + (err && err.message ? err.message : "network error"), true);
  }
}

async function loadAudit() {
  const { data } = await api("GET", "/api/audit");
  const body = $("#audit-body");
  if (!data || data.error) {
    body.innerHTML = '<tr><td colspan="4" class="muted">Could not load the audit log.</td></tr>';
    return;
  }
  body.innerHTML = "";
  (data.audit || []).forEach((a) => {
    const tr = document.createElement("tr");
    tr.innerHTML =
      "<td>" + esc(a.created) + "</td>" +
      "<td>" + esc(a.action) + "</td>" +
      "<td>" + esc(a.target) + "</td>" +
      "<td>" + esc(a.result) + "</td>";
    body.appendChild(tr);
  });
  if (!(data.audit || []).length) {
    body.innerHTML = '<tr><td colspan="4" class="muted">Nothing logged yet.</td></tr>';
  }
}

/* --- chat ---------------------------------------------------------------- */
function renderChat() {
  const log = $("#chat-log");
  log.innerHTML = "";
  if (!state.chat.length) {
    log.innerHTML = '<div class="msg system">No messages yet. The AI is optional; add a model in Settings.</div>';
    return;
  }
  state.chat.forEach((m) => {
    const div = document.createElement("div");
    div.className = "msg " + m.role;
    div.textContent = m.content;
    $("#chat-log").appendChild(div);
  });
  $("#chat-log").scrollTop = $("#chat-log").scrollHeight;
}

async function sendChat() {
  const input = $("#chat-input");
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  state.chat.push({ role: "user", content: text });
  renderChat();
  const { data } = await api("POST", "/api/ai/chat", { messages: state.chat }, { timeout: 130000 });
  if (!data || !data.type) {
    // Transport or setup failure: show the reason, but keep it out of the conversation history.
    toast((data && data.error) || "The AI did not reply", true);
    return;
  }
  if (data.type === "error") {
    appendChatMessage("error", data.text, true);
    return;
  }
  if (data.type === "action" && data.tool) {
    appendChatMessage("assistant", data.text || "Proposed action:", true);
    renderProposal(data.tool, data.payload || {});
    return;
  }
  appendChatMessage("assistant", data.text || "(no response)", true);
}

function appendChatMessage(kind, text, push) {
  if (push) state.chat.push({ role: kind, content: text });
  renderChat();
}

function renderProposal(toolId, payload) {
  // AI proposals never carry the external-target authorisation. The user must tick
  // "I confirm ..." in the tool panel for external targets, so drop any value the model sent.
  payload = Object.assign({}, payload);
  delete payload.confirm_external;
  const log = $("#chat-log");
  const box = document.createElement("div");
  box.className = "proposal";
  const pairs = Object.entries(payload).map(([k, v]) => k + ": " + v).join("\n");
  box.innerHTML =
    "<strong>Proposed tool run:</strong> " + esc(toolId) +
    "<pre>" + esc(pairs || "(no fields)") + "</pre>" +
    '<div class="actions">' +
    '<button class="primary" data-act="run">Confirm and run</button>' +
    '<button class="ghost" data-act="cancel">Cancel</button></div>';
  box.querySelector('[data-act="run"]').addEventListener("click", async () => {
    box.remove();
    state.chat.push({ role: "user", content: "Confirmed: run " + toolId });
    renderChat();
    // Runs can take minutes, so no client-side timeout (the server enforces its own limits).
    const { data } = await api("POST", "/api/tool/" + encodeURIComponent(toolId),
      payload, { timeout: 0 });
    let resultText;
    if (!data || data.error) {
      resultText = "ERROR: " + ((data && data.error) || "unknown error") +
        ((data && data.detail) ? "\n" + data.detail : "");
    } else {
      const argv = data.argv ? data.argv.join(" ") : "\u2026";
      const rc = data.rc != null ? data.rc
        : (data.returncode != null ? data.returncode : "?");
      resultText = "$ " + argv + "\n(exit " + rc + ")" +
        (data.stdout ? "\n\n" + data.stdout : "") +
        (data.stderr ? "\n[stderr]\n" + data.stderr : "") +
        (data.truncated ? "\n\n[output truncated]" : "");
    }
    if (resultText.length > 4000) resultText = resultText.slice(0, 4000) + "\n\n[truncated in chat]";
    state.chat.push({ role: "system", content: "[ran " + toolId + "]\n" + resultText });
    renderChat();
    if (!data || data.error) toast((data && data.error) || "run failed", true);
    else toast("Ran " + toolId);
  });
  box.querySelector('[data-act="cancel"]').addEventListener("click", () => {
    box.remove();
    state.chat.push({ role: "assistant", content: "(action cancelled)" });
    renderChat();
  });
  log.appendChild(box);
  log.scrollTop = log.scrollHeight;
}

/* --- settings ------------------------------------------------------------ */
const AI_DEFAULTS = {
  ollama: { url: "http://127.0.0.1:11434", model: "llama3.1", key: false },
  openai: { url: "https://api.openai.com/v1", model: "gpt-4o-mini", key: true },
  anthropic: { url: "https://api.anthropic.com", model: "claude-sonnet-4-5", key: true },
  gemini: { url: "https://generativelanguage.googleapis.com/v1beta", model: "gemini-2.0-flash", key: true },
};

function aiProviderChanged() {
  const provider = $("#ai-provider").value;
  const d = AI_DEFAULTS[provider];
  $("#ai-base").placeholder = d ? d.url : "";
  $("#ai-model").placeholder = d ? d.model : "";
  $("#ai-key-row").classList.toggle("hidden", !d || !d.key);
  $("#ai-test").disabled = !d;
  $("#ai-models").innerHTML = "";
}

async function loadAiConfig() {
  const { data } = await api("GET", "/api/ai/config");
  if (!data || data.error) {
    $("#ai-status").textContent = "Could not load AI settings.";
    return;
  }
  $("#ai-provider").value = data.provider || "none";
  $("#ai-base").value = data.base_url || "";
  $("#ai-model").value = data.model || "";
  aiProviderChanged();
  const d = AI_DEFAULTS[data.provider];
  $("#ai-status").textContent = d && d.key
    ? "API key stored for this provider: " + (data.key_set === "yes" ? "yes" : "no") + "."
    : (d ? "Local models need no key." : "");
}

async function testAi() {
  const status = $("#ai-status");
  status.textContent = "Testing\u2026";
  const { data } = await api("POST", "/api/ai/test", {
    provider: $("#ai-provider").value,
    base_url: $("#ai-base").value.trim(),
    model: $("#ai-model").value.trim(),
    api_key: $("#ai-key").value,
  }, { timeout: 30000 });
  status.textContent = (data.ok ? "OK: " : "Problem: ") + (data.message || data.error || "no answer");
  const list = $("#ai-models");
  list.innerHTML = "";
  (data.models || []).forEach((name) => {
    const opt = document.createElement("option");
    opt.value = name;
    list.appendChild(opt);
  });
}

async function saveAiConfig(event) {
  event.preventDefault();
  const provider = $("#ai-provider").value;
  const saved = await api("POST", "/api/ai/config", {
    provider, base_url: $("#ai-base").value.trim(), model: $("#ai-model").value.trim(),
  });
  if (!saved.ok) { toast((saved.data && saved.data.error) || "could not save AI settings", true); return; }
  const key = $("#ai-key").value;
  if (key && provider !== "none") {
    const keyResp = await api("POST", "/api/ai/key", { provider, api_key: key });
    if (!keyResp.ok) {
      // Keep the typed key so the user can retry; show the server's reason.
      toast((keyResp.data && keyResp.data.error) || "could not save the API key", true);
      loadAiConfig();
      return;
    }
    $("#ai-key").value = "";
  }
  toast("AI settings saved");
  loadAiConfig();
}

async function restoreBackup() {
  const file = $("#backup-file").files[0];
  const status = $("#backup-status");
  if (!file) { status.textContent = "Choose a backup file first."; return; }
  if (!confirm("Replace your current findings, history and settings with this backup?")) return;
  status.textContent = "Restoring\u2026";
  try {
    const resp = await fetch("/api/backup/import", {
      method: "POST", credentials: "include",
      headers: { "Content-Type": "application/zip", "X-KWS-CSRF": csrf() }, body: file,
    });
    const data = await resp.json().catch(() => ({}));
    status.textContent = (resp.ok && data.message) || data.error || "Restore failed (" + resp.status + ")";
    toast(status.textContent, !resp.ok);
  } catch (err) {
    status.textContent = "Restore failed";
    toast("Restore failed: " + (err && err.message ? err.message : "network error"), true);
  }
}

/* --- navigation ---------------------------------------------------------- */
function showPanel(view) {
  const panels = ["manager-panel", "findings-panel", "audit-panel", "chat-panel", "settings-panel", "containers-panel", "history-panel", "playground-panel", "cheat-sheets-panel", "achievements-panel", "notebook-panel", "recordings-panel", "backup-panel", "onboarding-panel"];
  $$("#view-list li").forEach((li) => li.classList.toggle("active", li.dataset.view === view));
  if (view === "home") {
    $("#view-home").classList.remove("hidden");
    panels.forEach((p) => $("#" + p).classList.add("hidden"));
  } else {
    $("#view-home").classList.add("hidden");
    panels.forEach((p) => $("#" + p).classList.toggle("hidden", p !== view));
    if (view === "manager-panel") loadManager();
    if (view === "findings-panel") loadFindings();
    if (view === "audit-panel") loadAudit();
    if (view === "chat-panel") renderChat();
    if (view === "settings-panel") { refreshRuntime(); loadAiConfig(); }
    if (view === "containers-panel") { initContainers(); }
    if (view === "history-panel") { initHistory(); }
    if (view === "playground-panel") { initPlayground(); }
    if (view === "cheat-sheets-panel") { initCheatSheets(); }
    if (view === "achievements-panel") { initAchievements(); }
    if (view === "notebook-panel") { initNotebook(); }
    if (view === "recordings-panel") { initRecordings(); }
    if (view === "onboarding-panel") { initOnboarding(); }
  }
  window.scrollTo({ top: 0, behavior: "smooth" });
}

/* --- wiring -------------------------------------------------------------- */
function wireMain() {
  $("#search").addEventListener("input", renderTiles);
  $("#cat-filter").addEventListener("change", renderTiles);

  $("#setup-ensure").addEventListener("click", ensureRuntime);

  $("#tool-close").addEventListener("click", closeTool);
  $("#tool-run").addEventListener("click", () => {
    if (!state.currentTool) return;
    if (!requireInputs(state.currentTool.id)) return;
    runTool(state.currentTool.id, collectPayload());
  });
  $("#tool-preview").addEventListener("click", previewCommand);
  $("#tool-cancel").addEventListener("click", cancelRun);
  $("#tool-cheat").addEventListener("click", () => {
    if (state.currentTool) openCheatSheet(state.currentTool.id);
  });
  $("#backup-export").addEventListener("click", () => {
    window.location.href = "/api/backup/export";
  });
  $("#backup-import").addEventListener("click", restoreBackup);
  $("#open-shell").addEventListener("click", async () => {
    const { data } = await api("POST", "/api/runtime/shell", {});
    toast(data.message || data.error || "done", !!data.error || data.ok === false);
  });
  $("#ai-explain").addEventListener("click", explainOutput);

  $("#manager-search").addEventListener("input", renderManager);
  $("#manager-installed").addEventListener("change", renderManager);

  $("#finding-new").addEventListener("click", toggleFindingForm);
  $("#report-html").addEventListener("click", () => downloadReport("html"));
  $("#report-json").addEventListener("click", () => downloadReport("json"));
  $("#report-csv").addEventListener("click", () => downloadReport("csv"));

  $("#chat-send").addEventListener("click", sendChat);
  $("#chat-input").addEventListener("keydown", (e) => { if (e.key === "Enter") sendChat(); });

  $("#ai-form").addEventListener("submit", saveAiConfig);
  $("#ai-provider").addEventListener("change", aiProviderChanged);
  $("#ai-test").addEventListener("click", testAi);

  $$("#view-list li").forEach((li) => {
    li.addEventListener("click", () => showPanel(li.dataset.view));
  });
  $$("[data-close]").forEach((btn) => {
    btn.addEventListener("click", () => showPanel("home"));
  });

  // Command palette buttons
  const paletteBtn = $("#cmd-palette-btn");
  const sidebarPalette = $("#cmd-palette-sidebar");
  const helpBtn = $("#help-btn");
  
  if (paletteBtn) paletteBtn.addEventListener("click", toggleCommandPalette);
  if (sidebarPalette) sidebarPalette.addEventListener("click", toggleCommandPalette);
  if (helpBtn) helpBtn.addEventListener("click", showKeyboardHelp);

  // Keyboard shortcuts
  document.addEventListener("keydown", (e) => {
    // Ctrl+K for command palette
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      toggleCommandPalette();
      return;
    }
    
    // F1 for help
    if (e.key === "F1") {
      e.preventDefault();
      showKeyboardHelp();
      return;
    }
    
    // Escape: close the topmost overlay (help, then palette), otherwise the open panel. One action per press.
    if (e.key === "Escape") {
      const help = document.getElementById("keyboard-help-overlay");
      if (help) {
        help.remove();
        return;
      }
      const palette = document.getElementById("command-palette-overlay");
      if (palette) {
        if (window.closeCommandPalette) window.closeCommandPalette();
        else { palette.remove(); commandPaletteOpen = false; }
        return;
      }
      // Close open panels
      const openPanel = $$(".panel").find(p => !p.classList.contains("hidden") && p.id !== "view-home");
      if (openPanel) {
        showPanel("home");
        return;
      }
    }

    // Number shortcuts (1-9) - only when not typing in a field and no select has focus
    const tag = e.target.tagName;
    const typing = tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || e.target.isContentEditable;
    if (!typing && !e.ctrlKey && !e.altKey && !e.metaKey) {
      const map = {
        "1": "manager-panel",
        "2": "findings-panel",
        "3": "audit-panel",
        "4": "chat-panel",
        "5": "history-panel",
        "6": "playground-panel",
        "7": "cheat-sheets-panel",
        "8": "achievements-panel",
        "9": "notebook-panel"
      };
      const panel = map[e.key];
      if (panel) {
        e.preventDefault();
        showPanel(panel);
      }
    }
    
    // Ctrl+H for home
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "h") {
      e.preventDefault();
      showPanel("home");
    }
    
    // Ctrl+M for manager
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "m") {
      e.preventDefault();
      showPanel("manager-panel");
    }
    
    // Ctrl+T to focus search
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "t") {
      e.preventDefault();
      const search = $("#search");
      if (search) search.focus();
    }
  });

}

/* --- Command Palette --------------------------------------------------- */
let commandPaletteOpen = false;

function buildCommandPaletteCommands() {
  const commands = [];
  
  // Navigation commands
  const navItems = [
    { label: "Go to All tools", action: () => showPanel("home"), shortcut: "Ctrl+H" },
    { label: "Go to Tool manager", action: () => showPanel("manager-panel"), shortcut: "Ctrl+M" },
    { label: "Go to Findings", action: () => showPanel("findings-panel") },
    { label: "Go to Audit log", action: () => showPanel("audit-panel") },
    { label: "Go to AI chat", action: () => showPanel("chat-panel") },
    { label: "Go to Containers", action: () => showPanel("containers-panel") },
    { label: "Go to History", action: () => showPanel("history-panel") },
    { label: "Go to Playground", action: () => showPanel("playground-panel") },
    { label: "Go to Cheat Sheets", action: () => showPanel("cheat-sheets-panel") },
    { label: "Go to Notebook", action: () => showPanel("notebook-panel") },
    { label: "Go to Recordings", action: () => showPanel("recordings-panel") },
    { label: "Go to Achievements", action: () => showPanel("achievements-panel") },
    { label: "Go to Backup", action: () => showPanel("backup-panel") },
    { label: "Go to Settings", action: () => showPanel("settings-panel") },
    { label: "Go to Onboarding", action: () => showPanel("onboarding-panel") },
  ];
  commands.push(...navItems);
  
  // Tool commands - add all tools
  state.tools.forEach(tool => {
    commands.push({
      label: `Run ${tool.name}`,
      action: () => { showPanel("home"); setTimeout(() => openTool(tool.id), 100); },
      shortcut: tool.id
    });
  });
  
  // Actions
  commands.push(
    { label: "Focus search bar", action: () => { const s = $("#search"); if (s) s.focus(); }, shortcut: "Ctrl+T" },
    { label: "Close panels", action: () => showPanel("home"), shortcut: "Escape" },
    { label: "Keyboard shortcuts", action: () => showKeyboardHelp(), shortcut: "F1" }
  );
  
  return commands;
}

function toggleCommandPalette() {
  if (commandPaletteOpen) {
    closeCommandPalette();
    return;
  }
  
  const previousActiveElement = document.activeElement;
  const commands = buildCommandPaletteCommands();
  
  const overlay = document.createElement("div");
  overlay.id = "command-palette-overlay";
  overlay.setAttribute("role", "dialog");
  overlay.setAttribute("aria-modal", "true");
  overlay.setAttribute("aria-label", "Command Palette");
  overlay.style.cssText = `
    position: fixed; top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0,0,0,0.4); backdrop-filter: blur(4px);
    z-index: 9999; display: flex; align-items: flex-start;
    justify-content: center; padding-top: 80px;
  `;
  
  const palette = document.createElement("div");
  palette.style.cssText = `
    width: 560px; max-width: 90vw; max-height: 70vh;
    background: var(--panel, #fff); border: 1px solid var(--line, #e9ecef);
    border-radius: 12px; box-shadow: 0 10px 40px rgba(0,0,0,0.2);
    overflow: hidden; display: flex; flex-direction: column;
  `;
  
  const input = document.createElement("input");
  input.placeholder = "Search commands or tools...";
  input.setAttribute("aria-label", "Filter commands");
  input.style.cssText = `
    width: 100%; padding: 1rem 1.25rem; border: none;
    border-bottom: 1px solid var(--line, #e9ecef);
    font-size: 1rem; outline: none; background: transparent;
    color: var(--text, #212529); font-family: var(--font-sans);
  `;
  
  const listContainer = document.createElement("div");
  listContainer.style.cssText = "max-height: 500px; overflow-y: auto;";
  
  const list = document.createElement("ul");
  list.setAttribute("role", "listbox");
  list.style.cssText = "list-style: none; margin: 0; padding: 0.5rem;";
  
  let selectedIndex = -1;
  
  function render(filter = "") {
    list.innerHTML = "";
    const filtered = commands.filter(cmd =>
      !filter || cmd.label.toLowerCase().includes(filter.toLowerCase()) ||
      (cmd.shortcut && cmd.shortcut.toLowerCase().includes(filter.toLowerCase()))
    );
    
    if (!filtered.length) {
      const li = document.createElement("li");
      li.style.cssText = "padding: 1rem; color: var(--muted, #6c757d); text-align: center;";
      li.textContent = "No matching commands";
      list.appendChild(li);
      return;
    }
    
    selectedIndex = 0;
    filtered.forEach((cmd, index) => {
      const li = document.createElement("li");
      li.setAttribute("role", "option");
      li.setAttribute("aria-selected", index === 0 ? "true" : "false");
      li.tabIndex = -1;
      li.style.cssText = `
        padding: 0.6rem 1rem; cursor: pointer; display: flex;
        justify-content: space-between; align-items: center;
        border-radius: 6px; font-size: 0.9rem;
        ${index === selectedIndex ? "background: var(--accent-light, #e0e7ff); color: var(--accent, #4f46e5);" : ""}
      `;
      li.innerHTML = `
        <span>${esc(cmd.label)}</span>
        ${cmd.shortcut ? `<span class="kbd-chip">${esc(cmd.shortcut)}</span>` : ""}
      `;
      li.addEventListener("click", () => { 
        // Defer action to allow UI update/close first if needed
        setTimeout(() => {
            cmd.action(); 
            closeCommandPalette();
        }, 0);
      });
      li.addEventListener("mouseenter", () => {
        if (selectedIndex !== index) {
          const prevLi = list.children[selectedIndex];
          if(prevLi) {
             prevLi.style.background = "";
             prevLi.setAttribute("aria-selected", "false");
          }
          selectedIndex = index;
          li.style.background = "var(--accent-light, #e0e7ff)";
          li.setAttribute("aria-selected", "true");
        }
      });
      list.appendChild(li);
    });
  }
  
  function closePalette() {
    overlay.remove();
    commandPaletteOpen = false;
    if (previousActiveElement && previousActiveElement.focus) {
      previousActiveElement.focus();
    }
  }
  
  window.closeCommandPalette = closePalette;
  
  input.addEventListener("input", (e) => render(e.target.value));
  
  // Focus Trap Logic
  input.addEventListener("keydown", (e) => {
    const items = Array.from(list.querySelectorAll("li"));

    if (e.key === "Escape") {
      // Stop here so the document-level handler does not also close the panel behind the palette.
      e.preventDefault();
      e.stopPropagation();
      closePalette();
      return;
    }
    if (items.length === 0) return;
    
    if (e.key === "ArrowDown") {
      e.preventDefault();
      const nextIndex = Math.min(selectedIndex + 1, items.length - 1);
      updateSelection(nextIndex, items);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      const prevIndex = Math.max(selectedIndex - 1, 0);
      updateSelection(prevIndex, items);
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (selectedIndex >= 0 && items[selectedIndex]) {
        items[selectedIndex].click();
      }
    } else if (e.key === "Tab") {
      // Prevent tabbing out of the modal
      e.preventDefault();
      // Optional: Cycle focus within modal if there were other inputs, 
      // but here we only have one input, so we just keep it focused.
    }
  });

  function updateSelection(newIndex, items) {
    if (selectedIndex >= 0 && items[selectedIndex]) {
      items[selectedIndex].style.background = "";
      items[selectedIndex].setAttribute("aria-selected", "false");
    }
    selectedIndex = newIndex;
    if (items[selectedIndex]) {
      items[selectedIndex].style.background = "var(--accent-light, #e0e7ff)";
      items[selectedIndex].setAttribute("aria-selected", "true");
      items[selectedIndex].scrollIntoView({ block: "nearest" });
    }
  }
  
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) closePalette();
  });
  
  listContainer.appendChild(list);
  palette.appendChild(input);
  palette.appendChild(listContainer);
  overlay.appendChild(palette);
  document.body.appendChild(overlay);
  commandPaletteOpen = true;
  input.focus();
  render();
}

/* --- Keyboard Help Modal ----------------------------------------------- */
function showKeyboardHelp() {
  const existing = document.getElementById("keyboard-help-overlay");
  if (existing) existing.remove();
  
  const shortcuts = [
    { keys: "Ctrl + K", desc: "Command palette" },
    { keys: "Ctrl + H", desc: "Go to home" },
    { keys: "Ctrl + M", desc: "Tool manager" },
    { keys: "Ctrl + T", desc: "Focus search bar" },
    { keys: "1", desc: "Tool manager" },
    { keys: "2", desc: "Findings" },
    { keys: "3", desc: "Audit log" },
    { keys: "4", desc: "AI chat" },
    { keys: "5", desc: "History" },
    { keys: "6", desc: "Playground" },
    { keys: "7", desc: "Cheat Sheets" },
    { keys: "8", desc: "Achievements" },
    { keys: "9", desc: "Notebook" },
    { keys: "Escape", desc: "Close panels" },
    { keys: "F1", desc: "This help" },
  ];
  
  const overlay = document.createElement("div");
  overlay.id = "keyboard-help-overlay";
  overlay.setAttribute("role", "dialog");
  overlay.setAttribute("aria-modal", "true");
  overlay.setAttribute("aria-label", "Keyboard shortcuts help");
  overlay.style.cssText = `
    position: fixed; top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0,0,0,0.4); backdrop-filter: blur(4px);
    z-index: 9999; display: flex; align-items: center; justify-content: center;
  `;
  
  const modal = document.createElement("div");
  modal.style.cssText = `
    width: 440px; max-width: 90vw; background: var(--panel, #fff);
    border: 1px solid var(--line, #e9ecef); border-radius: 12px;
    box-shadow: 0 10px 40px rgba(0,0,0,0.2); padding: 1.5rem;
  `;
  
  let html = `
    <div class="kbd-help-head">
      <h2>Keyboard Shortcuts</h2>
      <button id="keyboard-help-close" class="kbd-help-close"
              aria-label="Close keyboard shortcuts help">&times;</button>
    </div>
    <div class="kbd-help-list">
  `;

  shortcuts.forEach(s => {
    html += `
      <div class="kbd-help-row">
        <span class="kbd-help-desc">${esc(s.desc)}</span>
        <span class="kbd-chip kbd-chip-help">${esc(s.keys)}</span>
      </div>
    `;
  });

  html += "</div>";
  modal.innerHTML = html;
  overlay.appendChild(modal);
  document.body.appendChild(overlay);

  const closeBtn = overlay.querySelector("#keyboard-help-close");
  if (closeBtn) closeBtn.addEventListener("click", () => overlay.remove());

  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) overlay.remove();
  });
  
  // Escape is handled once in wireMain's document keydown listener.
}

async function init() {
  wireMain();
  // The catalog and runtime status are independent: load them together.
  await Promise.all([refreshRuntime(), loadCatalog()]);
  const first = await api("GET", "/api/onboarding/status");
  if (first.ok && first.data.needed) showPanel("onboarding-panel");
  renderChat();
  setInterval(refreshRuntime, 20000);
}

document.addEventListener("DOMContentLoaded", init);
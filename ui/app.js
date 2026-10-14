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
  currentTool: null,
  evidence: [],
  manager: [],
  chat: [],
};

/* --- helpers ------------------------------------------------------------- */
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

function csrf() {
  const m = document.cookie.match(/(?:^|;\s*)kws_csrf=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : "";
}

function esc(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function toast(message, isError) {
  const el = $("#toast");
  el.textContent = message;
  el.classList.toggle("error", !!isError);
  el.classList.remove("hidden");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.add("hidden"), 4500);
}

async function api(method, path, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  if (method !== "GET") opts.headers["X-KWS-CSRF"] = csrf();
  const resp = await fetch(path, opts);
  const text = await resp.text();
  let data;
  try { data = text ? JSON.parse(text) : {}; } catch (_) { data = { raw: text }; }
  if (!resp.ok && !data.error) data.error = "request failed (" + resp.status + ")";
  return { ok: resp.ok, status: resp.status, data };
}

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
    { k: "service", label: "Service", type: "select", options: [["ssh", "SSH"], ["ftp", "FTP"], ["http-get", "HTTP GET"], ["http-post", "HTTP POST"]] },
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
    { k: "service", label: "Service", type: "select", options: [["ssh", "SSH"], ["ftp", "FTP"], ["http", "HTTP"]] },
  ],
  crunch: [
    { k: "min", label: "Minimum length", type: "text", value: "6" },
    { k: "max", label: "Maximum length", type: "text", value: "8" },
    { k: "charset", label: "Characters to use", type: "text", value: "abc123" },
  ],
  cewl: [{ k: "url", label: "URL to crawl", type: "text", placeholder: "https://example.com" }],
  "aircrack-ng": [{ k: "file", label: "Capture file (.cap) from the evidence folder", type: "evidence" }],
  hcxtools: [{ k: "file", label: "Capture file (.cap/.pcapng)", type: "evidence" }],
  metasploit: [
    { k: "module", label: "Auxiliary module", type: "text", placeholder: "auxiliary/scanner/http/http_version" },
    { k: "target", label: "Target host(s)", type: "text", placeholder: "192.168.1.10" },
  ],
  tcpdump: [{ k: "filter", label: "Capture filter, e.g. 'port 53'", type: "text", placeholder: "port 53" }],
  tshark: [{ k: "file", label: "Capture file from the evidence folder", type: "evidence" }],
  netcat: [
    { k: "target", label: "Target host", type: "text", placeholder: "192.168.1.10" },
    { k: "port", label: "Port", type: "text", value: "22" },
  ],
  foremost: [{ k: "file", label: "Disk image or binary", type: "evidence" }],
  binwalk: [{ k: "file", label: "Firmware or binary", type: "evidence" }],
  exiftool: [{ k: "file", label: "Image or document", type: "evidence" }],
  steghide: [{ k: "file", label: "Suspect file", type: "evidence" }],
  volatility3: [{ k: "file", label: "Memory image", type: "evidence" }],
  sleuthkit: [{ k: "file", label: "Disk image", type: "evidence" }],
  radare2: [{ k: "file", label: "Binary", type: "evidence" }],
  gdb: [{ k: "file", label: "Program", type: "evidence" }],
  strace: [{ k: "file", label: "Program", type: "evidence" }],
};

/* --- runtime ------------------------------------------------------------- */
async function refreshRuntime() {
  const { data } = await api("GET", "/api/runtime");
  const dot = $("#runtime-dot");
  const text = $("#runtime-text");
  const banner = $("#setup-banner");
  dot.className = "dot";
  if (data.agent) {
    dot.classList.add("ok");
    text.textContent = "runtime online";
    banner.classList.add("hidden");
    banner.classList.remove("bad");
  } else {
    if (!data.wsl) dot.classList.add("bad");
    text.textContent = data.wsl ? "runtime offline" : "WSL2 missing";
    banner.classList.remove("hidden");
    banner.classList.toggle("bad", !data.wsl);
    $("#setup-message").textContent = data.message || "Runtime is not ready.";
  }
  $("#set-wsl").textContent = data.wsl ? "yes" : "no";
  $("#set-installed").textContent = data.installed ? "yes" : "no";
  $("#set-agent").textContent = data.agent ? "online" : "offline";
  $("#set-message").textContent = data.message || "\u2014";
}

async function ensureRuntime() {
  const btn = $("#setup-ensure");
  btn.disabled = true;
  btn.textContent = "Setting up\u2026";
  const { data } = await api("POST", "/api/runtime/ensure", {});
  btn.disabled = false;
  btn.textContent = "Set up runtime";
  toast(data.message || "done", !data.ok);
  refreshRuntime();
}

/* --- catalog ------------------------------------------------------------- */
async function loadCatalog() {
  const { data } = await api("GET", "/api/catalog");
  state.catalog = data.app || {};
  state.tools = data.tools || [];
  state.categories = data.categories || [];
  state.automated = data.automated || [];
  renderCategories();
  renderTiles();
}

function categoryName(id) {
  const found = state.categories.find((c) => c.id === id);
  return found ? found.name : id;
}

function renderCategories() {
  const list = $("#cat-list");
  const select = $("#cat-filter");
  list.innerHTML = "";
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
    automated = state.automated.indexOf(tool.id) >= 0;
    const kind = tool.builtin ? "built-in" : (tool.baseline ? "preinstalled" : "on demand");
    card.innerHTML =
      '<span class="badge">' + kind + "</span>" +
      "<h3>" + esc(tool.name) + "</h3>" +
      '<div class="cat">' + esc(categoryName(tool.category)) + "</div>" +
      "<p>" + esc(tool.summary || "") + "</p>" +
      '<p class="muted mode">' +
      (automated ? "one-click form" : "expert / terminal") + "</p>";
    card.addEventListener("click", () => openTool(tool.id));
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
  state.evidence = data.files || [];
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
  form.innerHTML = "";
  const spec = FORM_SPECS[tool.id];
  const automated = state.automated.indexOf(tool.id) >= 0;

  if (!spec || !automated) {
    const note = document.createElement("p");
    note.className = "muted";
    note.textContent =
      "This tool has no one-click form yet. You can still install it here, " +
      "then run it from the runtime shell. Its prerequisites and usage are above.";
    form.appendChild(note);
    $("#tool-run").disabled = true;
    $("#tool-preview").disabled = true;
    return;
  }

  $("#tool-run").disabled = false;
  $("#tool-preview").disabled = false;

  spec.forEach((field) => {
    const label = document.createElement("label");
    label.textContent = field.label;
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
    form.appendChild(input);
  });

  const confirmWrap = document.createElement("div");
  confirmWrap.className = "check";
  confirmWrap.innerHTML =
    '<input type="checkbox" id="f-confirm_external">' +
    "<span>I confirm I own or am authorised to test any non-private target above.</span>";
  form.appendChild(confirmWrap);
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

async function runTool(id, payload) {
  const out = $("#tool-output");
  out.classList.remove("hidden");
  out.textContent = "Running\u2026";
  const { data } = await api("POST", "/api/tool/" + encodeURIComponent(id), payload || {});
  showOutput(data);
  if (!data.error) toast("Run complete");
  else toast(data.error, true);
  return data;
}

async function previewCommand() {
  if (!state.currentTool) return;
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
  const { data } = await api("POST", "/api/ai/explain", {
    tool: state.currentTool.name,
    output: output,
  });
  box.textContent = data.text || data.error || "No response.";
}

/* --- tool manager -------------------------------------------------------- */
async function loadManager() {
  const { data } = await api("GET", "/api/tools/manage");
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

async function installTool(id) {
  toast("Installing " + id + "\u2026 this can take a while");
  const { data } = await api("POST", "/api/tools/" + id + "/install", {});
  toast(data.message || data.error || "done", !!data.error);
  loadManager();
}

async function removeTool(id) {
  const { data } = await api("POST", "/api/tools/" + id + "/remove", {});
  toast(data.message || data.error || "done", !!data.error);
  loadManager();
}

/* --- findings, audit, report -------------------------------------------- */
async function loadFindings() {
  const { data } = await api("GET", "/api/findings");
  const body = $("#findings-body");
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
    await api("POST", "/api/findings", payload);
    toast("Finding saved");
    form.remove();
    $("#finding-new").textContent = "Add finding";
    loadFindings();
  });
}

async function downloadReport(fmt) {
  const resp = await fetch("/api/report?format=" + fmt);
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "kws-report." + fmt;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

async function loadAudit() {
  const { data } = await api("GET", "/api/audit");
  const body = $("#audit-body");
  body.innerHTML = "";
  (data.audits || []).forEach((a) => {
    const tr = document.createElement("tr");
    tr.innerHTML =
      "<td>" + esc(a.created) + "</td>" +
      "<td>" + esc(a.action) + "</td>" +
      "<td>" + esc(a.target) + "</td>" +
      "<td>" + esc(a.result) + "</td>";
    body.appendChild(tr);
  });
  if (!(data.audits || []).length) {
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
    div.textContent = msg.content;
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
  const { data } = await api("POST", "/api/ai/chat", { messages: state.chat });
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
    await runTool(toolId, Object.assign({}, payload, { confirm_external: !!payload.confirm_external }));
    toast("Ran " + toolId);
    renderChat();
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
async function loadAiConfig() {
  const { data } = await api("GET", "/api/ai/config");
  $("#ai-provider").value = data.provider || "none";
  $("#ai-base").value = data.base_url || "";
  $("#ai-model").value = data.model || "";
  $("#ai-status").textContent =
    "API key stored: " + (data.key_set === "yes" ? "yes" : "no") +
    ". Local models need no key.";
}

async function saveAiConfig(event) {
  event.preventDefault();
  const provider = $("#ai-provider").value;
  const base = $("#ai-base").value.trim();
  const model = $("#ai-model").value.trim();
  await api("POST", "/api/ai/config", { provider: provider, base_url: base, model: model });
  const key = $("#ai-key").value;
  if (key) {
    await api("POST", "/api/ai/key", { api_key: key });
    $("#ai-key").value = "";
  }
  toast("AI settings saved");
  loadAiConfig();
}

/* --- navigation ---------------------------------------------------------- */
function showPanel(view) {
  const panels = ["manager-panel", "findings-panel", "audit-panel", "chat-panel", "settings-panel"];
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
  }
  window.scrollTo({ top: 0, behavior: "smooth" });
}

/* --- wiring -------------------------------------------------------------- */
function wire() {
  $("#search").addEventListener("input", renderTiles);
  $("#cat-filter").addEventListener("change", renderTiles);

  $("#setup-ensure").addEventListener("click", ensureRuntime);

  $("#tool-close").addEventListener("click", closeTool);
  $("#tool-run").addEventListener("click", () => {
    if (state.currentTool) runTool(state.currentTool.id, collectPayload());
  });
  $("#tool-preview").addEventListener("click", previewCommand);
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

  $$("#view-list li").forEach((li) => {
    li.addEventListener("click", () => showPanel(li.dataset.view));
  });
  $$("[data-close]").forEach((btn) => {
    btn.addEventListener("click", () => showPanel("home"));
  });
}

async function init() {
  wire();
  await refreshRuntime();
  await loadCatalog();
  renderChat();
  setInterval(refreshRuntime, 20000);
}

document.addEventListener("DOMContentLoaded", init);

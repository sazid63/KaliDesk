/* 
 * Kali Linux Windows Substitute - Run History Panel
 */

let history = [];

async function initHistory() {
  await loadHistory();
  wireHistory();
  setInterval(() => {
    if (!$("#history-panel").classList.contains("hidden")) {
      loadHistory();
    }
  }, 10000);
}

async function loadHistory() {
  const { data } = await api("GET", "/api/history");
  if (!data) return;
  history = data;
  renderHistory();
}

function renderHistory() {
  const tbody = $("#history-table-body");
  tbody.innerHTML = "";
  
  if (!history.length) {
    tbody.innerHTML = '<tr><td colspan="6" class="muted">No runs recorded.</td></tr>';
    return;
  }
  
  history.slice().reverse().forEach((run) => {
    const tr = document.createElement("tr");
    tr.innerHTML =
      '<td>' + esc(run.tool) + '</td>' +
      '<td>' + esc(run.target || "—") + '</td>' +
      '<td>' + esc(String(run.rc || "—")) + '</td>' +
      '<td>' + esc(formatDuration(run.duration_ms)) + '</td>' +
      '<td>' + (run.success ? "Yes" : "No") + '</td>' +
      '<td>' +
      '<button class="ghost tiny" data-id="' + run.id + '" data-act="delete">Del</button>' +
      '</td>';
    tbody.appendChild(tr);
  });
  
  tbody.querySelectorAll('[data-act="delete"]').forEach((btn) => {
    btn.addEventListener("click", () => deleteHistory(btn.dataset.id));
  });
}

function formatDuration(ms) {
  if (!ms) return "—";
  if (ms < 1000) return ms + "ms";
  const s = (ms / 1000).toFixed(1);
  return s + "s";
}

function esc(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function deleteHistory(id) {
  if (!confirm("Delete this run record?")) return;
  api("DELETE", "/api/history/" + id).then(() => {
    loadHistory();
    toast("Run deleted");
  });
}

async function wireHistory() {
  $("#history-filter-tool").addEventListener("input", renderHistory);
  $("#history-filter-success").addEventListener("change", renderHistory);
  $("#history-clear").addEventListener("click", async () => {
    if (confirm("Clear all run history?")) {
      await api("POST", "/api/history/clear");
      loadHistory();
      toast("History cleared");
    }
  });
}

async function api(method, path, body, options = {}) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  if (method !== "GET") {
    const m = document.cookie.match(/(?:^|;\s*)kws_csrf=([^;]+)/);
    if (m) opts.headers["X-KWS-CSRF"] = decodeURIComponent(m[1]);
  }
  if (options.signal) opts.signal = options.signal;
  
  const resp = await fetch(path, opts);
  const text = await resp.text();
  let data;
  try { data = text ? JSON.parse(text) : {}; } catch (_) { data = { raw: text }; }
  if (!resp.ok && !data.error) data.error = "request failed (" + resp.status + ")";
  return { ok: resp.ok, status: resp.status, data };
}

function wire() {
}

wire();
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
  if (!data || !data.history) return;
  history = data.history;
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

/* esc, toast, api provided globally by utils.js */

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

/* $, $$, esc, toast, api provided globally by utils.js */

function wire() {
}

wire();
(function () {
"use strict";
/* Run history: newest first, filterable, refreshed while the panel is open. */

let rows = [];
let wired = false;
let timer = null;

function visible() {
  const tool = ($("#history-filter-tool").value || "").trim().toLowerCase();
  const ok = $("#history-filter-success").value;
  return rows.filter((run) =>
    (!tool || String(run.tool).toLowerCase().includes(tool)) &&
    (ok === "" || (ok === "true") === !!run.success));
}

function render() {
  const body = $("#history-table-body");
  body.textContent = "";
  const list = visible();
  if (!list.length) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 7;
    td.className = "muted";
    td.textContent = rows.length ? "No runs match that filter." : "No runs recorded yet.";
    tr.appendChild(td);
    body.appendChild(tr);
    return;
  }
  list.forEach((run) => {
    const tr = document.createElement("tr");
    [formatWhen(run.created), run.tool, run.target || "—",
     run.rc === null || run.rc === undefined ? "—" : String(run.rc),
     formatDuration(run.duration_ms), run.success ? "ok" : "failed"].forEach((text, i) => {
      const td = document.createElement("td");
      td.textContent = text;
      if (i === 5) td.className = run.success ? "ok" : "bad";
      tr.appendChild(td);
    });
    const actions = document.createElement("td");
    const del = document.createElement("button");
    del.type = "button";
    del.className = "ghost tiny";
    del.textContent = "Delete";
    del.addEventListener("click", () => removeRun(run.id));
    actions.appendChild(del);
    tr.appendChild(actions);
    tr.title = run.output_preview || "";
    body.appendChild(tr);
  });
}

async function load() {
  const { data } = await api("GET", "/api/history?limit=500");
  rows = (data && data.history) || [];
  render();
}

async function removeRun(id) {
  if (!confirm("Delete this run record?")) return;
  const { ok, data } = await api("DELETE", "/api/history/" + encodeURIComponent(id));
  if (!ok) { toast((data && data.error) || "Could not delete that run", true); return; }
  toast("Run deleted");
  load();
}

function wire() {
  if (wired) return;
  wired = true;
  $("#history-filter-tool").addEventListener("input", render);
  $("#history-filter-success").addEventListener("change", render);
  $("#history-clear").addEventListener("click", async () => {
    if (!confirm("Clear the whole run history?")) return;
    const { ok, data } = await api("POST", "/api/history/clear", {});
    if (!ok) { toast((data && data.error) || "Could not clear history", true); return; }
    toast("History cleared");
    load();
  });
  timer = setInterval(() => {
    if (!$("#history-panel").classList.contains("hidden")) load();
  }, 10000);
}

async function initHistory() {
  wire();
  await load();
}

window.initHistory = initHistory;
})();

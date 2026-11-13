(function () {
"use strict";
/* Run transcripts: every finished tool run saved with its full output. */

let recordings = [];

async function initRecordings() {
  await loadRecordings();
}

async function loadRecordings() {
  const { data } = await api("GET", "/api/recordings");
  recordings = (data && data.recordings) || [];
  renderRecordings();
}

const RESULT = { done: "finished", failed: "failed", cancelled: "stopped", timeout: "timed out" };

function renderRecordings() {
  const tbody = $("#recordings-table-body");
  tbody.innerHTML = "";
  if (!recordings.length) {
    tbody.innerHTML = '<tr><td colspan="6" class="muted">Nothing yet. Run a tool and its output is saved here.</td></tr>';
    return;
  }
  recordings.forEach((rec) => {
    const tr = document.createElement("tr");
    const cells = [
      rec.tool,
      (RESULT[rec.state] || rec.state) + (rec.rc != null ? " (exit " + rec.rc + ")" : ""),
      formatDuration(rec.duration_ms),
      (rec.size_bytes / 1024).toFixed(1) + " KB",
      formatWhen(rec.started),
    ];
    cells.forEach((text) => {
      const td = document.createElement("td");
      td.textContent = text;
      tr.appendChild(td);
    });
    const actions = document.createElement("td");
    [["View", () => viewRecording(rec.id)],
     ["Save", () => { window.location.href = "/api/recordings/" + encodeURIComponent(rec.id) + "?download=1"; }],
     ["Delete", () => deleteRecording(rec.id)]].forEach(([label, handler]) => {
      const btn = document.createElement("button");
      btn.className = "ghost tiny";
      btn.type = "button";
      btn.textContent = label;
      btn.addEventListener("click", handler);
      actions.appendChild(btn);
    });
    tr.appendChild(actions);
    tbody.appendChild(tr);
  });
}

async function viewRecording(id) {
  const { ok, data } = await api("GET", "/api/recordings/" + encodeURIComponent(id));
  if (!ok || !data.meta) {
    toast("Could not load that transcript", true);
    return;
  }
  const modal = document.createElement("div");
  modal.className = "modal recording-modal";
  const box = document.createElement("div");
  box.className = "modal-content";
  const title = document.createElement("h3");
  title.textContent = data.meta.tool + (data.meta.target ? " → " + data.meta.target : "");
  const cmd = document.createElement("p");
  cmd.className = "muted";
  cmd.textContent = "$ " + (data.meta.argv || []).join(" ");
  const pre = document.createElement("pre");
  pre.className = "recording-lines";
  pre.textContent = data.text;
  const close = document.createElement("button");
  close.className = "primary";
  close.type = "button";
  close.textContent = "Close";
  close.addEventListener("click", () => modal.remove());
  box.append(title, cmd, pre, close);
  modal.appendChild(box);
  document.body.appendChild(modal);
  close.focus();
}

async function deleteRecording(id) {
  if (!confirm("Delete this transcript?")) return;
  const { ok, data } = await api("DELETE", "/api/recordings/" + encodeURIComponent(id));
  if (!ok) { toast((data && data.error) || "Could not delete that transcript", true); return; }
  toast("Transcript deleted");
  loadRecordings();
}

window.initRecordings = initRecordings;
})();

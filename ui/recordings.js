/*
 * Kali Linux Windows Substitute - Terminal Recordings Panel
 */

let recordings = [];
let activeRecording = null;

async function initRecordings() {
  await loadRecordings();
  wireRecordings();
}

async function loadRecordings() {
  const { data } = await api("GET", "/api/recordings");
  if (!data) return;
  recordings = data;
  renderRecordings();
}

function renderRecordings() {
  const tbody = $("#recordings-table-body");
  tbody.innerHTML = "";
  
  if (!recordings.length) {
    tbody.innerHTML = '<tr><td colspan="5" class="muted">No recordings found.</td></tr>';
    return;
  }
  
  recordings.forEach((rec) => {
    const tr = document.createElement("tr");
    tr.innerHTML =
      '<td>' + esc(rec.tool) + '</td>' +
      '<td>' + esc(formatDuration(rec.duration_ms)) + '</td>' +
      '<td>' + esc(rec.size_kb + "KB") + '</td>' +
      '<td>' + esc(rec.created) + '</td>' +
      '<td>' +
      '<button class="ghost tiny" data-id="' + rec.id + '" data-act="load">Load</button>' +
      '<button class="ghost tiny" data-id="' + rec.id + '" data-act="delete">Delete</button>' +
      '</td>';
    tbody.appendChild(tr);
  });
  
  tbody.querySelectorAll('[data-act="load"]').forEach((btn) => {
    btn.addEventListener("click", () => loadRecording(btn.dataset.id));
  });
  tbody.querySelectorAll('[data-act="delete"]').forEach((btn) => {
    btn.addEventListener("click", () => deleteRecording(btn.dataset.id));
  });
}

async function startRecording() {
  const tool = prompt("Enter tool name (e.g., nmap, sqlmap):");
  if (!tool) return;
  
  const { data } = await api("POST", "/api/recordings/start", { tool });
  if (data.id) {
    activeRecording = data.id;
    toast("Recording started");
  } else {
    toast(data.error || "Failed to start recording", true);
  }
}

async function stopRecording() {
  if (!activeRecording) {
    toast("No active recording", true);
    return;
  }
  
  const { data } = await api("POST", "/api/recordings/stop", { id: activeRecording });
  activeRecording = null;
  toast(data.message || "Recording stopped");
  loadRecordings();
}

async function loadRecording(id) {
  const { data } = await api("GET", "/api/recordings/" + id);
  if (!data || !data.lines) {
    toast("Failed to load recording", true);
    return;
  }
  
  // Show in a modal-like overlay
  const modal = document.createElement("div");
  modal.className = "modal recording-modal";
  modal.innerHTML =
    '<div class="modal-content">' +
    '<h3>Recording</h3>' +
    '<pre class="recording-lines">' + esc(data.lines.join("\n")) + '</pre>' +
    '<div class="actions">' +
    '<button class="primary" id="recording-modal-close">Close</button>' +
    '</div>' +
    '</div>';
  document.body.appendChild(modal);
  
  modal.querySelector("#recording-modal-close").addEventListener("click", () => {
    modal.remove();
  });
}

async function deleteRecording(id) {
  if (!confirm("Delete this recording?")) return;
  await api("DELETE", "/api/recordings/" + id);
  loadRecordings();
  toast("Recording deleted");
}

function formatDuration(ms) {
  if (!ms) return "—";
  if (ms < 1000) return ms + "ms";
  const s = (ms / 1000).toFixed(1);
  return s + "s";
}

/* $, $$, esc, toast, api provided globally by utils.js */

function wire() {
  const startBtn = $("#recordings-start");
  if (startBtn) startBtn.addEventListener("click", startRecording);
  const stopBtn = $("#recordings-stop");
  if (stopBtn) stopBtn.addEventListener("click", stopRecording);
}

wire();
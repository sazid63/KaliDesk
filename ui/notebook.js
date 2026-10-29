/*
 * Kali Linux Windows Substitute - OSINT Notebook Panel
 */

let notebookEntries = [];

async function initNotebook() {
  await loadEntries();
  wireNotebook();
}

async function loadEntries() {
  const { data } = await api("GET", "/api/notebook/entries");
  if (!data) return;
  notebookEntries = data;
  renderEntries();
}

function renderEntries() {
  const list = $("#entries-list");
  list.innerHTML = "";
  
  if (!notebookEntries.length) {
    list.innerHTML = '<p class="muted">No entries yet. Click "Add Entry" to get started.</p>';
    return;
  }
  
  notebookEntries.forEach((entry) => {
    const div = document.createElement("div");
    div.className = "card entry";
    div.innerHTML =
      '<div class="entry-header">' +
      '<span class="badge entry-type">' + esc(entry.type) + '</span>' +
      '<span class="muted entry-date">' + esc(entry.created || "") + '</span>' +
      '<button class="ghost tiny" data-id="' + entry.id + '" data-act="delete">Delete</button>' +
      '</div>' +
      '<div class="entry-content">' + esc(entry.content) + '</div>' +
      (entry.tags ? '<div class="entry-tags">' + entry.tags.split(",").map(t => '<span class="chip">' + esc(t.trim()) + "</span>").join("") + "</div>" : "");
    list.appendChild(div);
  });
  
  list.querySelectorAll('[data-act="delete"]').forEach((btn) => {
    btn.addEventListener("click", () => deleteEntry(btn.dataset.id));
  });
}

async function addEntry() {
  const type = $("#notebook-type").value;
  const content = $("#notebook-content").value.trim();
  const tags = $("#notebook-tags").value.trim();
  
  if (!content) {
    toast("Content is required", true);
    return;
  }
  
  const { data } = await api("POST", "/api/notebook/entries", { type, content, tags });
  toast(data.message || "Entry added");
  $("#entry-form").style.display = "none";
  $("#notebook-content").value = "";
  $("#notebook-tags").value = "";
  loadEntries();
}

async function deleteEntry(id) {
  if (!confirm("Delete this entry?")) return;
  await api("DELETE", "/api/notebook/entries/" + id);
  loadEntries();
  toast("Entry deleted");
}

async function exportNotebook() {
  const { data } = await api("GET", "/api/notebook/export");
  if (!data || !data.markdown) {
    toast("Export failed", true);
    return;
  }
  const blob = new Blob([data.markdown], { type: "text/markdown" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "kws-notebook.md";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
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
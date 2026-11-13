(function () {
"use strict";
/*
 * Kali Linux Windows Substitute - OSINT Notebook Panel
 */

let notebookEntries = [];

async function initNotebook() {
  await loadEntries();
}

async function loadEntries() {
  const { data } = await api("GET", "/api/notebook/entries");
  if (!data || !Array.isArray(data.entries)) return;
  notebookEntries = data.entries;
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
      (entry.tags ? '<div class="entry-tags">' + (Array.isArray(entry.tags) ? entry.tags : entry.tags.split(",")).map(t => '<span class="chip">' + esc(String(t).trim()) + "</span>").join("") + "</div>" : "");
    list.appendChild(div);
  });
  
  list.querySelectorAll('[data-act="delete"]').forEach((btn) => {
    btn.addEventListener("click", () => deleteEntry(btn.dataset.id));
  });
}

async function addEntry() {
  const type = $("#notebook-type").value;
  const content = $("#notebook-content").value.trim();
  const tagsRaw = $("#notebook-tags").value.trim();
  
  if (!content) {
    toast("Content is required", true);
    return;
  }
  
  const tags = tagsRaw ? tagsRaw.split(",").map(t => t.trim()).filter(Boolean) : [];
  const { ok, data } = await api("POST", "/api/notebook/entries", { type, content, tags });
  if (!ok) { toast((data && data.error) || "Could not save the entry", true); return; }
  toast(data.message || "Entry added");
  $("#entry-form").classList.add("hidden");
  $("#notebook-content").value = "";
  $("#notebook-tags").value = "";
  loadEntries();
}

async function deleteEntry(id) {
  if (!confirm("Delete this entry?")) return;
  const { ok, data } = await api("DELETE", "/api/notebook/entries/" + encodeURIComponent(id));
  if (!ok) { toast((data && data.error) || "Could not delete the entry", true); return; }
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

/* $, $$, esc, toast, api provided globally by utils.js */

let searchDebounce = null;

async function searchEntries(query) {
  if (!query.trim()) {
    await loadEntries();
    return;
  }
  const { data } = await api("GET", "/api/notebook/search?q=" + encodeURIComponent(query));
  if (data && data.entries) {
    notebookEntries = data.entries;
    renderEntries();
  }
}

function wireNotebook() {
  const addBtn = $("#notebook-add");
  const form = $("#entry-form");
  if (addBtn) addBtn.addEventListener("click", () => {
    if (form) form.classList.toggle("hidden");
  });
  const saveBtn = $("#notebook-save");
  if (saveBtn) saveBtn.addEventListener("click", addEntry);
  const cancelBtn = $("#notebook-cancel");
  if (cancelBtn) cancelBtn.addEventListener("click", () => {
    if (form) form.classList.add("hidden");
  });
  const exportBtn = $("#notebook-export");
  if (exportBtn) exportBtn.addEventListener("click", exportNotebook);

  const searchInput = $("#notebook-search");
  if (searchInput) {
    searchInput.addEventListener("input", (e) => {
      clearTimeout(searchDebounce);
      searchDebounce = setTimeout(() => searchEntries(e.target.value), 300);
    });
  }
}

wireNotebook();

  window.initNotebook = initNotebook;
})();

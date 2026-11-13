(function () {
"use strict";
/* Cheat sheets come from the server (one per catalog tool), so they never drift from the app. */

let loaded = false;
let pending = null;

async function loadToolList() {
  const select = $("#cheat-sheets-tool-select");
  const { ok, data } = await api("GET", "/api/cheatsheets");
  if (!ok || !data || !Array.isArray(data.cheatsheets)) {
    toast((data && data.error) || "Could not load cheat sheets", true);
    return;
  }
  const sheets = data.cheatsheets;
  select.textContent = "";
  const first = document.createElement("option");
  first.value = "";
  first.textContent = "— Select a tool —";
  select.appendChild(first);
  sheets.sort((a, b) => a.title.localeCompare(b.title)).forEach((sheet) => {
    const opt = document.createElement("option");
    opt.value = sheet.tool_id;
    opt.textContent = sheet.title;
    select.appendChild(opt);
  });
  loaded = true;
}

async function loadCheatSheet(toolId) {
  const content = $("#cheat-sheets-content");
  content.textContent = "";
  if (!toolId) return;
  const { ok, data } = await api("GET", "/api/cheatsheets/" + encodeURIComponent(toolId));
  if (!ok || !data || !data.sections) {
    content.textContent = "No cheat sheet for this tool.";
    return;
  }
  const title = document.createElement("h3");
  title.textContent = data.title;
  content.appendChild(title);
  data.sections.forEach((section) => {
    const block = document.createElement("div");
    block.className = "section";
    const heading = document.createElement("h4");
    heading.textContent = section.heading;
    const pre = document.createElement("pre");
    pre.textContent = section.content_md;
    pre.title = "Click to copy";
    pre.addEventListener("click", () => {
      if (navigator.clipboard) navigator.clipboard.writeText(section.content_md);
      toast("Copied");
    });
    block.append(heading, pre);
    content.appendChild(block);
  });
}

async function initCheatSheets() {
  if (!loaded) await loadToolList();
  if (pending) {
    $("#cheat-sheets-tool-select").value = pending;
    await loadCheatSheet(pending);
    pending = null;
  }
}

/* Called from a tool's own panel: open the cheat sheets with that tool selected. */
function openCheatSheet(toolId) {
  pending = toolId;
  showPanel("cheat-sheets-panel");
}

$("#cheat-sheets-tool-select").addEventListener("change", (e) => loadCheatSheet(e.target.value));

window.initCheatSheets = initCheatSheets;
window.openCheatSheet = openCheatSheet;
})();

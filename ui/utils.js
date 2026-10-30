/* Kali Linux Windows Substitute - Shared UI Utilities
 * Keyboard shortcuts, command palette, and common helpers
 */
"use strict";

/* --- DOM Helpers -------------------------------------------------------- */
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

function esc(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

let toastTimer = null;
function toast(message, isError) {
  const el = $("#toast");
  if (!el) return;
  el.textContent = message;
  el.classList.toggle("error", !!isError);
  el.classList.remove("hidden");
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    el.classList.add("hidden");
    toastTimer = null;
  }, 4500);
}

/* --- API Helper --------------------------------------------------------- */
async function api(method, path, body, options = {}) {
  // 10-second timeout to prevent indefinite hangs.
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 10000);

  // If the caller also supplies a signal (e.g. a Stop button), abort on either.
  const callerSignal = options.signal;
  if (callerSignal) {
    if (callerSignal.aborted) controller.abort(callerSignal.reason);
    else callerSignal.addEventListener("abort", () => controller.abort(callerSignal.reason), { once: true });
  }

  const opts = {
    method,
    credentials: 'include',
    headers: {},
    signal: controller.signal
  };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  if (method !== "GET") opts.headers["X-KWS-CSRF"] = csrf();
  try {
    const resp = await fetch(path, opts);
    clearTimeout(timeoutId);
    const text = await resp.text();
    let data;
    try { data = text ? JSON.parse(text) : {}; } catch (_) { data = { raw: text }; }
    if (!resp.ok && !data.error) data.error = "request failed (" + resp.status + ")";
    return { ok: resp.ok, status: resp.status, data };
  } catch (err) {
    clearTimeout(timeoutId);
    if (err.name === "AbortError") {
      // Distinguish our timeout from a caller-initiated cancellation.
      if (callerSignal && callerSignal.aborted) throw err;
      return { ok: false, status: 408, data: { error: "Request timeout (10s)" } };
    }
    throw err;
  }
}

function csrf() {
  const m = document.cookie.match(/(?:^|;\s*)kws_csrf=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : "";
}

/* --- Keyboard Shortcuts ------------------------------------------------- */
const shortcuts = {
  "Ctrl+K": { action: "openCommandPalette", description: "Open command palette" },
  "Ctrl+H": { action: "goHome", description: "Go to home" },
  "Ctrl+M": { action: "goManager", description: "Go to tool manager" },
  "Ctrl+F": { action: "goFindings", description: "Go to findings" },
  "Ctrl+A": { action: "goAudit", description: "Go to audit log" },
  "Ctrl+T": { action: "focusSearch", description: "Focus tool search" },
  "Escape": { action: "closePanels", description: "Close open panels" },
  "F1": { action: "showHelp", description: "Show keyboard shortcuts" },
};

function initKeyboardShortcuts(handlers) {
  document.addEventListener("keydown", (e) => {
    let key = e.key;
    if (e.ctrlKey || e.metaKey) key = "Ctrl+" + key;
    const shortcut = shortcuts[key];
    if (!shortcut) return;
    
    e.preventDefault();
    
    if (handlers[shortcut.action]) {
      handlers[shortcut.action]();
    }
  });
}

/* --- Command Palette ---------------------------------------------------- */
let commandPalette = null;
let previousActiveElement = null;

function showCommandPalette(commands) {
  if (commandPalette) {
    commandPalette.remove();
    commandPalette = null;
    return;
  }

  // Save previously focused element to return focus later
  previousActiveElement = document.activeElement;

  const overlay = document.createElement("div");
  overlay.id = "command-palette-overlay";
  overlay.setAttribute("role", "dialog");
  overlay.setAttribute("aria-modal", "true");
  overlay.setAttribute("aria-label", "Command palette");
  overlay.style.cssText = `
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0, 0, 0, 0.4);
    backdrop-filter: blur(4px);
    z-index: 9999;
    display: flex;
    align-items: flex-start;
    justify-content: center;
    padding-top: 100px;
  `;

  const palette = document.createElement("div");
  palette.style.cssText = `
    width: 600px;
    max-width: 90vw;
    background: var(--panel, #fff);
    border: 1px solid var(--line, #e9ecef);
    border-radius: 12px;
    box-shadow: 0 10px 40px rgba(0,0,0,0.2);
    overflow: hidden;
  `;

  const input = document.createElement("input");
  input.placeholder = "Type a command...";
  input.setAttribute("aria-label", "Command search");
  input.style.cssText = `
    width: 100%;
    padding: 1rem 1.25rem;
    border: none;
    border-bottom: 1px solid var(--line, #e9ecef);
    font-size: 1rem;
    outline: none;
    background: transparent;
    color: var(--text, #212529);
  `;

  const list = document.createElement("ul");
  list.setAttribute("role", "listbox");
  list.style.cssText = `
    list-style: none;
    margin: 0;
    padding: 0;
    max-height: 400px;
    overflow-y: auto;
  `;

  function renderCommands(filter = "") {
    list.innerHTML = "";
    const filtered = commands.filter(cmd => 
      !filter || cmd.label.toLowerCase().includes(filter.toLowerCase()) ||
      (cmd.shortcut && cmd.shortcut.toLowerCase().includes(filter.toLowerCase()))
    );

    if (!filtered.length) {
      list.innerHTML = '<li style="padding: 1rem; color: var(--muted, #6c757d); text-align: center;">No commands found</li>';
      return;
    }

    let selectedIndex = 0;
    const items = [];

    filtered.forEach((cmd, index) => {
      const li = document.createElement("li");
      li.setAttribute("role", "option");
      li.setAttribute("aria-selected", "false");
      li.setAttribute("tabindex", "-1");
      li.style.cssText = `
        padding: 0.75rem 1.25rem;
        cursor: pointer;
        display: flex;
        justify-content: space-between;
        align-items: center;
        border-bottom: 1px solid var(--line, #e9ecef);
      `;
      if (index === 0) {
        li.style.background = "var(--accent-light, #e0e7ff)";
        li.setAttribute("aria-selected", "true");
        selectedIndex = 0;
      }

      li.innerHTML = `
        <span>${esc(cmd.label)}</span>
        ${cmd.shortcut ? `<span style="font-size: 0.75rem; color: var(--muted, #6c757d); background: var(--panel-hover, #f3f4f6); padding: 0.25rem 0.5rem; border-radius: 4px;">${esc(cmd.shortcut)}</span>` : ""}
      `;

      li.addEventListener("click", () => {
        cmd.action();
        closePalette();
      });

      li.addEventListener("mouseenter", () => {
        if (selectedIndex !== index) {
          items[selectedIndex].style.background = "";
          items[selectedIndex].setAttribute("aria-selected", "false");
          li.style.background = "var(--accent-light, #e0e7ff)";
          li.setAttribute("aria-selected", "true");
          selectedIndex = index;
        }
      });

      list.appendChild(li);
      items.push(li);
    });

    return { items, selectedIndex };
  }

  function closePalette() {
    overlay.remove();
    commandPalette = null;
    // Return focus to previous element
    if (previousActiveElement && previousActiveElement.focus) {
      previousActiveElement.focus();
    }
  }

  window.closeCommandPalette = closePalette;

  input.addEventListener("input", (e) => {
    const { items, selectedIndex } = renderCommands(e.target.value);
    if (items.length > 0) {
      items[selectedIndex].style.background = "var(--accent-light, #e0e7ff)";
      items[selectedIndex].setAttribute("aria-selected", "true");
    }
  });

  input.addEventListener("keydown", (e) => {
    const { items, selectedIndex } = renderCommands(input.value);
    
    if (e.key === "Escape") {
      closePalette();
    } else if (e.key === "Enter" && items.length > 0) {
      items[selectedIndex].click();
    } else if (e.key === "ArrowDown" && items.length > 0) {
      e.preventDefault();
      const newIndex = Math.min(selectedIndex + 1, items.length - 1);
      items[selectedIndex].style.background = "";
      items[selectedIndex].setAttribute("aria-selected", "false");
      items[newIndex].style.background = "var(--accent-light, #e0e7ff)";
      items[newIndex].setAttribute("aria-selected", "true");
      items[newIndex].scrollIntoView({ block: "nearest" });
    } else if (e.key === "ArrowUp" && items.length > 0) {
      e.preventDefault();
      const newIndex = Math.max(selectedIndex - 1, 0);
      items[selectedIndex].style.background = "";
      items[selectedIndex].setAttribute("aria-selected", "false");
      items[newIndex].style.background = "var(--accent-light, #e0e7ff)";
      items[newIndex].setAttribute("aria-selected", "true");
      items[newIndex].scrollIntoView({ block: "nearest" });
    }
  });

  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) closePalette();
  });

  palette.appendChild(input);
  palette.appendChild(list);
  overlay.appendChild(palette);
  document.body.appendChild(overlay);
  commandPalette = overlay;
  input.focus();
  renderCommands();
}

/* --- Panel Navigation --------------------------------------------------- */
function navigateToPanel(panelId) {
  // Hide all panels
  $$(".panel").forEach(panel => {
    if (!panel.classList.contains("hidden")) {
      panel.classList.add("hidden");
    }
  });
  
  // Remove active from all sidebar items
  $$("#view-list li").forEach(li => {
    li.classList.remove("active");
  });
  
  // Show target panel
  const target = $("#" + panelId);
  if (target) {
    target.classList.remove("hidden");
  }
  
  // Activate sidebar item
  const sidebarItem = $(`#view-list li[data-view="${panelId.replace('-panel', '')}"]`);
  if (sidebarItem) {
    sidebarItem.classList.add("active");
  }
}

/* --- Responsive Helpers ------------------------------------------------- */
function isMobile() {
  return window.innerWidth <= 760;
}

function initResponsiveSidebar() {
  const sidebar = $(".sidebar");
  if (!sidebar) return;
  
  const toggle = document.createElement("button");
  toggle.innerHTML = "☰";
  toggle.className = "ghost";
  toggle.style.cssText = `
    position: fixed;
    top: 1rem;
    left: 1rem;
    z-index: 100;
    display: none;
    width: 44px;
    height: 44px;
    border-radius: 8px;
    align-items: center;
    justify-content: center;
    font-size: 1.25rem;
  `;
  
  toggle.addEventListener("click", () => {
    sidebar.classList.toggle("sidebar-open");
  });
  
  document.body.appendChild(toggle);
  
  function update() {
    if (isMobile()) {
      toggle.style.display = "flex";
      sidebar.classList.add("sidebar-mobile");
    } else {
      toggle.style.display = "none";
      sidebar.classList.remove("sidebar-mobile", "sidebar-open");
    }
  }
  
  update();
  window.addEventListener("resize", update);
}

/* --- Loading States ----------------------------------------------------- */
function showLoading(element, message = "Loading...") {
  if (!element) return;
  element.innerHTML = `
    <div style="display: flex; align-items: center; justify-content: center; gap: 0.5rem; color: var(--muted);">
      <span class="spinner"></span>
      <span>${esc(message)}</span>
    </div>
  `;
}

function hideLoading(element) {
  if (!element) return;
  const loader = element.querySelector(".spinner");
  if (loader) loader.parentElement.remove();
}

/* --- Export utilities --------------------------------------------------- */
/* Global exports for script tags */
if (typeof window !== "undefined") {
  window.$ = $;
  window.$$ = $$;
  window.esc = esc;
  window.toast = toast;
  window.api = api;
  window.csrf = csrf;
  window.shortcuts = shortcuts;
  window.initKeyboardShortcuts = initKeyboardShortcuts;
  window.showCommandPalette = showCommandPalette;
  window.navigateToPanel = navigateToPanel;
  window.isMobile = isMobile;
  window.initResponsiveSidebar = initResponsiveSidebar;
  window.showLoading = showLoading;
  window.hideLoading = hideLoading;
}

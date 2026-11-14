(function () {
"use strict";
/* 
 * Kali Linux Windows Substitute - Playground Panel
 */

let playgroundRunning = false;

let statusTimer = null;

async function initPlayground() {
  await loadStatus();
  // Auto-refresh status every 5s when tab visible; started once, not per open.
  if (!statusTimer) {
    statusTimer = setInterval(() => {
      if (!$("#playground-panel").classList.contains("hidden") && document.visibilityState === "visible") {
        loadStatus();
      }
    }, 5000);
  }
}

let statusLoading = false;

async function loadStatus() {
  if (statusLoading) return;
  statusLoading = true;
  try {
    const { ok, data } = await api("GET", "/api/playground/status", undefined, { timeout: 30000 });
    const statusEl = $("#playground-status");
    if (!ok || !data) {
      // Keep the last known state; a failed check is not the same as "not running".
      statusEl.textContent = "Could not read playground status: " + ((data && data.error) || "unknown error");
      statusEl.classList.add("error");
      return;
    }
    applyStatus(data, statusEl);
  } finally {
    statusLoading = false;
  }
}

function applyStatus(data, statusEl) {
  if (data.running) {
    statusEl.textContent = "Running on 127.0.0.1:3000";
    statusEl.classList.remove("error");
    playgroundRunning = true;
    $("#playground-start").disabled = true;
    $("#playground-stop").disabled = false;
    $("#playground-text").textContent =
      "Running. Point a tool at http://127.0.0.1:3000 (try sqlmap on /sqli?id=1, or nikto and ffuf).";
  } else {
    statusEl.textContent = "Not running";
    statusEl.classList.add("error");
    playgroundRunning = false;
    $("#playground-start").disabled = false;
    $("#playground-stop").disabled = true;
    $("#playground-text").textContent = "Start the playground to test security tools.";
  }
}

async function startPlayground() {
  const btn = $("#playground-start");
  btn.disabled = true;
  btn.textContent = "Starting\u2026";
  const { data } = await api("POST", "/api/playground/start", {}, { timeout: 60000 });
  btn.textContent = "Start";
  toast(data.message || data.error || "done", !!data.error || data.ok === false);
  loadStatus();
}

async function stopPlayground() {
  const { data } = await api("POST", "/api/playground/stop");
  toast(data.message || data.error || "done", !!data.error);
  loadStatus();
}

async function openInBrowser() {
  if (!playgroundRunning) {
    toast("Playground is not running", true);
    return;
  }
  window.open("http://127.0.0.1:3000", "_blank");
}

/* $, $$, esc, toast, api provided globally by utils.js */

function wirePlayground() {
  $("#playground-start").addEventListener("click", startPlayground);
  $("#playground-stop").addEventListener("click", stopPlayground);
  $("#playground-open").addEventListener("click", openInBrowser);
}

wirePlayground();

  window.initPlayground = initPlayground;
})();

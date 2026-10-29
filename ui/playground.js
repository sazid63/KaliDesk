/* 
 * Kali Linux Windows Substitute - Playground Panel
 */

let playgroundRunning = false;

async function initPlayground() {
  await loadStatus();
  // Auto-refresh status every 5s when tab visible
  setInterval(() => {
    if (!$("#playground-panel").classList.contains("hidden") && document.visibilityState === "visible") {
      loadStatus();
    }
  }, 5000);
}

async function loadStatus() {
  const { data } = await api("GET", "/api/playground/status");
  const statusEl = $("#playground-status");
  
  if (data.running) {
    statusEl.textContent = "Running on 127.0.0.1:3000";
    statusEl.classList.remove("error");
    playgroundRunning = true;
    $("#playground-start").disabled = true;
    $("#playground-stop").disabled = false;
    $("#playground-text").textContent = "The vulnerable app is running. Click 'Open in Browser' to test.";
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
  const { data } = await api("POST", "/api/playground/start");
  toast(data.message || data.error || "done", !!data.error);
  if (data.running) {
    loadStatus();
  }
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

async function wire() {
  $("#playground-start").addEventListener("click", startPlayground);
  $("#playground-stop").addEventListener("click", stopPlayground);
}

function esc(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
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
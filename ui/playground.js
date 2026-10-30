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

/* $, $$, esc, toast, api provided globally by utils.js */

function wire() {
  $("#playground-start").addEventListener("click", startPlayground);
  $("#playground-stop").addEventListener("click", stopPlayground);
}

wire();
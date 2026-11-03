/* Strix UI Logic */

function strixRefresh() {
  api("GET", "/api/strix/status").then(r => {
    if (!r || !r.data) {
      document.getElementById("strix-text").textContent = "Error checking status";
      return;
    }
    const installed = r.data.installed;
    const running = r.data.running;
    const pid = r.data.pid;
    const url = r.data.url;

    document.getElementById("strix-dot").className = "dot " +
        (running ? "ok" : installed ? "info" : "bad");
    document.getElementById("strix-text").textContent =
        running ? "Running" : installed ? "Installed" : "Not installed";

    document.getElementById("strix-install").disabled = installed;
    document.getElementById("strix-start").disabled = !installed || running;
    document.getElementById("strix-stop").disabled = !running;

    const iframe = document.getElementById("strix-iframe");
    const log = document.getElementById("strix-log");
    if (running && url) {
      // Validate URL is local/loopback before loading in iframe
      try {
        const parsedUrl = new URL(url);
        const allowedHosts = ['127.0.0.1', 'localhost', '[::1]'];
        if (allowedHosts.includes(parsedUrl.hostname)) {
          iframe.src = url;
          iframe.sandbox.add("allow-scripts", "allow-same-origin", "allow-forms");
          iframe.classList.remove("hidden");
          log.classList.add("hidden");
        } else {
          log.textContent = "Strix URL not allowed (external host blocked by policy).";
          log.classList.remove("hidden");
          iframe.classList.add("hidden");
        }
      } catch (e) {
        log.textContent = "Invalid Strix URL.";
        log.classList.remove("hidden");
        iframe.classList.add("hidden");
      }
    } else {
      iframe.classList.add("hidden");
      log.classList.remove("hidden");
      if (!installed) {
        log.textContent = "Strix is not installed. Click Install to begin.";
      } else if (!running) {
        log.textContent = "Strix is installed but not running. Click Start to begin.";
      }
    }
  }).catch(() => {
    document.getElementById("strix-text").textContent = "Error checking status";
  });
}

function strixInstall() {
  const btn = document.getElementById("strix-install");
  const text = document.getElementById("strix-text");
  btn.disabled = true;
  text.textContent = "Installing...";

  api("POST", "/api/strix/install").then(r => {
    if (r.data && r.data.ok) {
      // Poll until installed using the new pollUntil helper
      pollUntil("/api/strix/status", (data) => data && data.installed, {
        maxAttempts: 60,
        interval: 2000,
        timeout: 120000
      }).then(() => strixRefresh()).catch(() => strixRefresh());
    } else {
      toast("Install failed: " + (r.data && r.data.message ? r.data.message : "unknown error"), true);
      btn.disabled = false;
      strixRefresh();
    }
  }).catch(e => {
    toast("Install failed: " + e, true);
    btn.disabled = false;
    strixRefresh();
  });
}

function strixStart() {
  const btn = document.getElementById("strix-start");
  const text = document.getElementById("strix-text");
  btn.disabled = true;
  text.textContent = "Starting...";

  api("POST", "/api/strix/start").then(r => {
    if (r.data && r.data.ok) {
      // Poll until running using the new pollUntil helper
      pollUntil("/api/strix/status", (data) => data && data.running, {
        maxAttempts: 60,
        interval: 2000,
        timeout: 120000
      }).then(() => strixRefresh()).catch(() => strixRefresh());
    } else {
      toast("Start failed: " + (r.data && r.data.message ? r.data.message : "unknown error"), true);
      btn.disabled = false;
      strixRefresh();
    }
  }).catch(e => {
    toast("Start failed: " + e, true);
    btn.disabled = false;
    strixRefresh();
  });
}

function strixStop() {
  const btn = document.getElementById("strix-stop");
  const text = document.getElementById("strix-text");
  btn.disabled = true;
  text.textContent = "Stopping...";

  api("POST", "/api/strix/stop").then(r => {
    if (r.data && r.data.ok) {
      strixRefresh();
    } else {
      toast("Stop failed: " + (r.data && r.data.message ? r.data.message : "unknown error"), true);
      btn.disabled = false;
      strixRefresh();
    }
  }).catch(e => {
    toast("Stop failed: " + e, true);
    btn.disabled = false;
    strixRefresh();
  });
}

function strixInfo() {
  const tooltip = document.getElementById("strix-tooltip");
  tooltip.classList.toggle("hidden");
}

document.addEventListener("DOMContentLoaded", () => {
  const installBtn = document.getElementById("strix-install");
  const startBtn = document.getElementById("strix-start");
  const stopBtn = document.getElementById("strix-stop");
  const refreshBtn = document.getElementById("strix-refresh");
  const infoBtn = document.getElementById("strix-info");

  if (installBtn) installBtn.onclick = strixInstall;
  if (startBtn) startBtn.onclick = strixStart;
  if (stopBtn) stopBtn.onclick = strixStop;
  if (refreshBtn) refreshBtn.onclick = strixRefresh;
  if (infoBtn) infoBtn.onclick = strixInfo;

  // Auto-refresh when tab is visible
  const strixPanel = document.getElementById("strix-panel");
  const observer = new MutationObserver(mutations => {
    for (const mutation of mutations) {
      if (mutation.attributeName === "class") {
        if (!strixPanel.classList.contains("hidden")) {
          strixRefresh();
        }
      }
    }
  });
  observer.observe(strixPanel, { attributes: true });
});

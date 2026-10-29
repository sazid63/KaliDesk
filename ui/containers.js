/*
 * Kali Linux Windows Substitute - Containers Panel (Podman Manager)
 */

let currentTab = "images";
let images = [];
let containers = [];

async function initContainers() {
  await loadContainers();
  wireContainers();
  // Auto-refresh every 10s when tab is visible
  setInterval(() => {
    if (document.visibilityState === "visible" && !$("#containers-panel").classList.contains("hidden")) {
      loadContainers();
    }
  }, 10000);
}

async function loadContainers() {
  const { data } = await api("GET", "/api/containers/status");
  const status = $("#containers-status");
  
  if (data.podman_installed) {
    status.textContent = "Podman ready";
    status.classList.remove("error");
    images = data.images || [];
    containers = data.containers || [];
    renderImages();
    renderContainers();
  } else {
    status.textContent = "Podman not installed";
    status.classList.add("error");
    images = [];
    containers = [];
    renderImages();
    renderContainers();
  }
}

function renderImages() {
  const list = $("#containers-images-list");
  const empty = $("#containers-images-empty");
  list.innerHTML = "";
  
  if (!images.length) {
    empty.style.display = "block";
    return;
  }
  
  empty.style.display = "none";
  images.forEach((img) => {
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML =
      '<div class="manager-info">' +
      '<h3>' + esc(img.name) + '</h3>' +
      '<p class="muted">ID: ' + esc(img.id) + '</p>' +
      '<p class="muted">Size: ' + (img.size / 1024 / 1024).toFixed(1) + ' MB</p>' +
      '<p class="muted">Created: ' + esc(img.created) + '</p>' +
      '</div>' +
      '<div class="manager-actions"></div>';
    
    const actions = card.querySelector(".manager-actions");
    const runBtn = document.createElement("button");
    runBtn.className = "primary";
    runBtn.textContent = "Run";
    runBtn.addEventListener("click", () => {
      $("#containers-run-image").value = img.name;
      showTab("run");
    });
    actions.appendChild(runBtn);
    
    list.appendChild(card);
  });
}

function renderContainers() {
  const list = $("#containers-containers-list");
  const empty = $("#containers-containers-empty");
  list.innerHTML = "";
  
  if (!containers.length) {
    empty.style.display = "block";
    return;
  }
  
  empty.style.display = "none";
  containers.forEach((cont) => {
    const row = document.createElement("div");
    row.className = "card";
    row.innerHTML =
      '<div class="manager-info">' +
      '<h3>' + esc(cont.names.join(", ")) + '</h3>' +
      '<p class="muted">Image: ' + esc(cont.image) + '</p>' +
      '<p class="muted">Status: ' + esc(cont.status) + '</p>' +
      '<p class="muted">Ports: ' + esc(cont.ports || "—") + '</p>' +
      '</div>' +
      '<div class="manager-actions"></div>';
    
    const actions = row.querySelector(".manager-actions");
    
    if (cont.status.includes("running")) {
      const stopBtn = document.createElement("button");
      stopBtn.className = "ghost";
      stopBtn.textContent = "Stop";
      stopBtn.addEventListener("click", () => stopContainer(cont.id));
      actions.appendChild(stopBtn);
    } else {
      const startBtn = document.createElement("button");
      startBtn.className = "primary";
      startBtn.textContent = "Start";
      startBtn.addEventListener("click", () => startContainer(cont.id));
      actions.appendChild(startBtn);
    }
    
    const logsBtn = document.createElement("button");
    logsBtn.className = "ghost";
    logsBtn.textContent = "Logs";
    logsBtn.addEventListener("click", () => viewLogs(cont.id));
    actions.appendChild(logsBtn);
    
    const removeBtn = document.createElement("button");
    removeBtn.className = "ghost";
    removeBtn.textContent = "Remove";
    removeBtn.addEventListener("click", () => removeContainer(cont.id));
    actions.appendChild(removeBtn);
    
    list.appendChild(row);
  });
}

function showTab(tab) {
  currentTab = tab;
  $$(".tabs.button").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.tab === tab);
  });
  $$(".tab-content").forEach((div) => {
    div.classList.toggle("hidden", div.id !== "containers-" + tab);
  });
}

function wireContainers() {
  // Tabs
  $$(".tabs.button").forEach((btn) => {
    btn.addEventListener("click", () => showTab(btn.dataset.tab));
  });
  
  // Refresh
  $("#containers-refresh").addEventListener("click", loadContainers);
  $("#containers-refresh-containers").addEventListener("click", loadContainers);
  
  // Install Podman
  $("#containers-install-podman").addEventListener("click", async () => {
    const btn = $("#containers-install-podman");
    btn.disabled = true;
    btn.textContent = "Installing...";
    const { data } = await api("POST", "/api/containers/podman/install");
    btn.disabled = false;
    btn.textContent = "Install Podman";
    toast(data.message || data.error || "done", !!data.error);
    loadContainers();
  });
  
  // Pull custom image
  $("#containers-pull-custom").addEventListener("click", async () => {
    const name = prompt("Enter image name (e.g., nginx:latest):");
    if (!name) return;
    const { data } = await api("POST", "/api/containers/images/pull", { name });
    toast(data.message || data.error || "done", !!data.error);
    loadContainers();
  });
  
  // Run container form
  $("#containers-run-image").addEventListener("change", () => {
    const customDiv = $("#containers-run-custom-image");
    customDiv.style.display = $("#containers-run-image").value === "custom" ? "block" : "none";
  });
  
  $("#containers-run-submit").addEventListener("click", async () => {
    let image = $("#containers-run-image").value;
    if (image === "custom") {
      image = $("#containers-run-custom-image-input").value;
      if (!image) {
        toast("Custom image name required", true);
        return;
      }
    }
    const name = $("#containers-run-name").value;
    if (!name) {
      toast("Container name required", true);
      return;
    }
    
    const portsStr = $("#containers-run-ports").value;
    const ports = portsStr ? portsStr.split(",").map(s => s.trim()) : [];
    
    const volumesStr = $("#containers-run-volumes").value;
    const volumes = volumesStr ? volumesStr.split(",").map(s => s.trim()) : [];
    
    const btn = $("#containers-run-submit");
    btn.disabled = true;
    btn.textContent = "Running...";
    
    const { data } = await api("POST", "/api/containers/run", {
      image, name, ports, volumes
    });
    
    btn.disabled = false;
    btn.textContent = "Run Container";
    
    toast(data.message || data.error || "done", !!data.error);
    if (data.ok) {
      showTab("containers");
      loadContainers();
    }
  });
  
  $("#containers-run-cancel").addEventListener("click", () => {
    $("#containers-run-form").reset();
    $("#containers-run-custom-image").style.display = "none";
    showTab("images");
  });
}

async function startContainer(id) {
  const { data } = await api("POST", "/api/containers/" + id + "/start");
  toast(data.message || data.error || "done", !!data.error);
  loadContainers();
}

async function stopContainer(id) {
  const { data } = await api("POST", "/api/containers/" + id + "/stop");
  toast(data.message || data.error || "done", !!data.error);
  loadContainers();
}

async function removeContainer(id) {
  if (!confirm("Remove container " + id + "?")) return;
  const { data } = await api("DELETE", "/api/containers/" + id);
  toast(data.message || data.error || "done", !!data.error);
  loadContainers();
}

async function viewLogs(id) {
  const { data } = await api("GET", "/api/containers/" + id + "/logs");
  if (data.ok) {
    // Show logs in a modal
    const modal = document.createElement("div");
    modal.className = "modal";
    modal.innerHTML =
      '<div class="modal-content">' +
      '<h3>Logs: ' + id + '</h3>' +
      '<pre class="logs">' + esc(data.logs) + '</pre>' +
      '<div class="actions"><button class="primary" id="modal-close">Close</button></div>' +
      '</div>';
    document.body.appendChild(modal);
    document.getElementById("modal-close").addEventListener("click", () => modal.remove());
  } else {
    toast(data.error || "Failed to get logs", true);
  }
}

// API wrapper
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

function wire() {
}

wire();
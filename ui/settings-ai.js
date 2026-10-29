
/* Kali Linux Windows Substitute - AI Settings Panel
 * Managing AI providers: OpenAI, Anthropic, Gemini, Ollama, Local AI, OpenCode, DeepSeek
 */

let currentProvider = null;

async function loadProviders() {
  const { data } = await api("GET", "/api/ai/providers");
  const container = $("#ai-providers-container");
  container.innerHTML = "";

  if (!(data || []).length) {
    container.innerHTML = '<p class="muted">No providers configured.</p>';
    return;
  }

  data.forEach((provider) => {
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML =
      '<div class="manager-info">' +
      "<h3>" + esc(provider.name) + "</h3>" +
      '<p>' + esc(provider.type) + "</p>" +
      (provider.model ? '<p class="muted">Model: ' + esc(provider.model) + "</p>" : "") +
      "</div>" +
      '<div class="manager-actions"></div>';
    
    const actions = card.querySelector(".manager-actions");
    const editBtn = document.createElement("button");
    editBtn.className = "ghost";
    editBtn.textContent = "Edit";
    editBtn.addEventListener("click", () => editProvider(provider));
    actions.appendChild(editBtn);

    const delBtn = document.createElement("button");
    delBtn.className = "ghost";
    delBtn.textContent = "Delete";
    delBtn.addEventListener("click", () => deleteProvider(provider.name));
    actions.appendChild(delBtn);

    container.appendChild(card);
  });
}

function editProvider(provider) {
  currentProvider = provider;
  $("#ai-provider-select").value = provider.type;
  $("#ai-provider-form-title").textContent = "Edit: " + provider.name;
  showProviderForm(provider.type, provider.config);
  $("#ai-provider-submit").textContent = "Update";
  $("#ai-provider-delete").disabled = false;
  $("#ai-provider-form").classList.remove("hidden");
}

async function deleteProvider(name) {
  if (!confirm(`Delete provider "${name}"?`)) return;
  const { data } = await api("DELETE", "/api/ai/providers/" + encodeURIComponent(name));
  toast(data.message || "Provider deleted");
  loadProviders();
  clearForm();
}

function clearForm() {
  currentProvider = null;
  $("#ai-provider-select").value = "";
  $("#ai-provider-form-title").textContent = "Provider Settings";
  $("#ai-provider-form-content").innerHTML = "";
  $("#ai-provider-submit").textContent = "Save";
  $("#ai-provider-delete").disabled = true;
  $("#ai-provider-form").classList.add("hidden");
}

function showProviderForm(type, config = {}) {
  const content = $("#ai-provider-form-content");
  content.innerHTML = "";

  // Common fields
  const nameField = document.createElement("div");
  nameField.className = "field";
  nameField.innerHTML = `
    <label for="ai-provider-name">Name</label>
    <input id="ai-provider-name" type="text" placeholder="My OpenAI Account" ${config.name ? 'value="' + esc(config.name) + '"' : ""}>
  `;
  content.appendChild(nameField);

  switch (type) {
    case "openai":
    case "anthropic":
    case "gemini":
      content.innerHTML += `
        <div class="field">
          <label for="ai-api-key">API Key</label>
          <input id="ai-api-key" type="password" placeholder="••••••••" ${config.api_key ? 'value="' + "•".repeat(8) + '"' : ""}>
        </div>
        <div class="field">
          <label for="ai-base-url">Base URL (optional)</label>
          <input id="ai-base-url" type="text" placeholder="https://api.openai.com/v1" value="${config.base_url || ""}">
        </div>
        <div class="field">
          <label for="ai-model">Model</label>
          <select id="ai-model" class="grow"></select>
        </div>
      `;
      break;

    case "ollama":
      content.innerHTML += `
        <div class="field">
          <label for="ai-ollama-url">Base URL</label>
          <input id="ai-ollama-url" type="text" placeholder="http://127.0.0.1:11434" value="${config.base_url || "http://127.0.0.1:11434"}">
        </div>
        <div class="field">
          <label for="ai-ollama-model">Model</label>
          <select id="ai-ollama-model" class="grow"></select>
        </div>
        <button class="ghost" id="ai-ollama-refresh">Refresh models</button>
      `;
      break;

    case "local":
      content.innerHTML += `
        <div class="field">
          <label for="ai-local-model">Model</label>
          <select id="ai-local-model" class="grow"></select>
        </div>
        <div class="field">
          <label for="ai-llama-path">llama.cpp path (optional)</label>
          <input id="ai-llama-path" type="text" placeholder="Auto-detected" value="${config.llama_path || ""}">
        </div>
        <button class="ghost" id="ai-local-refresh">Refresh models</button>
      `;
      break;

    case "opencode":
      content.innerHTML += `
        <div class="field">
          <label for="ai-host-port">Host:Port</label>
          <input id="ai-host-port" type="text" placeholder="127.0.0.1:11434" value="${config.host_port || "127.0.0.1:11434"}">
        </div>
      `;
      break;

    case "deepseek_harness":
      content.innerHTML += `
        <div class="field">
          <label for="ai-harness-host">Host</label>
          <input id="ai-harness-host" type="text" placeholder="127.0.0.1" value="${config.freellmapi_host || "127.0.0.1"}">
        </div>
        <div class="field">
          <label for="ai-harness-port">Port</label>
          <input id="ai-harness-port" type="text" placeholder="31415" value="${config.freellmapi_port || 31415}">
        </div>
        <div class="field">
          <label for="ai-harness-api-key">FreeLLMAPI API Key (optional)</label>
          <input id="ai-harness-api-key" type="password" placeholder="••••••••" value="${config.api_key ? "•".repeat(8) : ""}">
        </div>
      `;
      break;

    default:
      content.innerHTML = "<p class="muted">Select a provider to configure.</p>";
      return;
  }

  content.innerHTML += `
    <div class="field">
      <label for="ai-auto-detect">Auto-detect available models</label>
      <button class="ghost" id="ai-auto-detect-btn">Detect</button>
    </div>
  `;

  // Load models for applicable providers
  if (["openai", "anthropic", "gemini", "local"].includes(type)) {
    loadModels(type);
  }

  // Auto-detect buttons
  if (type === "ollama") {
    document.getElementById("ai-ollama-refresh").addEventListener("click", () => loadOllamaModels());
  }
  if (type === "local") {
    document.getElementById("ai-local-refresh").addEventListener("click", () => loadLocalModels());
  }
  document.getElementById("ai-auto-detect-btn").addEventListener("click", () => {
    if (type === "opencode") autoDetectOpenCode();
    else if (type === "deepseek") autoDetectDeepSeek();
    else if (type === "ollama") loadOllamaModels();
    else if (type === "local") loadLocalModels();
  });
}

async function loadModels(type) {
  try {
    const { data } = await api("GET", "/api/ai/models?type=" + type);
    let select;
    if (type === "local") {
      select = $("#ai-local-model");
      select.innerHTML = '<option value=""> — Select model — </option>';
      data.forEach((m) => {
        const opt = document.createElement("option");
        opt.value = m.path;
        opt.textContent = m.name + " (" + (m.size_mb || 0) + "MB)";
        select.appendChild(opt);
      });
    } else {
      select = $("#ai-model");
      select.innerHTML = '<option value=""> — Select model — </option>';
      (data || []).forEach((m) => {
        const opt = document.createElement("option");
        opt.value = m;
        opt.textContent = m;
        select.appendChild(opt);
      });
    }
  } catch (e) {
    toast("Could not load models", true);
  }
}

async function loadOllamaModels() {
  try {
    const { data } = await api("GET", "/api/ai/models?type=ollama");
    const select = $("#ai-ollama-model");
    select.innerHTML = '<option value=""> — Select model — </option>';
    (data || []).forEach((m) => {
      const opt = document.createElement("option");
      opt.value = m;
      opt.textContent = m;
      select.appendChild(opt);
    });
  } catch (e) {
    toast("Ollama not reachable", true);
  }
}

async function loadLocalModels() {
  try {
    const { data } = await api("GET", "/api/ai/models?type=local");
    const select = $("#ai-local-model");
    select.innerHTML = '<option value=""> — Select model — </option>';
    (data || []).forEach((m) => {
      const opt = document.createElement("option");
      opt.value = m.path;
      opt.textContent = m.name + " (" + (m.size_mb || 0) + "MB)";
      select.appendChild(opt);
    });
  } catch (e) {
    toast("Local AI not initialized", true);
  }
}

async function autoDetectOpenCode() {
  // Scan localhost ports 11434, 11435, etc.
  const ports = [11434, 11435, 8080, 8000, 3000];
  const found = [];
  for (const port of ports) {
    try {
      const res = await fetch("http://127.0.0.1:" + port + "/health", { timeout: 500 });
      if (res.ok) {
        const data = await res.json();
        if (data && data.app && data.app.name.includes("OpenCode")) {
          found.push(port);
        }
      } catch (_) {}
    }
  }
  if (found.length) {
    $("#ai-host-port").value = "127.0.0.1:" + found[0];
    toast("OpenCode detected on port " + found[0]);
  } else {
    toast("OpenCode not detected on common ports", true);
  }
}

async function autoDetectDeepSeek() {
  // Scan for FreeLLMAPI (DSH backend) on common ports
  const ports = [31415, 31416, 8080, 8000];
  const found = [];
  for (const port of ports) {
    try {
      const res = await fetch("http://127.0.0.1:" + port + "/v1/models", { timeout: 500 });
      if (res.ok) {
        found.push(port);
      }
    } catch (_) {}
  }
  if (found.length) {
    $("#ai-harness-host").value = "127.0.0.1";
    $("#ai-harness-port").value = found[0].toString();
    toast("FreeLLMAPI (DSH backend) detected on port " + found[0]);
  } else {
    toast("FreeLLMAPI not detected on common ports", true);
  }
}

async function testProvider() {
  const type = $("#ai-provider-select").value;
  if (!type || type === "none") {
    toast("Select a provider to test", true);
    return;
  }

  const payload = { type };
  // Collect form fields — map field IDs to config keys
  const fields = $$("#ai-provider-form-content input, #ai-provider-form-content select");
  fields.forEach((el) => {
    if (el.type === "password" && el.value === "•".repeat(8)) return; // Don't send masked key
    payload[el.id] = el.value;
  });
  // Normalize deepseek_harness field IDs to config keys the backend expects
  if (type === "deepseek_harness") {
    payload.config = {};
    if (payload["ai-harness-host"]) payload.config.freellmapi_host = payload["ai-harness-host"];
    if (payload["ai-harness-port"]) payload.config.freellmapi_port = parseInt(payload["ai-harness-port"], 10);
    if (payload["ai-harness-api-key"]) payload.config.api_key = payload["ai-harness-api-key"];
  }

  const btn = $("#ai-provider-test");
  btn.disabled = true;
  btn.textContent = "Testing...";
  try {
    const { data } = await api("POST", "/api/ai/test", payload);
    if (data.ok) {
      toast("Connection successful", false);
    } else {
      toast("Connection failed: " + (data.error || "unknown"), true);
    }
  } catch (e) {
    toast("Test failed", true);
  } finally {
    btn.disabled = false;
    btn.textContent = "Test";
  }
}

async function saveProvider() {
  const type = $("#ai-provider-select").value;
  if (!type || type === "none") {
    toast("Select a provider", true);
    return;
  }

  const name = $("#ai-provider-name").value.trim();
  if (!name) {
    toast("Provider name is required", true);
    return;
  }

  const payload = { type, name };
  // Collect form fields — map field IDs to config keys
  const fields = $$("#ai-provider-form-content input, #ai-provider-form-content select");
  fields.forEach((el) => {
    if (el.type === "password" && el.value === "•".repeat(8)) return; // Don't send masked key
    payload[el.id] = el.value;
  });
  // Normalize deepseek_harness field IDs to config keys the backend expects
  if (type === "deepseek_harness") {
    if (payload["ai-harness-host"]) payload.config = payload.config || {};
    if (payload["ai-harness-host"]) payload.config.freellmapi_host = payload["ai-harness-host"];
    if (payload["ai-harness-port"]) payload.config.freellmapi_port = parseInt(payload["ai-harness-port"], 10);
    if (payload["ai-harness-api-key"]) payload.config.api_key = payload["ai-harness-api-key"];
  }

  const url = currentProvider ? "/api/ai/providers/" + encodeURIComponent(currentProvider.name) : "/api/ai/providers";
  const method = currentProvider ? "POST" : "POST"; // POST for both create and update
  
  const btn = $("#ai-provider-submit");
  btn.disabled = true;
  btn.textContent = "Saving...";
  try {
    const { data } = await api("POST", url, payload);
    toast(data.message || "Provider saved");
    loadProviders();
    clearForm();
  } catch (e) {
    toast("Save failed", true);
  } finally {
    btn.disabled = false;
    btn.textContent = currentProvider ? "Update" : "Save";
  }
}

// Wiring
function wireSettingsAI() {
  $("#ai-provider-select").addEventListener("change", () => {
    if (currentProvider && !confirm("Switching providers will discard unsaved changes.")) {
      $("#ai-provider-select").value = currentProvider.type;
      return;
    }
    clearForm();
    const type = $("#ai-provider-select").value;
    if (type && type !== "none") {
      showProviderForm(type);
    }
  });

  $("#ai-provider-save").addEventListener("click", () => {
    const type = $("#ai-provider-select").value;
    if (type && type !== "none") {
      showProviderForm(type);
    }
  });

  $("#ai-provider-test").addEventListener("click", testProvider);
  $("#ai-provider-delete").addEventListener("click", () => {
    if (currentProvider) deleteProvider(currentProvider.name);
  });

  $("#ai-provider-cancel").addEventListener("click", clearForm);
  $("#ai-provider-submit").addEventListener("click", saveProvider);
}

async function loadSettingsAI() {
  loadProviders();
  wireSettingsAI();
}

document.addEventListener("DOMContentLoaded", loadSettingsAI);

/*
 * Kali Linux Windows Substitute - AI CyberSecurity Chat Panel
 * Full-featured chat with conversation management, tool confirmation, markdown rendering
 */

let currentConversationId = null;
let abortController = null;
let availableTools = [];
let availableSkills = [];

async function initAiChat() {
  await loadConversations();
  await loadTools();
  await loadSkills();
  await checkEmbeddedApps();
  wireAiChat();
}

async function checkEmbeddedApps() {
  const opencodeMode = document.querySelector('#ai-chat-mode option[value="opencode"]')
  try {
    const res = await fetch("http://127.0.0.1:4096/health", { timeout: 2000 })
    if (!res.ok && opencodeMode) {
      opencodeMode.disabled = true
      opencodeMode.textContent = "OpenCode (not running)"
    }
  } catch (_) {
    if (opencodeMode) {
      opencodeMode.disabled = true
      opencodeMode.textContent = "OpenCode (not running)"
    }
  }
  const dshMode = document.querySelector('#ai-chat-mode option[value="dsh"]')
  try {
    const res = await fetch("http://127.0.0.1:55551/", { timeout: 2000 })
    if (res.status === 401) {
      if (dshMode) { dshMode.disabled = false; dshMode.textContent = "DeepSeek Harness" }
    } else if (!res.ok && dshMode) {
      dshMode.disabled = true
      dshMode.textContent = "DeepSeek Harness (not running)"
    }
  } catch (_) {
    if (dshMode) {
      dshMode.disabled = true
      dshMode.textContent = "DeepSeek Harness (not running)"
    }
  }
}

async function loadConversations() {
  const { data } = await api("GET", "/api/ai/conversations");
  const select = $("#ai-chat-conversation");
  select.innerHTML = '<option value="new">New conversation</option>';
  
  if (!(data || []).length) return;
  
  data.forEach((conv) => {
    const opt = document.createElement("option");
    opt.value = conv.id;
    opt.textContent = conv.title || "Chat " + conv.id;
    select.appendChild(opt);
  });
}

async function loadTools() {
  const { data } = await api("GET", "/api/ai/providers");
  const { data: toolsData } = await api("GET", "/api/catalog");
  availableTools = toolsData.tools || [];
  renderToolsStrip();
}

async function loadSkills() {
  const { data } = await api("GET", "/api/skills");
  availableSkills = data.skills || [];
}

function renderToolsStrip() {
  const strip = $("#ai-chat-tools-strip");
  strip.innerHTML = "";
  
  const tools = availableTools.slice(0, 10);
  tools.forEach((tool) => {
    const chip = document.createElement("span");
    chip.className = "chip";
    chip.textContent = tool.name;
    chip.title = tool.summary;
    chip.addEventListener("click", () => {
      const input = $("#ai-chat-input");
      input.value += "@" + tool.name + " ";
      input.focus();
    });
    strip.appendChild(chip);
  });
}

function wireAiChat() {
  const modeSelect = $("#ai-chat-mode");
  const input = $("#ai-chat-input");
  const sendBtn = $("#ai-chat-send");
  const newBtn = $("#ai-chat-new");
  const deleteBtn = $("#ai-chat-delete");
  const exportBtn = $("#ai-chat-export");
  const select = $("#ai-chat-conversation");
  const log = $("#ai-chat-log");
  const beginnerToggle = $("#ai-chat-beginner");
  const nativeView = $("#ai-chat-native-view");
  const opencodeView = $("#ai-chat-opencode-view");
  const dshView = $("#ai-chat-dsh-view");

  modeSelect.addEventListener("change", () => {
    const mode = modeSelect.value;
    if (mode === "native") {
      nativeView.classList.remove("hidden");
      opencodeView.classList.add("hidden");
      dshView.classList.add("hidden");
    } else if (mode === "opencode") {
      nativeView.classList.add("hidden");
      opencodeView.classList.remove("hidden");
      dshView.classList.add("hidden");
    } else if (mode === "dsh") {
      nativeView.classList.add("hidden");
      opencodeView.classList.add("hidden");
      dshView.classList.remove("hidden");
    }
  });

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendAiMessage();
    }
  });

  sendBtn.addEventListener("click", sendAiMessage);
  newBtn.addEventListener("click", newConversation);
  deleteBtn.addEventListener("click", deleteConversation);
  exportBtn.addEventListener("click", exportChat);
  select.addEventListener("change", selectConversation);
  
  document.getElementById("ai-chat-stop")?.addEventListener("click", () => {
    if (abortController) abortController.abort();
  });
}

async function sendAiMessage() {
  const input = $("#ai-chat-input");
  const text = input.value.trim();
  if (!text) return;
  
  input.value = "";
  input.disabled = true;
  input.placeholder = "Sending...";
  
  addUserMessage(text);
  
  const payload = {
    messages: [
      { role: "user", content: text }
    ],
    conversation_id: currentConversationId,
    beginner: $("#ai-chat-beginner").checked
  };
  
  abortController = new AbortController();
  
  try {
    const { data } = await api("POST", "/api/ai/chat", payload, { signal: abortController.signal });
    
    if (data.type === "error") {
      addSystemMessage("ERROR: " + (data.text || "Unknown error"), true);
    } else if (data.type === "action" && data.tool) {
      showToolConfirmCard(data.tool, data.payload || {});
    } else if (data.type === "message") {
      addAiMessage(data.text);
    }
  } catch (e) {
    if (e.name !== "AbortError") {
      addSystemMessage("ERROR: " + e.message, true);
    }
  } finally {
    input.disabled = false;
    input.placeholder = "Ask about security tools, techniques, or investigations...";
    input.focus();
    abortController = null;
  }
}

function addUserMessage(text) {
  const div = document.createElement("div");
  div.className = "msg user";
  div.textContent = text;
  $("#ai-chat-log").appendChild(div);
  scrollToBottom();
}

function addAiMessage(text) {
  const div = document.createElement("div");
  div.className = "msg assistant";
  div.innerHTML = renderMarkdown(text);
  $("#ai-chat-log").appendChild(div);
  scrollToBottom();
}

function addSystemMessage(text, isError = false) {
  const div = document.createElement("div");
  div.className = "msg system" + (isError ? " error" : "");
  div.textContent = text;
  $("#ai-chat-log").appendChild(div);
  scrollToBottom();
}

function showToolConfirmCard(toolId, payload) {
  const log = $("#ai-chat-log");
  const card = document.createElement("div");
  card.className = "tool-proposal";
  card.innerHTML = "<strong>Proposed tool run:</strong> " + toolId + 
    "<pre>" + JSON.stringify(payload, null, 2) + "</pre>" +
    '<div class="actions">' +
    '<button class="primary" data-act="run">Confirm and run</button>' +
    '<button class="ghost" data-act="cancel">Cancel</button></div>';
  
  card.querySelector('[data-act="run"]').addEventListener("click", async () => {
    card.remove();
    addUserMessage("Confirmed: run " + toolId);
    
    const { data } = await api("POST", "/api/tool/" + encodeURIComponent(toolId), payload);
    
    let resultText;
    if (!data || data.error) {
      resultText = "ERROR: " + ((data && data.error) || "unknown error") +
        ((data && data.detail) ? "\n" + data.detail : "");
    } else {
      const argv = data.argv ? data.argv.join(" ") : "...";
      const rc = data.rc != null ? data.rc : (data.returncode != null ? data.returncode : "?");
      resultText = "$ " + argv + "\n(exit " + rc + ")" +
        (data.stdout ? "\n\n" + data.stdout : "") +
        (data.stderr ? "\n[stderr]\n" + data.stderr : "") +
        (data.truncated ? "\n\n[output truncated]" : "");
    }
    
    if (resultText.length > 2000) resultText = resultText.slice(0, 2000) + "\n\n[truncated]";
    
    const resultCard = document.createElement("div");
    resultCard.className = "tool-result";
    resultCard.innerHTML = 
      '<span class="badge tool-badge">✓ ' + toolId + '</span>' +
      '<pre>' + escapeHtml(resultText) + '</pre>';
    $("#ai-chat-log").appendChild(resultCard);
    scrollToBottom();
    
    addSystemMessage("[ran " + toolId + "]\n" + resultText);
  });
  
  card.querySelector('[data-act="cancel"]').addEventListener("click", () => {
    card.remove();
    addSystemMessage("(action cancelled)");
  });
  
  log.appendChild(card);
  scrollToBottom();
}

function newConversation() {
  currentConversationId = null;
  $("#ai-chat-conversation").value = "new";
  $("#ai-chat-input").value = "";
  $("#ai-chat-log").innerHTML = "";
  $("#ai-chat-delete").disabled = true;
}

async function selectConversation() {
  const select = $("#ai-chat-conversation");
  const id = select.value;
  
  if (id === "new") {
    newConversation();
    return;
  }
  
  const { data } = await api("GET", "/api/ai/conversations/" + id);
  currentConversationId = id;
  
  const { data: messages } = await api("GET", "/api/ai/conversations/" + id + "/messages");
  const log = $("#ai-chat-log");
  log.innerHTML = "";
  
  messages.forEach((msg) => {
    if (msg.role === "user") {
      addUserMessage(msg.content);
    } else if (msg.role === "assistant") {
      addAiMessage(msg.content);
    } else if (msg.role === "system") {
      addSystemMessage(msg.content);
    }
  });
  
  $("#ai-chat-delete").disabled = false;
}

async function deleteConversation() {
  if (!currentConversationId) return;
  if (!confirm("Delete this conversation?")) return;
  
  await api("DELETE", "/api/ai/conversations/" + currentConversationId);
  await loadConversations();
  newConversation();
}

async function exportChat() {
  if (!currentConversationId) {
    toast("No conversation to export", true);
    return;
  }
  
  const { data } = await api("GET", "/api/ai/conversations/" + currentConversationId + "/export");
  const blob = new Blob([data.markdown], { type: "text/markdown" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "kws-chat-" + currentConversationId + ".md";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function renderMarkdown(text) {
  let html = escapeHtml(text);
  
  html = html.replace(/```(\w*)\n([\s\S]*?)\n```/g, (_, lang, code) => {
    return "<pre class=\"code-block\"><code class=\"" + lang + "\">" + escapeHtml(code) + "</code></pre>";
  });
  
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  
  html = html.replace(/^\s*[-*]\s+(.+)$/gm, "<li>$1</li>");
  html = html.replace(/<li>(.*?)<\/li>/g, "<ul><li>$1</li></ul>");
  
  html = html.replace(/https?:\/\/[^\s]+/g, "<a href='$&' target='_blank' rel='noopener'>$&</a>");
  
  return html;
}

function escapeHtml(text) {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function scrollToBottom() {
  const log = $("#ai-chat-log");
  log.scrollTop = log.scrollHeight;
}

/* toast, api, $, $$ provided globally by utils.js */

function wire() {
  window.addEventListener("resize", scrollToBottom);
}

wire();
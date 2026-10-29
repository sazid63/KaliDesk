/* 
 * Kali Linux Windows Substitute - Achievements Panel
 */

let achievements = [];

async function initAchievements() {
  await loadAchievements();
  wireAchievements();
}

async function loadAchievements() {
  const { data } = await api("GET", "/api/achievements");
  if (!data) return;
  achievements = data;
  renderAchievements();
}

function renderAchievements() {
  const grid = $("#achievements-grid");
  grid.innerHTML = "";
  
  if (!achievements.length) {
    grid.innerHTML = '<p class="muted">No achievements yet.</p>';
    return;
  }
  
  achievements.forEach((ach) => {
    const card = document.createElement("div");
    card.className = "card achievement" + (ach.unlocked ? " unlocked" : "");
    
    const badge = document.createElement("span");
    badge.className = "achievement-badge";
    badge.textContent = ach.unlocked ? "✓" : "○";
    card.appendChild(badge);
    
    const info = document.createElement("div");
    info.className = "achievement-info";
    info.innerHTML =
      '<h4>' + esc(ach.name) + '</h4>' +
      '<p>' + esc(ach.description) + '</p>';
    card.appendChild(info);
    
    card.addEventListener("click", () => {
      if (!ach.unlocked) {
        unlockAchievement(ach.key);
      }
    });
    
    grid.appendChild(card);
  });
}

async function unlockAchievement(key) {
  const { data } = await api("POST", "/api/achievements/" + key + "/unlock");
  toast(data.message || "Achievement unlocked", false);
  loadAchievements();
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
  $("#achievements-reload").addEventListener("click", loadAchievements);
}

wire();
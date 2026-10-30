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
  if (!data || !data.achievements) return;
  achievements = data.achievements;
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

/* $, $$, esc, toast, api provided globally by utils.js */

function wire() {
  $("#achievements-reload").addEventListener("click", loadAchievements);
}

wire();
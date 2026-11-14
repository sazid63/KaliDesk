(function () {
"use strict";
/* Achievements: progress is computed on the server from your run history. */

let achievements = [];

async function initAchievements() {
  await loadAchievements();
}

async function loadAchievements() {
  const { data } = await api("GET", "/api/achievements");
  achievements = (data && data.achievements) || [];
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
    badge.setAttribute("aria-hidden", "true");
    card.appendChild(badge);

    const info = document.createElement("div");
    info.className = "achievement-info";
    const title = document.createElement("h4");
    title.textContent = ach.name;
    const text = document.createElement("p");
    text.textContent = ach.description;
    const progress = document.createElement("p");
    progress.className = "muted";
    progress.textContent = ach.unlocked
      ? "Unlocked" + (ach.unlocked_at ? " " + ach.unlocked_at : "")
      : ach.progress + " / " + ach.goal;
    info.append(title, text, progress);
    card.appendChild(info);
    grid.appendChild(card);
  });
}

function wireAchievements() {
  $("#achievements-reload").addEventListener("click", loadAchievements);
}

wireAchievements();

window.initAchievements = initAchievements;
})();

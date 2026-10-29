/*
 * Kali Linux Windows Substitute - Onboarding Wizard Panel
 */

const STEPS = [
  {
    title: "Welcome to Kali Windows Substitute",
    body: "This is a Kali-style workbench for Windows. It runs real Linux security tools inside a private WSL2 runtime. You can install tools on demand, record findings, and export reports."
  },
  {
    title: "Tool Manager",
    body: "Use the Tool Manager tab to install or uninstall tools. Each tool shows its prerequisites and usage. Tools are installed only inside the WSL2 runtime, not on Windows."
  },
  {
    title: "Findings & Audit",
    body: "Record your findings as you test. Each finding includes severity, tool, target, and details. The Audit log tracks every tool run, install, and removal."
  },
  {
    title: "AI Assistance",
    body: "The AI chat can explain tool output and propose commands. It never runs anything without your confirmation. Configure providers in AI Settings."
  },
  {
    title: "Containers (Advanced)",
    body: "Run vulnerable apps in Podman containers for safe testing. Containers are isolated in WSL2. Never run privileged containers."
  },
  {
    title: "Ready to Start",
    body: "You're all set! Start by installing a tool from the Tool Manager, or explore the other tabs. Remember: only test systems you own or are authorized to test."
  }
];

let currentStep = 0;

async function initOnboarding() {
  await loadStatus();
  showStep(0);
  wireOnboarding();
}

async function loadStatus() {
  const { data } = await api("GET", "/api/onboarding/status");
  if (data && data.completed) {
    currentStep = STEPS.length - 1;
  }
}

function showStep(index) {
  currentStep = index;
  const step = STEPS[index];
  $("#onboarding-title").textContent = step.title;
  $("#onboarding-body").textContent = step.body;

  const progress = ((index + 1) / STEPS.length) * 100;
  $("#onboarding-progress").style.width = progress + "%";

  $("#onboarding-prev").disabled = index === 0;
  $("#onboarding-next").textContent = index === STEPS.length - 1 ? "Finish" : "Next";
}

async function nextStep() {
  if (currentStep < STEPS.length - 1) {
    showStep(currentStep + 1);
  } else {
    await finishWizard();
  }
}

async function prevStep() {
  if (currentStep > 0) {
    showStep(currentStep - 1);
  }
}

async function finishWizard() {
  const { data } = await api("POST", "/api/onboarding/finish");
  toast(data.message || "Onboarding complete!");
  // Navigate to home panel
  const homeLink = Array.from(document.querySelectorAll("[data-view]")).find(el => el.dataset.view === "home");
  if (homeLink) homeLink.click();
}

async function skipWizard() {
  // Navigate to home panel
  const homeLink = Array.from(document.querySelectorAll("[data-view]")).find(el => el.dataset.view === "home");
  if (homeLink) homeLink.click();
}

function wireOnboarding() {
  const prevBtn = $("#onboarding-prev");
  const nextBtn = $("#onboarding-next");
  const skipBtn = $("#onboarding-skip");
  if (prevBtn) prevBtn.addEventListener("click", prevStep);
  if (nextBtn) nextBtn.addEventListener("click", nextStep);
  if (skipBtn) skipBtn.addEventListener("click", skipWizard);
}
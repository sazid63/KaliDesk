(function () {
"use strict";
/* First-run guide. Each step reflects the real state of the app, not just text. */

let step = 0;
let accepted = false;
let timer = null;
// Bumped on every step change or panel exit; async work from an older generation stops quietly.
let gen = 0;
let lastRuntimeStart = 0;

const STEPS = ["welcome", "runtime", "tool", "try", "done"];

function el(tag, text, cls) {
  const node = document.createElement(tag);
  if (text) node.textContent = text;
  if (cls) node.className = cls;
  return node;
}

function button(label, handler, cls) {
  const b = el("button", label, cls || "primary");
  b.type = "button";
  b.addEventListener("click", handler);
  return b;
}

async function runtimeState() {
  const { data } = await api("GET", "/api/runtime", undefined, { timeout: 30000 });
  const s = data || {};
  // Start the agent only when it is installed but down, nothing is provisioning, and at most once per 60 s.
  const provisioning = !!(s.provisioning && !s.provisioning.done);
  if (s.installed && !s.agent && !provisioning && Date.now() - lastRuntimeStart >= 60000) {
    lastRuntimeStart = Date.now();
    api("POST", "/api/runtime/start", {});
  }
  return s;
}

async function installedState(id) {
  const { data } = await api("GET", "/api/tools/manage");
  if (!data || !data.online) return null;
  const row = (data.tools || []).find((t) => t.id === id);
  return row ? row.present : null;
}

async function render() {
  clearTimeout(timer);
  const myGen = ++gen;
  const box = $("#onboarding-content");
  box.textContent = "";
  $("#onboarding-progress-bar").style.width = ((step + 1) / STEPS.length) * 100 + "%";
  const next = $("#onboarding-next");
  const prev = $("#onboarding-prev");
  prev.disabled = step === 0;
  next.disabled = false;
  next.textContent = step === STEPS.length - 1 ? "Finish" : "Next";

  const name = STEPS[step];
  if (name === "welcome") {
    box.append(
      el("h3", "Welcome"),
      el("p", "This is a Kali-style workbench for Windows. The real Linux tools run in a private WSL2 " +
        "runtime that this app owns; nothing is installed on Windows itself."),
      el("p", "These tools can harm systems and break laws if misused. Use them only on systems you " +
        "own or have written permission to test.", "warning"),
    );
    const label = el("label", "", "check");
    const box1 = document.createElement("input");
    box1.type = "checkbox";
    box1.checked = accepted;
    box1.addEventListener("change", () => { accepted = box1.checked; next.disabled = !accepted; });
    label.append(box1, el("span", "I will only test systems I own or am authorised to test."));
    box.appendChild(label);
    next.disabled = !accepted;
  } else if (name === "runtime") {
    const status = el("p", "Checking the runtime…", "muted");
    box.append(el("h3", "Set up the runtime"), status);
    const act = el("div", "", "actions");
    box.appendChild(act);
    const refresh = async () => {
      clearTimeout(timer);
      const s = await runtimeState();
      if (myGen !== gen) return; // the user left this step or the panel while the request was in flight
      const prov = s.provisioning;
      act.textContent = "";
      if (s.agent) {
        status.textContent = "The runtime is online. You can continue.";
        next.disabled = false;
        return;
      }
      next.disabled = true;
      if (prov && !prov.done) {
        status.textContent = provisionText(prov);
        timer = setTimeout(refresh, 2000);
      } else if (!s.wsl) {
        status.textContent = s.message;
        act.appendChild(button("Check again", refresh, "ghost"));
      } else {
        status.textContent = (prov && prov.error) ? prov.message : s.message;
        act.appendChild(button(prov && prov.error ? "Try again" : "Set up runtime", async () => {
          const mine = gen;
          await ensureRuntime();
          if (mine === gen) refresh();
        }));
        if (s.installed) timer = setTimeout(refresh, 4000);
      }
    };
    refresh();
  } else if (name === "tool") {
    const status = el("p", "Checking…", "muted");
    box.append(el("h3", "Install your first tool"),
      el("p", "Nmap finds the devices and open ports on a network. It is already part of the runtime " +
        "image; if it is missing you can install it here."), status);
    const act = el("div", "", "actions");
    box.appendChild(act);
    const refresh = async () => {
      const present = await installedState("nmap");
      if (myGen !== gen) return;
      act.textContent = "";
      if (present === true) {
        status.textContent = "Nmap is installed.";
      } else if (present === false) {
        status.textContent = "Nmap is not installed yet.";
        act.appendChild(button("Install Nmap", async () => { await installTool("nmap"); if (myGen === gen) refresh(); }));
      } else {
        status.textContent = "The runtime is not reachable yet - go back one step.";
      }
    };
    refresh();
  } else if (name === "try") {
    box.append(el("h3", "Try it"),
      el("p", "Scan your own computer (127.0.0.1). It is always allowed, and it shows how a run, its " +
        "live output and the Stop button work."));
    const act = el("div", "", "actions");
    act.appendChild(button("Open Nmap with 127.0.0.1", async () => {
      showPanel("home");
      await openTool("nmap");
      const target = document.getElementById("f-target");
      if (target) target.value = "127.0.0.1";
    }));
    box.appendChild(act);
  } else {
    box.append(el("h3", "You are set"),
      el("p", "Pick a tool from the home screen. Findings, History and Run transcripts keep your " +
        "results. The AI assistant is optional: set it up in Settings."));
  }
}

async function finish() {
  clearTimeout(timer);
  gen++;
  const { ok, data } = await api("POST", "/api/onboarding/finish", { accepted });
  if (!ok) { toast(data.error || "could not finish", true); return; }
  toast("All set");
  showPanel("home");
}

function wire() {
  $("#onboarding-prev").addEventListener("click", () => { if (step > 0) { step--; render(); } });
  $("#onboarding-next").addEventListener("click", () => {
    if (step < STEPS.length - 1) { step++; render(); } else { finish(); }
  });
  $("#onboarding-skip").addEventListener("click", () => {
    clearTimeout(timer); gen++;
    // Remember the choice so the guide does not open by itself next time. It stays in the Views list.
    api("POST", "/api/onboarding/skip", {});
    showPanel("home");
  });
}

wire();

async function initOnboarding() {
  step = 0;
  render();
}

window.initOnboarding = initOnboarding;
})();

/*
 * Kali Linux Windows Substitute - Portable Mode Panel
 */

let availableDrives = [];

async function initPortable() {
  await detectDrives();
  wirePortable();
}

async function detectDrives() {
  const { data } = await api("GET", "/api/portable/drives");
  availableDrives = data.drives || [];
  renderDrives();
}

function renderDrives() {
  const select = $("#portable-drive-select");
  const status = $("#portable-status");
  select.innerHTML = '<option value="">— Select USB drive —</option>';

  if (!availableDrives.length) {
    status.textContent = "No USB drives detected. Insert a USB drive and click Refresh.";
    status.classList.add("error");
    return;
  }

  status.textContent = availableDrives.length + " drive(s) detected.";
  status.classList.remove("error");

  availableDrives.forEach((drive) => {
    const opt = document.createElement("option");
    opt.value = drive.path;
    opt.textContent = drive.label + " (" + drive.path + ") - " + drive.free_gb + "GB free";
    select.appendChild(opt);
  });
}

async function switchToUsb() {
  const path = $("#portable-drive-select").value;
  if (!path) {
    toast("Select a USB drive first", true);
    return;
  }

  if (!confirm("Switch to portable mode? This will move your data to " + path + ". The app will restart.")) {
    return;
  }

  const { data } = await api("POST", "/api/portable/switch", { path });
  if (data.ok) {
    toast("Switching to portable mode...");
    setTimeout(() => {
      window.location.reload();
    }, 2000);
  } else {
    toast(data.error || "Failed to switch", true);
  }
}

function wirePortable() {
  const refreshBtn = $("#portable-refresh-drives");
  const switchBtn = $("#portable-switch");
  if (refreshBtn) refreshBtn.addEventListener("click", detectDrives);
  if (switchBtn) switchBtn.addEventListener("click", switchToUsb);
}
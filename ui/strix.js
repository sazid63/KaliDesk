/* Strix UI Logic */

function strixRefresh() {
    api("GET", "/api/strix/status").then(r => {
        const installed = r.data.installed;
        const running = r.data.running;
        const pid = r.data.pid;
        const url = r.data.url;
        
        document.getElementById("strix-dot").className = "dot " +
            (running ? "green" : installed ? "yellow" : "red");
        document.getElementById("strix-text").textContent = 
            running ? "Running" : installed ? "Installed" : "Not installed";
        
        document.getElementById("strix-install").disabled = installed;
        document.getElementById("strix-start").disabled = !installed || running;
        document.getElementById("strix-stop").disabled = !running;
        
        const iframe = document.getElementById("strix-iframe");
        const log = document.getElementById("strix-log");
        if (running && url) {
            iframe.src = url;
            iframe.classList.remove("hidden");
            log.classList.add("hidden");
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
    document.getElementById("strix-install").disabled = true;
    document.getElementById("strix-text").textContent = "Installing...";
    api("POST", "/api/strix/install").then(r => {
        if (r.data.ok) {
            // Poll until installed
            const check = setInterval(() => {
                api("GET", "/api/strix/status").then(r2 => {
                    if (r2.data.installed) {
                        clearInterval(check);
                        strixRefresh();
                    }
                });
            }, 2000);
        } else {
            showToast("Install failed: " + r.data.message);
            document.getElementById("strix-install").disabled = false;
            strixRefresh();
        }
    }).catch(e => {
        showToast("Install failed: " + e);
        document.getElementById("strix-install").disabled = false;
        strixRefresh();
    });
}

function strixStart() {
    document.getElementById("strix-start").disabled = true;
    document.getElementById("strix-text").textContent = "Starting...";
    api("POST", "/api/strix/start").then(r => {
        if (r.data.ok) {
            // Poll until running
            const check = setInterval(() => {
                api("GET", "/api/strix/status").then(r2 => {
                    if (r2.data.running) {
                        clearInterval(check);
                        strixRefresh();
                    }
                });
            }, 2000);
        } else {
            showToast("Start failed: " + r.data.message);
            document.getElementById("strix-start").disabled = false;
            strixRefresh();
        }
    }).catch(e => {
        showToast("Start failed: " + e);
        document.getElementById("strix-start").disabled = false;
        strixRefresh();
    });
}

function strixStop() {
    document.getElementById("strix-stop").disabled = true;
    document.getElementById("strix-text").textContent = "Stopping...";
    api("POST", "/api/strix/stop").then(r => {
        if (r.data.ok) {
            strixRefresh();
        } else {
            showToast("Stop failed: " + r.data.message);
            document.getElementById("strix-stop").disabled = false;
            strixRefresh();
        }
    }).catch(e => {
        showToast("Stop failed: " + e);
        document.getElementById("strix-stop").disabled = false;
        strixRefresh();
    });
}

function strixInfo() {
    const tooltip = document.getElementById("strix-tooltip");
    tooltip.classList.toggle("hidden");
}

document.addEventListener("DOMContentLoaded", () => {
    document.getElementById("strix-install").onclick = strixInstall;
    document.getElementById("strix-start").onclick = strixStart;
    document.getElementById("strix-stop").onclick = strixStop;
    document.getElementById("strix-refresh").onclick = strixRefresh;
    document.getElementById("strix-info").onclick = strixInfo;
    
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

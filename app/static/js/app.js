/**
 * 🍅 TomateCP Frontend Engine
 * Real-time hardware telemetry, async Nginx controls, and modal dialogs.
 */

document.addEventListener("DOMContentLoaded", () => {
    // Check if on dashboard page to start polling
    if (document.getElementById("dashboard-root")) {
        startTelemetryPolling();
    }

    // Check if on logs page
    if (document.getElementById("log-content")) {
        startLogViewer();
    }

    // Global ESC key listener for modals
    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape") {
            closeAllModals();
        }
    });

    // Close on overlay backdrop click
    document.querySelectorAll(".modal-overlay").forEach(overlay => {
        overlay.addEventListener("click", (e) => {
            if (e.target === overlay) {
                overlay.classList.remove("active");
            }
        });
    });
});

/**
 * Real-time hardware telemetry poller (2.5s interval)
 */
function startTelemetryPolling() {
    async function updateStats() {
        try {
            const res = await fetch("/api/system/stats");
            if (!res.ok) return;
            const data = await res.json();

            // CPU Temp
            const tempValEl = document.getElementById("metric-temp-val");
            const tempBadgeEl = document.getElementById("metric-temp-badge");
            if (tempValEl && data.cpu_temp !== null) {
                tempValEl.innerText = `${data.cpu_temp}°C`;
                if (tempBadgeEl) {
                    tempBadgeEl.className = "badge";
                    if (data.temp_status === "critical") {
                        tempBadgeEl.classList.add("badge-danger");
                        tempBadgeEl.innerText = "Crítico";
                    } else if (data.temp_status === "warning") {
                        tempBadgeEl.classList.add("badge-warning");
                        tempBadgeEl.innerText = "Atenção";
                    } else {
                        tempBadgeEl.classList.add("badge-success");
                        tempBadgeEl.innerText = "Normal";
                    }
                }
            } else if (tempValEl) {
                tempValEl.innerText = "N/A";
            }

            // CPU Percent
            const cpuValEl = document.getElementById("metric-cpu-val");
            const cpuBarEl = document.getElementById("metric-cpu-bar");
            if (cpuValEl) cpuValEl.innerText = `${data.cpu_percent}%`;
            if (cpuBarEl) {
                cpuBarEl.style.width = `${data.cpu_percent}%`;
                cpuBarEl.className = "progress-bar-fill " + (data.cpu_percent > 80 ? "danger" : data.cpu_percent > 50 ? "warning" : "success");
            }

            // Load Average
            const loadValEl = document.getElementById("metric-load-val");
            if (loadValEl && data.load_avg) {
                loadValEl.innerText = `${data.load_avg.load1} / ${data.load_avg.load5} / ${data.load_avg.load15}`;
            }

            // RAM Memory
            const ramValEl = document.getElementById("metric-ram-val");
            const ramSubEl = document.getElementById("metric-ram-sub");
            const ramBarEl = document.getElementById("metric-ram-bar");
            if (ramValEl && data.memory) {
                ramValEl.innerText = `${data.memory.ram_percent}%`;
                if (ramSubEl) ramSubEl.innerText = `${data.memory.ram_used_mb} MB de ${data.memory.ram_total_mb} MB`;
                if (ramBarEl) {
                    ramBarEl.style.width = `${data.memory.ram_percent}%`;
                    ramBarEl.className = "progress-bar-fill " + (data.memory.ram_percent > 85 ? "danger" : data.memory.ram_percent > 65 ? "warning" : "success");
                }
            }

            // Swap / zRAM
            const swapValEl = document.getElementById("metric-swap-val");
            const swapSubEl = document.getElementById("metric-swap-sub");
            const swapBarEl = document.getElementById("metric-swap-bar");
            if (swapValEl && data.memory) {
                swapValEl.innerText = `${data.memory.swap_percent}%`;
                if (swapSubEl) swapSubEl.innerText = `${data.memory.swap_used_mb} MB de ${data.memory.swap_total_mb} MB`;
                if (swapBarEl) {
                    swapBarEl.style.width = `${data.memory.swap_percent}%`;
                }
            }

            // Disk Storage
            const diskValEl = document.getElementById("metric-disk-val");
            const diskSubEl = document.getElementById("metric-disk-sub");
            const diskBarEl = document.getElementById("metric-disk-bar");
            if (diskValEl && data.disk) {
                diskValEl.innerText = `${data.disk.disk_percent}%`;
                if (diskSubEl) diskSubEl.innerText = `${data.disk.disk_used_gb} GB de ${data.disk.disk_total_gb} GB`;
                if (diskBarEl) diskBarEl.style.width = `${data.disk.disk_percent}%`;
            }

            // Uptime
            const uptimeEl = document.getElementById("metric-uptime");
            if (uptimeEl) uptimeEl.innerText = data.uptime;

        } catch (e) {
            console.warn("Telemetry poll error:", e);
        }
    }

    // Initial update + timer
    updateStats();
    setInterval(updateStats, 2500);
}

/**
 * Toggle site activation status
 */
async function handleSiteToggle(domain, checkbox) {
    const isChecked = checkbox.checked;
    const originalState = !isChecked;

    try {
        const formData = new FormData();
        formData.append("domain", domain);
        formData.append("enable", isChecked);

        const res = await fetch("/api/sites/toggle", {
            method: "POST",
            body: formData,
        });

        const data = await res.json();
        if (data.success) {
            showToast(data.message, "success");
            // Update UI badge
            const badge = document.getElementById(`status-badge-${domain}`);
            if (badge) {
                if (isChecked) {
                    badge.className = "badge badge-success";
                    badge.innerText = "Ativo";
                } else {
                    badge.className = "badge badge-neutral";
                    badge.innerText = "Pausado";
                }
            }
        } else {
            showToast(data.message || "Erro ao alterar estado.", "danger");
            checkbox.checked = originalState;
        }
    } catch (e) {
        showToast("Erro de comunicação com o servidor.", "danger");
        checkbox.checked = originalState;
    }
}

/**
 * Nginx safe reload button
 */
async function triggerNginxReload() {
    showToast("Validando e recarregando Nginx...", "neutral");
    try {
        const res = await fetch("/api/system/nginx-reload", { method: "POST" });
        const data = await res.json();
        if (data.success) {
            showToast(data.message, "success");
        } else {
            showToast(data.message, "danger");
        }
    } catch (e) {
        showToast("Falha ao comunicar com o servidor.", "danger");
    }
}

/**
 * Log viewer polling
 */
function startLogViewer() {
    const logEl = document.getElementById("log-content");
    const autoRefreshCb = document.getElementById("auto-refresh-logs");

    async function fetchLogs() {
        if (autoRefreshCb && !autoRefreshCb.checked) return;
        try {
            const type = document.getElementById("log-type")?.value || "access";
            const res = await fetch(`/api/logs?log_type=${type}&lines=80`);
            const data = await res.json();
            if (logEl) {
                logEl.innerText = data.logs;
                logEl.scrollTop = logEl.scrollHeight;
            }
        } catch (e) {
            console.error(e);
        }
    }

    fetchLogs();
    setInterval(fetchLogs, 3000);
}

/**
 * Modal Management
 */
function openModal(id) {
    const modal = document.getElementById(id);
    if (modal) modal.classList.add("active");
}

function closeModal(id) {
    const modal = document.getElementById(id);
    if (modal) modal.classList.remove("active");
}

function closeAllModals() {
    document.querySelectorAll(".modal-overlay").forEach(m => m.classList.remove("active"));
}

/**
 * Toast notifications
 */
function showToast(message, type = "success") {
    let container = document.getElementById("toast-container");
    if (!container) {
        container = document.createElement("div");
        container.id = "toast-container";
        container.style.cssText = "position: fixed; bottom: 24px; right: 24px; z-index: 9999; display: flex; flex-direction: column; gap: 8px;";
        document.body.appendChild(container);
    }

    const toast = document.createElement("div");
    const bg = type === "success" ? "#22C55E" : type === "danger" ? "#EF4444" : "#334155";
    toast.style.cssText = `background: #1E293B; border: 1px solid ${bg}; border-left: 4px solid ${bg}; color: #FFFFFF; padding: 12px 18px; border-radius: 8px; font-size: 13px; font-weight: 500; box-shadow: 0 10px 25px rgba(0,0,0,0.5); opacity: 0; transform: translateY(10px); transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);`;
    toast.innerText = message;

    container.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = "1";
        toast.style.transform = "translateY(0)";
    }, 10);

    setTimeout(() => {
        toast.style.opacity = "0";
        toast.style.transform = "translateY(10px)";
        setTimeout(() => toast.remove(), 250);
    }, 3500);
}

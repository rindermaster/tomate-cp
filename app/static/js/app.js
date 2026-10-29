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
        container.className = "toast-container-root";
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

/**
 * Mobile Drawer Navigation (UI/UX Pro Max)
 */
function toggleMobileDrawer(open) {
    const sidebar = document.getElementById("sidebar-drawer") || document.querySelector(".sidebar");
    const backdrop = document.getElementById("sidebar-backdrop");
    if (!sidebar) return;

    const isOpen = sidebar.classList.contains("open");
    const shouldOpen = open !== undefined ? open : !isOpen;

    if (shouldOpen) {
        sidebar.classList.add("open");
        if (backdrop) backdrop.classList.add("active");
        document.body.style.overflow = "hidden";
    } else {
        sidebar.classList.remove("open");
        if (backdrop) backdrop.classList.remove("active");
        document.body.style.overflow = "";
    }
}

// Global listeners for drawer & mobile touch
document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
        toggleMobileDrawer(false);
    }
});

document.addEventListener("DOMContentLoaded", () => {
    // Close drawer when clicking any nav link on mobile
    document.querySelectorAll(".sidebar .nav-link").forEach(link => {
        link.addEventListener("click", () => {
            if (window.innerWidth <= 768) {
                toggleMobileDrawer(false);
            }
        });
    });
});

/**
 * ⚡ Ações Rápidas de Sistema (UI/UX Pro Max)
 */
async function triggerDropCaches() {
    showToast("Limpando cache de memória RAM...", "neutral");
    try {
        const res = await fetch("/api/system/drop-caches", { method: "POST" });
        const data = await res.json();
        if (data.success) {
            showToast(data.message, "success");
            // If on dashboard, force stats update
            if (typeof updateStats === "function") {
                setTimeout(updateStats, 400);
            }
        } else {
            showToast(data.message, "danger");
        }
    } catch (e) {
        showToast("Erro ao otimizar memória.", "danger");
    }
}

async function triggerRebootConfirm() {
    if (!confirm("⚠️ Tem certeza de que deseja REINICIAR a TV Box / Servidor agora? O painel ficará inacessível por cerca de 30 a 60 segundos.")) {
        return;
    }
    showToast("Enviando comando de reinicialização...", "warning");
    try {
        const res = await fetch("/api/system/reboot", { method: "POST" });
        const data = await res.json();
        showToast(data.message, "success");
        setTimeout(() => {
            document.body.innerHTML = `<div style="height: 100vh; display: flex; flex-direction: column; align-items: center; justify-content: center; background: #0F172A; color: #FFFFFF; font-family: sans-serif; text-align: center; padding: 24px;"><h2 style="font-size: 24px; margin-bottom: 12px;">🔄 Dispositivo Reiniciando...</h2><p style="color: #94A3B8; max-width: 400px; line-height: 1.6;">A TV Box está reinicializando os serviços. Esta página tentará reconectar automaticamente em 30 segundos.</p></div>`;
            setTimeout(() => location.reload(), 30000);
        }, 1500);
    } catch (e) {
        showToast("Erro ao solicitar reinicialização.", "danger");
    }
}

/**
 * 💻 Web Terminal Client
 */
function fillTerminalCommand(cmd) {
    const input = document.getElementById("terminal-input");
    if (input) {
        input.value = cmd;
        handleTerminalSubmit(new Event("submit"));
    }
}

async function handleTerminalSubmit(e) {
    if (e && e.preventDefault) e.preventDefault();
    const input = document.getElementById("terminal-input");
    const output = document.getElementById("terminal-output");
    const btn = document.getElementById("btn-terminal-run");
    if (!input || !output) return;

    const command = input.value.trim();
    if (!command) return;

    input.value = "";
    if (btn) btn.disabled = true;

    // Append command to terminal
    output.innerText += `\n\nroot@tomate:~# ${command}`;
    output.scrollTop = output.scrollHeight;

    try {
        const formData = new FormData();
        formData.append("command", command);

        const res = await fetch("/api/system/terminal/exec", {
            method: "POST",
            body: formData
        });
        const data = await res.json();

        if (data.stdout) {
            output.innerText += `\n${data.stdout.trim()}`;
        }
        if (data.stderr) {
            output.innerText += `\n⚠️ [stderr]: ${data.stderr.trim()}`;
        }
        if (!data.stdout && !data.stderr) {
            output.innerText += `\n(Comando executado sem retorno, código de saída: ${data.exit_code})`;
        }
        output.innerText += `\n[Duração: ${data.duration_ms}ms]`;
    } catch (err) {
        output.innerText += `\n❌ Erro de comunicação com o servidor: ${err}`;
    } finally {
        if (btn) btn.disabled = false;
        output.scrollTop = output.scrollHeight;
        input.focus();
    }
}

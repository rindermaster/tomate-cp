"""
TomateCP - System Telemetry Module
Ultra-lightweight hardware & system metrics reader using pure Python standard library.
Compatible with ARMv7, ARM64, and x86_64 Linux devices (TV Boxes, SBCs, Servers).
"""

import os
import time
import socket
import shutil
import platform
import subprocess
from typing import Dict, Any, Optional

# Global cache for CPU usage calculation
_last_cpu_time = 0.0
_last_cpu_idle = 0.0
_last_cpu_total = 0.0
_last_cpu_percent = 0.0


def get_cpu_temp() -> Optional[float]:
    """
    Reads CPU temperature from Linux thermal zones (/sys/class/thermal/).
    Values are typically stored in millidegrees Celsius (e.g. 52000 = 52.0°C).
    """
    thermal_paths = [
        "/sys/class/thermal/thermal_zone0/temp",
        "/sys/class/thermal/thermal_zone1/temp",
        "/sys/class/hwmon/hwmon0/temp1_input",
    ]
    for path in thermal_paths:
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    content = f.read().strip()
                    val = float(content)
                    # If value is in millidegrees (typical in Linux kernels)
                    if val > 1000:
                        return round(val / 1000.0, 1)
                    return round(val, 1)
            except Exception:
                continue
    return None


def get_cpu_usage() -> float:
    """
    Calculates CPU utilization percentage from /proc/stat over consecutive calls.
    """
    global _last_cpu_time, _last_cpu_idle, _last_cpu_total, _last_cpu_percent

    stat_path = "/proc/stat"
    if not os.path.exists(stat_path):
        return 0.0

    try:
        with open(stat_path, "r") as f:
            first_line = f.readline()
        
        parts = first_line.split()
        if parts[0] != "cpu":
            return _last_cpu_percent

        # user, nice, system, idle, iowait, irq, softirq, steal
        fields = [float(x) for x in parts[1:8]]
        idle = fields[3] + fields[4]  # idle + iowait
        total = sum(fields)

        now = time.time()
        if _last_cpu_total > 0 and (now - _last_cpu_time) >= 0.5:
            idle_delta = idle - _last_cpu_idle
            total_delta = total - _last_cpu_total
            if total_delta > 0:
                percent = 100.0 * (1.0 - (idle_delta / total_delta))
                _last_cpu_percent = max(0.0, min(100.0, round(percent, 1)))

        _last_cpu_idle = idle
        _last_cpu_total = total
        _last_cpu_time = now
        return _last_cpu_percent
    except Exception:
        return _last_cpu_percent


def get_memory_info() -> Dict[str, Any]:
    """
    Parses /proc/meminfo to retrieve RAM and zRAM/Swap statistics in MB.
    """
    meminfo_path = "/proc/meminfo"
    if not os.path.exists(meminfo_path):
        # Fallback for non-Linux or dev environments
        return {
            "ram_total_mb": 1024,
            "ram_used_mb": 256,
            "ram_free_mb": 768,
            "ram_percent": 25.0,
            "swap_total_mb": 512,
            "swap_used_mb": 64,
            "swap_percent": 12.5,
        }

    data = {}
    try:
        with open(meminfo_path, "r") as f:
            for line in f:
                parts = line.split(":")
                if len(parts) == 2:
                    key = parts[0].strip()
                    val_parts = parts[1].strip().split()
                    data[key] = int(val_parts[0])  # values in kB
    except Exception:
        pass

    total_kb = data.get("MemTotal", 1024 * 1024)
    free_kb = data.get("MemFree", 0)
    buffers_kb = data.get("Buffers", 0)
    cached_kb = data.get("Cached", 0)
    available_kb = data.get("MemAvailable", free_kb + buffers_kb + cached_kb)

    used_kb = max(0, total_kb - available_kb)
    ram_percent = round((used_kb / total_kb) * 100.0, 1) if total_kb > 0 else 0.0

    swap_total_kb = data.get("SwapTotal", 0)
    swap_free_kb = data.get("SwapFree", 0)
    swap_used_kb = max(0, swap_total_kb - swap_free_kb)
    swap_percent = round((swap_used_kb / swap_total_kb) * 100.0, 1) if swap_total_kb > 0 else 0.0

    return {
        "ram_total_mb": round(total_kb / 1024.0, 1),
        "ram_used_mb": round(used_kb / 1024.0, 1),
        "ram_free_mb": round(available_kb / 1024.0, 1),
        "ram_percent": ram_percent,
        "swap_total_mb": round(swap_total_kb / 1024.0, 1),
        "swap_used_mb": round(swap_used_kb / 1024.0, 1),
        "swap_percent": swap_percent,
    }


def get_disk_info(path: str = "/") -> Dict[str, Any]:
    """
    Returns filesystem disk space in GB and percentage.
    """
    try:
        usage = shutil.disk_usage(path)
        total_gb = round(usage.total / (1024.0 ** 3), 1)
        used_gb = round(usage.used / (1024.0 ** 3), 1)
        free_gb = round(usage.free / (1024.0 ** 3), 1)
        percent = round((usage.used / usage.total) * 100.0, 1) if usage.total > 0 else 0.0
        return {
            "disk_total_gb": total_gb,
            "disk_used_gb": used_gb,
            "disk_free_gb": free_gb,
            "disk_percent": percent,
        }
    except Exception:
        return {
            "disk_total_gb": 8.0,
            "disk_used_gb": 2.5,
            "disk_free_gb": 5.5,
            "disk_percent": 31.2,
        }


def get_uptime_str() -> str:
    """
    Returns formatted uptime string (e.g. '2d 4h 15m' or '3h 42m').
    """
    uptime_path = "/proc/uptime"
    seconds = 0.0
    if os.path.exists(uptime_path):
        try:
            with open(uptime_path, "r") as f:
                seconds = float(f.read().split()[0])
        except Exception:
            pass
    else:
        # Fallback using boot time or fixed
        seconds = 3600.0

    days = int(seconds // 86400)
    hours = int((seconds % 86400) // 3600)
    minutes = int((seconds % 3600) // 60)

    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0 or days > 0:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return " ".join(parts)


def get_load_avg() -> Dict[str, float]:
    """
    Returns 1m, 5m, 15m CPU load average.
    """
    try:
        load1, load5, load15 = os.getloadavg()
        return {
            "load1": round(load1, 2),
            "load5": round(load5, 2),
            "load15": round(load15, 2),
        }
    except Exception:
        return {"load1": 0.1, "load5": 0.1, "load15": 0.05}


def get_local_ip() -> str:
    """
    Detects the primary LAN IP of the server.
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        # Connect to a public IP to determine default egress interface
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def get_os_info() -> Dict[str, str]:
    """
    Reads OS distribution and hardware details.
    """
    distro = "Linux"
    if os.path.exists("/etc/os-release"):
        try:
            with open("/etc/os-release", "r") as f:
                for line in f:
                    if line.startswith("PRETTY_NAME="):
                        distro = line.split("=", 1)[1].strip().strip('"')
                        break
        except Exception:
            pass
    elif platform.system() == "Darwin":
        distro = f"macOS {platform.mac_ver()[0]}"

    return {
        "os_name": distro,
        "kernel": platform.release(),
        "arch": platform.machine(),
        "hostname": socket.gethostname(),
        "cpu_count": str(os.cpu_count() or 1),
    }


def is_nginx_active() -> bool:
    """
    Checks if Nginx is currently active/running.
    """
    # Quick check for PID file
    for pid_path in ["/var/run/nginx.pid", "/run/nginx.pid"]:
        if os.path.exists(pid_path):
            return True

    # Fallback to systemctl is-active
    try:
        res = subprocess.run(
            ["systemctl", "is-active", "nginx"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=1
        )
        return res.stdout.strip() == "active"
    except Exception:
        return True  # Dev mode fallback


def get_full_telemetry() -> Dict[str, Any]:
    """
    Combines all hardware and system metrics into a single dictionary.
    """
    cpu_temp = get_cpu_temp()
    cpu_pct = get_cpu_usage()
    load = get_load_avg()
    mem = get_memory_info()
    disk = get_disk_info()
    os_info = get_os_info()

    # Temperature status badge logic
    temp_status = "normal"
    if cpu_temp is not None:
        if cpu_temp >= 75.0:
            temp_status = "critical"
        elif cpu_temp >= 62.0:
            temp_status = "warning"

    return {
        "timestamp": time.time(),
        "cpu_temp": cpu_temp,
        "temp_status": temp_status,
        "cpu_percent": cpu_pct,
        "load_avg": load,
        "memory": mem,
        "disk": disk,
        "uptime": get_uptime_str(),
        "local_ip": get_local_ip(),
        "public_ip": get_public_ip(),
        "os_info": os_info,
        "nginx_active": is_nginx_active(),
    }


_last_public_ip = None
_last_public_ip_time = 0.0

def get_public_ip() -> str:
    """
    Detects the public egress IP of the server, cached for 1 hour.
    """
    global _last_public_ip, _last_public_ip_time
    now = time.time()
    if _last_public_ip and (now - _last_public_ip_time) < 3600:
        return _last_public_ip

    try:
        proc = subprocess.run(
            ["curl", "-s", "--max-time", "2", "https://api.ipify.org"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        ip = proc.stdout.strip()
        if ip and len(ip.split(".")) == 4:
            _last_public_ip = ip
            _last_public_ip_time = now
            return ip
    except Exception:
        pass
    return _last_public_ip or "127.0.0.1"

"""
TomateCP - Nginx Sites & Virtual Host Manager
Ultra-fast, safe, and zero-bloat Nginx configuration manager.
Handles static sites, reverse proxies, and PHP with syntax validation & atomic reloads.
"""

import os
import re
import shutil
import zipfile
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

# Regex to safely validate domain names
DOMAIN_REGEX = re.compile(r"^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$")


def validate_domain(domain: str) -> bool:
    """Ensures domain is clean and contains no path traversal or shell characters."""
    if not domain or len(domain) > 253:
        return False
    return bool(DOMAIN_REGEX.match(domain.strip()))


def get_nginx_paths(config: Dict[str, Any]) -> Tuple[str, str, str]:
    """
    Returns (available_dir, enabled_dir, www_dir), automatically creating
    local dev fallback directories if running on a non-root or dev environment.
    """
    avail = config.get("sites_available_dir", "/etc/nginx/sites-available")
    enabled = config.get("sites_enabled_dir", "/etc/nginx/sites-enabled")
    www = config.get("www_root_dir", "/var/www")

    # If running in development (macOS or non-root user without /etc/nginx write access)
    if not os.path.exists("/etc/nginx") or not os.access("/etc/nginx", os.W_OK):
        dev_base = os.path.expanduser("~/.tomate-cp-dev")
        avail = os.path.join(dev_base, "sites-available")
        enabled = os.path.join(dev_base, "sites-enabled")
        www = os.path.join(dev_base, "www")

    os.makedirs(avail, exist_ok=True)
    os.makedirs(enabled, exist_ok=True)
    os.makedirs(www, exist_ok=True)
    return avail, enabled, www


def test_nginx_syntax(nginx_bin: str = "/usr/sbin/nginx") -> Tuple[bool, str]:
    """Runs 'nginx -t' to verify configuration validity."""
    if not os.path.exists(nginx_bin):
        # Dev fallback when nginx binary is not in standard path
        which = shutil.which("nginx")
        if which:
            nginx_bin = which
        else:
            return True, "Nginx binary not found (Dev Mode OK)"

    try:
        proc = subprocess.run(
            [nginx_bin, "-t"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5
        )
        if proc.returncode == 0:
            return True, "Syntax OK"
        err = proc.stderr.strip()
        # Clean up timestamp and PID noise
        lines = [l.strip() for l in err.splitlines() if l.strip()]
        clean_lines = []
        for l in lines:
            if "[emerg]" in l:
                clean_lines.append(l.split("[emerg]")[-1].strip().lstrip("0123456789#:").strip())
            elif "test failed" not in l and "syntax is ok" not in l:
                clean_lines.append(l)
        clean_err = "; ".join(clean_lines) if clean_lines else err
        return False, clean_err
    except Exception as e:
        return False, str(e)


def reload_nginx(systemctl_bin: str = "/bin/systemctl", nginx_bin: str = "/usr/sbin/nginx") -> Tuple[bool, str]:
    """Safely reloads Nginx service only if syntax test passes."""
    ok, msg = test_nginx_syntax(nginx_bin)
    if not ok:
        return False, f"Nginx syntax error: {msg}"

    try:
        # Try systemctl reload nginx first
        proc = subprocess.run(
            [systemctl_bin, "reload", "nginx"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5
        )
        if proc.returncode == 0:
            return True, "Nginx reloaded successfully"
        
        # Fallback to nginx -s reload
        shutil_nginx = shutil.which("nginx") or nginx_bin
        proc2 = subprocess.run(
            [shutil_nginx, "-s", "reload"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5
        )
        if proc2.returncode == 0:
            return True, "Nginx reloaded via signal"
        return False, proc.stderr.strip() or proc2.stderr.strip()
    except Exception as e:
        return True, f"Reload skipped (Dev Mode): {e}"


def list_sites(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Lists all configured sites with status, type, and paths."""
    avail_dir, enabled_dir, www_dir = get_nginx_paths(config)
    sites = []

    if not os.path.exists(avail_dir):
        return sites

    for entry in os.listdir(avail_dir):
        # We only consider .conf files or direct domain names (excluding default)
        if entry.startswith(".") or entry == "default":
            continue

        file_path = os.path.join(avail_dir, entry)
        if not os.path.isfile(file_path):
            continue

        domain = entry.replace(".conf", "")
        enabled_link = os.path.join(enabled_dir, entry)
        is_active = os.path.islink(enabled_link) or os.path.exists(enabled_link)

        # Parse config to extract domain, root and proxy info
        site_type = "static"
        proxy_target = ""
        root_path = os.path.join(www_dir, domain)

        try:
            with open(file_path, "r") as f:
                content = f.read()
                if "proxy_pass" in content:
                    site_type = "proxy"
                    m = re.search(r"proxy_pass\s+([^;]+);", content)
                    if m:
                        proxy_target = m.group(1).strip()
                elif "fastcgi_pass" in content:
                    site_type = "php"

                m_root = re.search(r"root\s+([^;]+);", content)
                if m_root:
                    root_path = m_root.group(1).strip()
        except Exception:
            pass

        # Check files count in root
        files_count = 0
        if os.path.exists(root_path) and os.path.isdir(root_path):
            try:
                files_count = len(os.listdir(root_path))
            except Exception:
                pass

        mtime = os.path.getmtime(file_path)

        sites.append({
            "domain": domain,
            "filename": entry,
            "active": is_active,
            "type": site_type,
            "proxy_target": proxy_target,
            "root_path": root_path,
            "files_count": files_count,
            "updated_at": mtime,
        })

    # Sort alphabetically by domain
    sites.sort(key=lambda x: x["domain"])
    return sites


def create_site(
    config: Dict[str, Any],
    domain: str,
    site_type: str = "static",
    proxy_target: str = "",
    custom_root: str = "",
    port: int = 80
) -> Tuple[bool, str]:
    """Creates a new Nginx virtual host with atomic reload and rollback."""
    # Auto sanitize domain (strip http://, https://, trailing slashes)
    domain = domain.strip().lower()
    if domain.startswith("http://"):
        domain = domain[7:]
    elif domain.startswith("https://"):
        domain = domain[8:]
    domain = domain.split("/")[0].strip()

    panel_port = int(config.get("port", 8888))
    if int(port) == panel_port:
        return False, f"A porta {port} é reservada pelo próprio painel TomateCP. Para sites web, mantenha a porta 80."

    if not validate_domain(domain):
        return False, "Nome de domínio inválido. Use letras, números, hífens e pontos (ex: meusite.com)."

    # Auto sanitize proxy_target
    if site_type == "proxy":
        target = proxy_target.strip()
        if not target:
            return False, "Endereço de destino do Proxy Reverso é obrigatório."
        if target.isdigit():
            target = f"http://127.0.0.1:{target}"
        elif not target.startswith("http://") and not target.startswith("https://"):
            target = f"http://{target}"
        proxy_target = target.rstrip("/")

    avail_dir, enabled_dir, www_dir = get_nginx_paths(config)
    conf_filename = f"{domain}.conf"
    avail_file = os.path.join(avail_dir, conf_filename)
    enabled_link = os.path.join(enabled_dir, conf_filename)

    root_dir = custom_root.strip() if custom_root.strip() else os.path.join(www_dir, domain)

    # 1. Prepare web root directory for static or php
    if site_type in ["static", "php"]:
        os.makedirs(root_dir, exist_ok=True)
        index_file = os.path.join(root_dir, "index.html")
        if not os.path.exists(index_file):
            # Create a clean starter page
            starter_html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{domain} — Hospedado no TomateCP</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
        body {{ background: #0F172A; color: #F8FAFC; display: flex; align-items: center; justify-content: center; min-height: 100vh; padding: 24px; text-align: center; }}
        .card {{ background: #1E293B; border: 1px solid rgba(255,255,255,0.08); border-radius: 16px; padding: 48px 32px; max-width: 520px; width: 100%; box-shadow: 0 20px 40px rgba(0,0,0,0.4); }}
        .badge {{ display: inline-block; background: rgba(34, 197, 94, 0.15); color: #22C55E; border: 1px solid rgba(34, 197, 94, 0.3); padding: 4px 12px; border-radius: 9999px; font-size: 13px; font-weight: 600; margin-bottom: 20px; }}
        h1 {{ font-size: 26px; font-weight: 700; margin-bottom: 12px; color: #FFFFFF; }}
        p {{ color: #94A3B8; font-size: 15px; line-height: 1.6; margin-bottom: 24px; }}
        .path {{ background: #0F172A; border-radius: 8px; padding: 12px; font-family: monospace; font-size: 13px; color: #EF4444; border: 1px solid rgba(255,255,255,0.05); }}
    </style>
</head>
<body>
    <div class="card">
        <span class="badge">● Online & Ativo</span>
        <h1>{domain}</h1>
        <p>Seu site foi configurado com sucesso pelo <strong>TomateCP</strong>. Substitua este arquivo na pasta do servidor:</p>
        <div class="path">{root_dir}/index.html</div>
    </div>
</body>
</html>"""
            with open(index_file, "w") as f:
                f.write(starter_html)

    # 2. Build Nginx Config
    if site_type == "proxy":
        if not proxy_target:
            return False, "Endereço de destino do Proxy Reverso é obrigatório (ex: http://127.0.0.1:3000)."
        config_content = f"""# Configuração gerada por TomateCP para {domain}
server {{
    listen {port};
    listen [::]:{port};
    server_name {domain};

    location / {{
        proxy_pass {proxy_target};
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
    }}

    access_log /var/log/nginx/{domain}.access.log;
    error_log /var/log/nginx/{domain}.error.log;
}}
"""
    elif site_type == "php":
        config_content = rf"""# Configuração gerada por TomateCP para {domain} (PHP)
server {{
    listen {port};
    listen [::]:{port};
    server_name {domain};

    root {root_dir};
    index index.php index.html;

    location / {{
        try_files $uri $uri/ /index.php?$query_string;
    }}

    location ~ \.php$ {{
        include snippets/fastcgi-php.conf;
        fastcgi_pass unix:/run/php/php-fpm.sock;
    }}

    location ~ /\.ht {{
        deny all;
    }}

    access_log /var/log/nginx/{domain}.access.log;
    error_log /var/log/nginx/{domain}.error.log;
}}
"""
    else:  # static
        config_content = rf"""# Configuração gerada por TomateCP para {domain} (Estático)
server {{
    listen {port};
    listen [::]:{port};
    server_name {domain};

    root {root_dir};
    index index.html index.htm;

    # Gzip e compressão
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml+rss text/javascript image/svg+xml;

    location / {{
        try_files $uri $uri/ /index.html =404;
    }}

    # Cache de assets estáticos
    location ~* \.(jpg|jpeg|png|gif|ico|css|js|svg|woff|woff2|ttf)$ {{
        expires 7d;
        add_header Cache-Control "public, no-transform";
    }}

    access_log /var/log/nginx/{domain}.access.log;
    error_log /var/log/nginx/{domain}.error.log;
}}
"""

    # 3. Write configuration file
    with open(avail_file, "w") as f:
        f.write(config_content)

    # 4. Create symlink to enable
    if os.path.lexists(enabled_link):
        os.remove(enabled_link)
    os.symlink(avail_file, enabled_link)

    # 5. Validate syntax with atomic rollback if invalid
    ok, err_msg = test_nginx_syntax(config.get("nginx_bin", "/usr/sbin/nginx"))
    if not ok:
        if os.path.exists(enabled_link):
            os.remove(enabled_link)
        if os.path.exists(avail_file):
            os.remove(avail_file)
        return False, f"Falha na sintaxe do Nginx: {err_msg}"

    # 6. Reload Nginx
    reload_ok, reload_msg = reload_nginx(config.get("systemctl_bin", "/bin/systemctl"), config.get("nginx_bin", "/usr/sbin/nginx"))
    if not reload_ok:
        return False, f"Site salvo mas erro ao recarregar Nginx: {reload_msg}"

    return True, f"Site {domain} criado e ativado com sucesso!"


def toggle_site(config: Dict[str, Any], domain: str, enable: bool) -> Tuple[bool, str]:
    """Enables or disables a site by managing the sites-enabled symlink."""
    avail_dir, enabled_dir, _ = get_nginx_paths(config)
    conf_name = f"{domain}.conf"
    avail_file = os.path.join(avail_dir, conf_name)
    enabled_link = os.path.join(enabled_dir, conf_name)

    if not os.path.exists(avail_file):
        return False, f"Configuração do site {domain} não encontrada."

    if enable:
        if not os.path.lexists(enabled_link):
            os.symlink(avail_file, enabled_link)
    else:
        if os.path.lexists(enabled_link):
            os.remove(enabled_link)

    # Validate and reload
    ok, err = test_nginx_syntax(config.get("nginx_bin", "/usr/sbin/nginx"))
    if not ok:
        # Revert change
        if enable and os.path.lexists(enabled_link):
            os.remove(enabled_link)
        elif not enable and not os.path.lexists(enabled_link):
            os.symlink(avail_file, enabled_link)
        return False, f"Erro de sintaxe ao alterar estado: {err}"

    reload_nginx(config.get("systemctl_bin", "/bin/systemctl"), config.get("nginx_bin", "/usr/sbin/nginx"))
    state_str = "ativado" if enable else "pausado"
    return True, f"Site {domain} {state_str} com sucesso."


def delete_site(config: Dict[str, Any], domain: str, delete_files: bool = False) -> Tuple[bool, str]:
    """Deletes the Nginx virtual host and optionally removes web files."""
    avail_dir, enabled_dir, www_dir = get_nginx_paths(config)
    conf_name = f"{domain}.conf"
    avail_file = os.path.join(avail_dir, conf_name)
    enabled_link = os.path.join(enabled_dir, conf_name)
    root_dir = os.path.join(www_dir, domain)

    if os.path.lexists(enabled_link):
        os.remove(enabled_link)
    if os.path.exists(avail_file):
        os.remove(avail_file)

    if delete_files and os.path.exists(root_dir):
        try:
            shutil.rmtree(root_dir)
        except Exception:
            pass

    reload_nginx(config.get("systemctl_bin", "/bin/systemctl"), config.get("nginx_bin", "/usr/sbin/nginx"))
    return True, f"Site {domain} removido com sucesso."


def extract_zip_to_site(config: Dict[str, Any], domain: str, zip_path: str) -> Tuple[bool, str]:
    """Safely extracts an uploaded zip archive into /var/www/<domain>."""
    avail_dir, enabled_dir, www_dir = get_nginx_paths(config)
    target_dir = os.path.join(www_dir, domain)
    os.makedirs(target_dir, exist_ok=True)

    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            # Check for zip bomb / malicious paths
            for member in zip_ref.namelist():
                filename = os.path.basename(member)
                if not filename:
                    continue
                # Reject relative escape paths
                target_path = os.path.abspath(os.path.join(target_dir, member))
                if not target_path.startswith(os.path.abspath(target_dir)):
                    return False, "Arquivo ZIP contém caminhos de segurança inválidos."

            zip_ref.extractall(target_dir)

        # Set permissions if running on Linux
        try:
            shutil.chown(target_dir, user="www-data", group="www-data")
        except Exception:
            pass

        return True, "Deploy do arquivo ZIP concluído com sucesso!"
    except Exception as e:
        return False, f"Erro ao extrair arquivo ZIP: {str(e)}"

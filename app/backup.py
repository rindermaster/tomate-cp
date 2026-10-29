import os
import shutil
import tarfile
import json
import time
import subprocess
from datetime import datetime
from typing import Dict, Any, List

BACKUP_DIR = "/var/backups/tomatecp"

def ensure_backup_dir():
    os.makedirs(BACKUP_DIR, exist_ok=True)

def list_backups() -> List[Dict[str, Any]]:
    """
    Returns list of existing TomateCP backups.
    """
    ensure_backup_dir()
    backups = []
    try:
        for fname in os.listdir(BACKUP_DIR):
            if fname.endswith(".tar.gz") and fname.startswith("tomatecp-backup-"):
                fpath = os.path.join(BACKUP_DIR, fname)
                st = os.stat(fpath)
                size_mb = round(st.st_size / (1024 * 1024), 2)
                mtime = datetime.fromtimestamp(st.st_mtime).strftime("%d/%m/%Y %H:%M:%S")
                backups.append({
                    "filename": fname,
                    "filepath": fpath,
                    "size_mb": size_mb,
                    "created_at": mtime,
                    "timestamp": st.st_mtime
                })
        backups.sort(key=lambda x: x["timestamp"], reverse=True)
    except Exception as e:
        print("Error listing backups:", e)
    return backups

def create_backup(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Creates a full backup archive (.tar.gz) containing:
    - /var/www (all hosted sites and files)
    - /etc/nginx/sites-available & sites-enabled
    - /opt/tomate-cp/data/config.json
    - Full MariaDB SQL dump (if active)
    - manifest.json
    """
    ensure_backup_dir()
    timestamp_str = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    archive_name = f"tomatecp-backup-{timestamp_str}.tar.gz"
    archive_path = os.path.join(BACKUP_DIR, archive_name)
    staging_dir = f"/tmp/tomatecp-backup-{timestamp_str}"

    os.makedirs(staging_dir, exist_ok=True)

    try:
        # 1. Copy /var/www
        www_source = config.get("nginx_www_dir", "/var/www")
        www_target = os.path.join(staging_dir, "www")
        if os.path.exists(www_source):
            shutil.copytree(www_source, www_target, symlinks=True, ignore=shutil.ignore_patterns("*.tmp", ".git"))
        else:
            os.makedirs(www_target, exist_ok=True)

        # 2. Copy Nginx configurations
        nginx_target = os.path.join(staging_dir, "nginx")
        os.makedirs(nginx_target, exist_ok=True)
        nginx_avail = "/etc/nginx/sites-available"
        nginx_enabled = "/etc/nginx/sites-enabled"
        if os.path.exists(nginx_avail):
            shutil.copytree(nginx_avail, os.path.join(nginx_target, "sites-available"), symlinks=True)
        if os.path.exists(nginx_enabled):
            shutil.copytree(nginx_enabled, os.path.join(nginx_target, "sites-enabled"), symlinks=True)

        # 3. Copy TomateCP configuration
        config_target = os.path.join(staging_dir, "tomatecp-config")
        os.makedirs(config_target, exist_ok=True)
        cfg_source = "/opt/tomate-cp/data/config.json"
        if os.path.exists(cfg_source):
            shutil.copy2(cfg_source, config_target)

        # 4. Dump MariaDB databases (if active)
        has_mariadb_dump = False
        try:
            sql_dump_path = os.path.join(staging_dir, "database_mariadb.sql")
            dump_res = subprocess.run(
                ["mysqldump", "--all-databases", "--single-transaction", "--quick", "-r", sql_dump_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30
            )
            if dump_res.returncode == 0 and os.path.exists(sql_dump_path):
                has_mariadb_dump = True
        except Exception:
            pass

        # 5. Build manifest
        sites_list = []
        if os.path.exists(www_target):
            sites_list = [d for d in os.listdir(www_target) if os.path.isdir(os.path.join(www_target, d))]

        manifest = {
            "version": "1.0.0",
            "generator": "TomateCP Disaster Recovery",
            "created_at": datetime.now().isoformat(),
            "panel_name": config.get("panel_name", "TomateCP"),
            "sites": sites_list,
            "has_mariadb_dump": has_mariadb_dump,
        }
        with open(os.path.join(staging_dir, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        # 6. Compress with tarfile
        with tarfile.open(archive_path, "w:gz") as tar:
            for item in os.listdir(staging_dir):
                item_path = os.path.join(staging_dir, item)
                tar.add(item_path, arcname=item)

        st = os.stat(archive_path)
        size_mb = round(st.st_size / (1024 * 1024), 2)

        return {
            "success": True,
            "filename": archive_name,
            "filepath": archive_path,
            "size_mb": size_mb,
            "sites_count": len(sites_list),
            "created_at": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            "message": f"Backup criado com sucesso! Tamanho: {size_mb} MB ({len(sites_list)} sites arquivados)."
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Erro ao gerar backup: {str(e)}"
        }
    finally:
        if os.path.exists(staging_dir):
            shutil.rmtree(staging_dir, ignore_errors=True)

def delete_backup(filename: str) -> Dict[str, Any]:
    """
    Deletes a backup file safely.
    """
    clean_name = os.path.basename(filename)
    if ".." in clean_name or "/" in clean_name or not clean_name.endswith(".tar.gz"):
        return {"success": False, "message": "Nome de arquivo inválido."}

    fpath = os.path.join(BACKUP_DIR, clean_name)
    if not os.path.exists(fpath):
        return {"success": False, "message": "Arquivo de backup não encontrado."}

    try:
        os.remove(fpath)
        return {"success": True, "message": f"Backup {clean_name} excluído."}
    except Exception as e:
        return {"success": False, "message": f"Erro ao excluir: {str(e)}"}

def restore_backup(archive_path: str) -> Dict[str, Any]:
    """
    Restores sites, Nginx configs, and databases from an uploaded or stored backup.
    """
    if not os.path.exists(archive_path):
        return {"success": False, "message": "Arquivo de backup não encontrado."}

    staging_dir = f"/tmp/tomatecp-restore-{int(time.time())}"
    os.makedirs(staging_dir, exist_ok=True)

    try:
        with tarfile.open(archive_path, "r:gz") as tar:
            tar.extractall(path=staging_dir)

        manifest_path = os.path.join(staging_dir, "manifest.json")
        if not os.path.exists(manifest_path):
            return {"success": False, "message": "Arquivo de backup inválido (manifest.json ausente)."}

        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        # 1. Restore /var/www
        staged_www = os.path.join(staging_dir, "www")
        if os.path.exists(staged_www):
            os.makedirs("/var/www", exist_ok=True)
            for item in os.listdir(staged_www):
                src = os.path.join(staged_www, item)
                dst = os.path.join("/var/www", item)
                if os.path.isdir(src):
                    if os.path.exists(dst):
                        shutil.rmtree(dst)
                    shutil.copytree(src, dst, symlinks=True)
                else:
                    shutil.copy2(src, dst)
            # Fix permissions
            subprocess.run(["chown", "-R", "www-data:www-data", "/var/www"], timeout=10)

        # 2. Restore Nginx sites
        staged_nginx = os.path.join(staging_dir, "nginx")
        if os.path.exists(staged_nginx):
            avail_src = os.path.join(staged_nginx, "sites-available")
            if os.path.exists(avail_src):
                os.makedirs("/etc/nginx/sites-available", exist_ok=True)
                for item in os.listdir(avail_src):
                    shutil.copy2(os.path.join(avail_src, item), "/etc/nginx/sites-available/")

            enabled_src = os.path.join(staged_nginx, "sites-enabled")
            if os.path.exists(enabled_src):
                os.makedirs("/etc/nginx/sites-enabled", exist_ok=True)
                for item in os.listdir(enabled_src):
                    src_link = os.path.join(enabled_src, item)
                    target_link = os.path.join("/etc/nginx/sites-enabled", item)
                    if not os.path.exists(target_link):
                        shutil.copy2(src_link, target_link)

        # 3. Restore MariaDB SQL dump if present
        staged_sql = os.path.join(staging_dir, "database_mariadb.sql")
        if os.path.exists(staged_sql):
            try:
                subprocess.run(f"mysql < {staged_sql}", shell=True, timeout=60)
            except Exception:
                pass

        # 4. Test and reload Nginx
        subprocess.run(["nginx", "-t"], timeout=5)
        subprocess.run(["systemctl", "reload", "nginx"], timeout=5)

        sites_count = len(manifest.get("sites", []))
        return {
            "success": True,
            "sites_count": sites_count,
            "message": f"Restauração concluída com sucesso! {sites_count} sites e configurações foram restaurados."
        }
    except Exception as e:
        return {"success": False, "message": f"Erro durante a restauração: {str(e)}"}
    finally:
        if os.path.exists(staging_dir):
            shutil.rmtree(staging_dir, ignore_errors=True)

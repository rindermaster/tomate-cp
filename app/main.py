"""
TomateCP - Main Application Entrypoint
Ultra-lightweight web hosting panel for TV Boxes, SBCs, and minimal Linux servers.
Built with FastAPI, Jinja2, and zero bloat.
"""

import os
import json
import urllib.parse
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, Form, UploadFile, File, HTTPException, status, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from app.files import (
    list_directory, read_file, save_file, create_file,
    create_directory, rename_item, delete_item, upload_to_directory, is_safe_path
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.system import get_full_telemetry, is_nginx_active

from app.system import drop_caches, reboot_system, execute_terminal_command
from app.backup import list_backups, create_backup, delete_backup, restore_backup, BACKUP_DIR
from app.databases import (
    list_sqlite_databases, create_sqlite_database, execute_sqlite_query,
    is_mariadb_active, list_mariadb_databases, create_mariadb_database, delete_mariadb_database
)
from app.git_deploy import git_pull, setup_git_repo, generate_webhook_token
from app.wordpress import install_wordpress, is_php_installed

from app.sites import (
    list_sites, create_site, toggle_site, delete_site, 
    extract_zip_to_site, reload_nginx, test_nginx_syntax
)
from app.ai_agent import (
    POPULAR_MODELS, mask_api_key, get_site_root, scan_site_files,
    read_text_safe, write_text_safe, backup_file, rollback_file,
    generate_diff, call_llm, extract_file_proposals
)

from app.auth import (
    create_session_token, verify_session_token, 
    get_current_user_optional, require_auth
)

# Root directory of TomateCP
BASE_DIR = Path(__file__).resolve().parent.parent

# Config loading helper
def load_config():
    config_path = BASE_DIR / "config" / "config.json"
    if not config_path.exists():
        example_path = BASE_DIR / "config.example.json"
        if example_path.exists():
            shutil.copy(example_path, config_path)
        else:
            return {
                "panel_name": "TomateCP",
                "brand_name": "Tomate Mini Server",
                "company_name": "ZipDigital",
                "accent_color": "#EF4444",
                "port": 8888,
                "host": "0.0.0.0",
                "secret_key": "tomate-cp-ultra-secret",
                "admin_username": "admin",
                "admin_password": "admin"
            }
    try:
        with open(config_path, "r") as f:
            return json.load(f)
    except Exception:
        return {}

def save_config(cfg):
    config_path = BASE_DIR / "config" / "config.json"
    os.makedirs(config_path.parent, exist_ok=True)
    with open(config_path, "w") as f:
        json.dump(cfg, f, indent=2)

config = load_config()

# Initialize FastAPI App
app = FastAPI(
    title=config.get("panel_name", "TomateCP"),
    description="Painel de hospedagem web ultra-leve para TV Boxes e SBCs",
    version="1.0.0"
)

# Mount Static Files & Templates
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app" / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

# Inject branding variables into all template contexts
def get_template_context(request: Request, extra: dict = None) -> dict:
    ctx = {
        "request": request,
        "config": config,
        "panel_name": config.get("panel_name", "TomateCP"),
        "brand_name": config.get("brand_name", "Tomate Mini Server"),
        "company_name": config.get("company_name", "ZipDigital"),
        "accent_color": config.get("accent_color", "#EF4444"),
        "logged_user": get_current_user_optional(request, config),
        "public_ip": get_full_telemetry().get("public_ip", "127.0.0.1"),
        "local_ip": get_full_telemetry().get("local_ip", "127.0.0.1"),
        "tunnel_cname": config.get("tunnel_cname", "ce28d5bc-f161-4c93-adcf-c6c6c44b4991.cfargotunnel.com"),
    }
    if extra:
        ctx.update(extra)
    return ctx


# -----------------------------------------------------------------------------
# Authentication Routes
# -----------------------------------------------------------------------------
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: Optional[str] = None):
    if get_current_user_optional(request, config):
        return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse(request=request, name="login.html", context=get_template_context(request, {"error": error}))


@app.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    valid_user = config.get("admin_username", "admin")
    valid_pass = config.get("admin_password", "admin")

    if username == valid_user and password == valid_pass:
        token = create_session_token(username, config.get("secret_key", "secret"))
        resp = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
        resp.set_cookie(
            key="tomate_session",
            value=token,
            httponly=True,
            max_age=7 * 86400,
            samesite="lax"
        )
        return resp

    return templates.TemplateResponse(
        "login.html",
        get_template_context(request, {"error": "Usuário ou senha incorretos."})
    )


@app.get("/logout")
async def logout():
    resp = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    resp.delete_cookie("tomate_session")
    return resp


# -----------------------------------------------------------------------------
# Web Pages (Authenticated)
# -----------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    require_auth(request, config)
    telemetry = get_full_telemetry()
    all_sites = list_sites(config)
    active_sites = [s for s in all_sites if s["active"]]
    
    context = get_template_context(request, {
        "page": "dashboard",
        "telemetry": telemetry,
        "sites_total": len(all_sites),
        "sites_active": len(active_sites),
    })
    return templates.TemplateResponse(request=request, name="dashboard.html", context=context)


@app.get("/sites", response_class=HTMLResponse)
async def sites_page(request: Request, msg: Optional[str] = None, err: Optional[str] = None):
    require_auth(request, config)
    all_sites = list_sites(config)
    context = get_template_context(request, {
        "page": "sites",
        "sites": all_sites,
        "msg": msg,
        "err": err,
    })
    return templates.TemplateResponse(request=request, name="sites.html", context=context)


@app.get("/files", response_class=HTMLResponse)
async def files_page(request: Request, path: Optional[str] = None):
    require_auth(request, config)
    all_sites = list_sites(config)
    www_dir = config.get("nginx_www_dir", "/var/www")
    
    target_path = path if path else www_dir
    if not os.path.exists(target_path):
        target_path = www_dir

    context = get_template_context(request, {
        "page": "files",
        "sites": all_sites,
        "initial_path": target_path,
        "www_dir": www_dir,
    })
    return templates.TemplateResponse(request=request, name="files.html", context=context)


@app.get("/deploy", response_class=HTMLResponse)
async def deploy_page(request: Request, site: Optional[str] = None, msg: Optional[str] = None, err: Optional[str] = None):
    require_auth(request, config)
    all_sites = list_sites(config)
    context = get_template_context(request, {
        "page": "deploy",
        "sites": all_sites,
        "selected_site": site,
        "msg": msg,
        "err": err,
    })
    return templates.TemplateResponse(request=request, name="deploy.html", context=context)


@app.get("/logs", response_class=HTMLResponse)
async def logs_page(request: Request):
    require_auth(request, config)
    context = get_template_context(request, {
        "page": "logs",
    })
    return templates.TemplateResponse(request=request, name="logs.html", context=context)


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, msg: Optional[str] = None, err: Optional[str] = None):
    require_auth(request, config)
    context = get_template_context(request, {
        "page": "settings",
        "msg": msg,
        "err": err,
    })
    return templates.TemplateResponse(request=request, name="settings.html", context=context)


# -----------------------------------------------------------------------------
# REST API Endpoints
# -----------------------------------------------------------------------------
@app.get("/api/system/stats")
async def api_system_stats(request: Request):
    require_auth(request, config)
    return get_full_telemetry()


@app.get("/api/sites")
async def api_list_sites(request: Request):
    require_auth(request, config)
    return list_sites(config)


@app.post("/api/sites/create")
async def api_create_site(
    request: Request,
    domain: str = Form(...),
    site_type: str = Form("static"),
    proxy_target: str = Form(""),
    custom_root: str = Form(""),
    port: int = Form(80)
):
    require_auth(request, config)
    domain_clean = domain.strip().lower()
    if domain_clean.startswith("http://"):
        domain_clean = domain_clean[7:]
    elif domain_clean.startswith("https://"):
        domain_clean = domain_clean[8:]
    domain_clean = domain_clean.split("/")[0].strip()

    if site_type == "wordpress":
        # 1. Create PHP virtual host in Nginx
        ok, msg = create_site(config, domain_clean, "php", proxy_target, custom_root, port)
        if not ok:
            return RedirectResponse(url=f"/sites?err={urllib.parse.quote(str(msg))}", status_code=status.HTTP_302_FOUND)
        
        # 2. Setup database credentials
        site_path = f"/var/www/{domain_clean}"
        db_name = "wp_" + "".join(c for c in domain_clean if c.isalnum())[:16]
        db_user = "usr_" + "".join(c for c in domain_clean if c.isalnum())[:12]
        import secrets
        db_pass = secrets.token_hex(8)

        if is_mariadb_active():
            create_mariadb_database(db_name, db_user, db_pass)

        # 3. Install WordPress
        wp_res = install_wordpress(domain_clean, db_name, db_user, db_pass, site_path)
        if wp_res.get("success"):
            return RedirectResponse(url=f"/sites?msg={urllib.parse.quote(wp_res['message'])}", status_code=status.HTTP_302_FOUND)
        else:
            return RedirectResponse(url=f"/sites?err={urllib.parse.quote(wp_res['message'])}", status_code=status.HTTP_302_FOUND)

    ok, msg = create_site(config, domain, site_type, proxy_target, custom_root, port)
    if ok:
        return RedirectResponse(url=f"/sites?msg={urllib.parse.quote(str(msg))}", status_code=status.HTTP_302_FOUND)
    return RedirectResponse(url=f"/sites?err={urllib.parse.quote(str(msg))}", status_code=status.HTTP_302_FOUND)


@app.post("/api/sites/toggle")
async def api_toggle_site(
    request: Request,
    domain: str = Form(...),
    enable: bool = Form(...)
):
    require_auth(request, config)
    ok, msg = toggle_site(config, domain, enable)
    return {"success": ok, "message": msg}


@app.post("/api/sites/delete")
async def api_delete_site(
    request: Request,
    domain: str = Form(...),
    delete_files: bool = Form(False)
):
    require_auth(request, config)
    ok, msg = delete_site(config, domain, delete_files)
    if ok:
        return RedirectResponse(url=f"/sites?msg={urllib.parse.quote(str(msg))}", status_code=status.HTTP_302_FOUND)
    return RedirectResponse(url=f"/sites?err={urllib.parse.quote(str(msg))}", status_code=status.HTTP_302_FOUND)



import socket

@app.get("/api/sites/check-dns")
async def api_check_dns(domain: str):
    domain = domain.strip().lower()
    if domain.startswith("http://"): domain = domain[7:]
    if domain.startswith("https://"): domain = domain[8:]
    domain = domain.split("/")[0]

    telemetry = get_full_telemetry()
    server_public_ip = telemetry.get("public_ip", "")

    try:
        results = socket.getaddrinfo(domain, 80)
        ips = list(set([r[4][0] for r in results]))
        is_cf = any(ip.startswith("104.") or ip.startswith("172.67.") or ip.startswith("2606:4700:") for ip in ips)
        is_direct = (server_public_ip in ips) if server_public_ip else False
        
        status_msg = "Apontado com Sucesso via Cloudflare!" if is_cf else ("Apontado diretamente para o IP da TV Box!" if is_direct else f"Apontando para {', '.join(ips)}")
        return {
            "success": True,
            "domain": domain,
            "ips": ips,
            "is_cloudflare": is_cf,
            "is_direct": is_direct,
            "status_msg": status_msg
        }
    except Exception as e:
        return {
            "success": False,
            "domain": domain,
            "error": "Domínio ainda não propaga ou não possui registro DNS.",
            "ips": []
        }

@app.post("/api/sites/upload-zip")
async def api_upload_zip(
    request: Request,
    domain: str = Form(...),
    file: UploadFile = File(...)
):
    require_auth(request, config)
    if not file.filename.endswith(".zip"):
        return RedirectResponse(url=f"/deploy?site={domain}&err=O arquivo deve ter extensão .zip", status_code=status.HTTP_302_FOUND)

    temp_zip = f"/tmp/{domain}_{file.filename}"
    with open(temp_zip, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    ok, msg = extract_zip_to_site(config, domain, temp_zip)
    if os.path.exists(temp_zip):
        os.remove(temp_zip)

    if ok:
        return RedirectResponse(url=f"/deploy?site={domain}&msg={urllib.parse.quote(str(msg))}", status_code=status.HTTP_302_FOUND)
    return RedirectResponse(url=f"/deploy?site={domain}&err={urllib.parse.quote(str(msg))}", status_code=status.HTTP_302_FOUND)


# -----------------------------------------------------------------------------
# File Manager & Code Editor API
# -----------------------------------------------------------------------------
@app.get("/api/files/list")
async def api_files_list(request: Request, path: str = "/var/www"):
    require_auth(request, config)
    ok, result = list_directory(path)
    if not ok:
        return JSONResponse(status_code=400, content={"success": False, "message": result})
    return {"success": True, "data": result}


@app.get("/api/files/read")
async def api_files_read(request: Request, path: str):
    require_auth(request, config)
    ok, result = read_file(path)
    if not ok:
        return JSONResponse(status_code=400, content={"success": False, "message": result})
    return {"success": True, "data": result}


@app.post("/api/files/save")
async def api_files_save(request: Request):
    require_auth(request, config)
    try:
        data = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"success": False, "message": "Corpo da requisição inválido."})
        
    path = data.get("path")
    file_content = data.get("content", "")
    if not path:
        return JSONResponse(status_code=400, content={"success": False, "message": "Caminho do arquivo não fornecido."})
    
    ok, msg = save_file(path, file_content)
    if not ok:
        return JSONResponse(status_code=400, content={"success": False, "message": msg})
    return {"success": True, "message": msg}


@app.post("/api/files/create")
async def api_files_create(request: Request):
    require_auth(request, config)
    try:
        data = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"success": False, "message": "Corpo da requisição inválido."})

    parent = data.get("parent")
    name = data.get("name")
    is_dir = data.get("is_dir", False)
    if not parent or not name:
        return JSONResponse(status_code=400, content={"success": False, "message": "Diretório e nome são obrigatórios."})
    
    if is_dir:
        ok, msg = create_directory(parent, name)
    else:
        ok, msg = create_file(parent, name)
        
    if not ok:
        return JSONResponse(status_code=400, content={"success": False, "message": msg})
    return {"success": True, "message": msg}


@app.post("/api/files/rename")
async def api_files_rename(request: Request):
    require_auth(request, config)
    try:
        data = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"success": False, "message": "Corpo da requisição inválido."})

    path = data.get("path")
    new_name = data.get("new_name")
    if not path or not new_name:
        return JSONResponse(status_code=400, content={"success": False, "message": "Caminho e novo nome são obrigatórios."})
    
    ok, msg = rename_item(path, new_name)
    if not ok:
        return JSONResponse(status_code=400, content={"success": False, "message": msg})
    return {"success": True, "message": msg}


@app.post("/api/files/delete")
async def api_files_delete(request: Request):
    require_auth(request, config)
    try:
        data = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"success": False, "message": "Corpo da requisição inválido."})

    path = data.get("path")
    if not path:
        return JSONResponse(status_code=400, content={"success": False, "message": "Caminho do item não fornecido."})
    
    ok, msg = delete_item(path)
    if not ok:
        return JSONResponse(status_code=400, content={"success": False, "message": msg})
    return {"success": True, "message": msg}


@app.post("/api/files/upload")
async def api_files_upload(
    request: Request,
    parent: str = Form(...),
    unzip: bool = Form(False),
    file: UploadFile = File(...)
):
    require_auth(request, config)
    content_bytes = await file.read()
    ok, msg = upload_to_directory(parent, file.filename, content_bytes, unzip=unzip)
    if not ok:
        return JSONResponse(status_code=400, content={"success": False, "message": msg})
    return {"success": True, "message": msg}


@app.get("/api/files/download")
async def api_files_download(request: Request, path: str):
    require_auth(request, config)
    if not is_safe_path(path) or not os.path.exists(path) or not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Arquivo não encontrado ou acesso negado.")
    filename = os.path.basename(path)
    return FileResponse(path, filename=filename)


@app.post("/api/system/nginx-reload")
async def api_nginx_reload(request: Request):
    require_auth(request, config)
    ok, msg = reload_nginx(config.get("systemctl_bin", "/bin/systemctl"), config.get("nginx_bin", "/usr/sbin/nginx"))
    return {"success": ok, "message": msg}


@app.get("/api/logs")
async def api_get_logs(request: Request, log_type: str = "access", lines: int = 50):
    require_auth(request, config)
    log_file = "/var/log/nginx/access.log" if log_type == "access" else "/var/log/nginx/error.log"
    if not os.path.exists(log_file):
        return {"logs": f"Arquivo {log_file} não encontrado ou vazio."}

    try:
        proc = subprocess.run(
            ["tail", "-n", str(lines), log_file],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=2
        )
        return {"logs": proc.stdout or "Nenhum registro recente."}
    except Exception as e:
        return {"logs": f"Erro ao ler logs: {e}"}


@app.post("/api/settings/update")
async def api_settings_update(
    request: Request,
    panel_name: str = Form(...),
    brand_name: str = Form(...),
    company_name: str = Form(...),
    accent_color: str = Form(...),
    tunnel_cname: Optional[str] = Form(None),
    new_password: Optional[str] = Form(None)
):
    require_auth(request, config)
    config["panel_name"] = panel_name.strip()
    config["brand_name"] = brand_name.strip()
    config["company_name"] = company_name.strip()
    config["accent_color"] = accent_color.strip()
    if tunnel_cname:
        config["tunnel_cname"] = tunnel_cname.strip()

    if new_password and new_password.strip():
        config["admin_password"] = new_password.strip()

    save_config(config)
    return RedirectResponse(url="/settings?msg=Configurações e marca atualizadas com sucesso!", status_code=status.HTTP_302_FOUND)


# -----------------------------------------------------------------------------
# Runner
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# 🗄️ Bancos de Dados (SQLite & MariaDB)
# -----------------------------------------------------------------------------
@app.get("/databases", response_class=HTMLResponse)
async def databases_page(request: Request, msg: Optional[str] = None, err: Optional[str] = None):
    require_auth(request, config)
    all_sites = list_sites(config)
    sqlite_dbs = list_sqlite_databases("/var/www")
    mariadb_dbs = list_mariadb_databases()
    mariadb_on = is_mariadb_active()

    context = get_template_context(request, {
        "page": "databases",
        "sites": all_sites,
        "sqlite_dbs": sqlite_dbs,
        "mariadb_dbs": mariadb_dbs,
        "mariadb_active": mariadb_on,
        "msg": msg,
        "err": err,
    })
    return templates.TemplateResponse(request=request, name="databases.html", context=context)


@app.post("/api/databases/sqlite/create")
async def api_create_sqlite(request: Request, folder_path: str = Form(...), filename: str = Form(...)):
    require_auth(request, config)
    res = create_sqlite_database(folder_path.strip(), filename.strip())
    if res["success"]:
        return RedirectResponse(url=f"/databases?msg={urllib.parse.quote(res['message'])}", status_code=status.HTTP_302_FOUND)
    return RedirectResponse(url=f"/databases?err={urllib.parse.quote(res['message'])}", status_code=status.HTTP_302_FOUND)


@app.post("/api/databases/sqlite/query")
async def api_query_sqlite(request: Request, db_path: str = Form(...), query: str = Form(...)):
    require_auth(request, config)
    return execute_sqlite_query(db_path.strip(), query.strip())


@app.post("/api/databases/mariadb/create")
async def api_create_mariadb(request: Request, db_name: str = Form(...), username: Optional[str] = Form(None), password: Optional[str] = Form(None)):
    require_auth(request, config)
    res = create_mariadb_database(db_name.strip(), username.strip() if username else None, password.strip() if password else None)
    if res["success"]:
        return RedirectResponse(url=f"/databases?msg={urllib.parse.quote(res['message'])}", status_code=status.HTTP_302_FOUND)
    return RedirectResponse(url=f"/databases?err={urllib.parse.quote(res['message'])}", status_code=status.HTTP_302_FOUND)


@app.post("/api/databases/mariadb/delete")
async def api_delete_mariadb(request: Request, db_name: str = Form(...)):
    require_auth(request, config)
    return delete_mariadb_database(db_name.strip())


# -----------------------------------------------------------------------------
# 📦 Backups & Disaster Recovery (1-Clique)
# -----------------------------------------------------------------------------
@app.get("/backups", response_class=HTMLResponse)
async def backups_page(request: Request, msg: Optional[str] = None, err: Optional[str] = None):
    require_auth(request, config)
    backups = list_backups()
    context = get_template_context(request, {
        "page": "backups",
        "backups": backups,
        "msg": msg,
        "err": err,
    })
    return templates.TemplateResponse(request=request, name="backups.html", context=context)


@app.post("/api/backups/create")
async def api_create_backup(request: Request):
    require_auth(request, config)
    return create_backup(config)


@app.get("/api/backups/download/{filename}")
async def api_download_backup(request: Request, filename: str):
    require_auth(request, config)
    clean_name = os.path.basename(filename)
    fpath = os.path.join(BACKUP_DIR, clean_name)
    if not os.path.exists(fpath):
        raise HTTPException(status_code=404, detail="Arquivo de backup não encontrado.")
    return FileResponse(path=fpath, filename=clean_name, media_type="application/gzip")


@app.post("/api/backups/delete")
async def api_delete_backup(request: Request, filename: str = Form(...)):
    require_auth(request, config)
    return delete_backup(filename.strip())


@app.post("/api/backups/restore")
async def api_restore_backup_upload(request: Request, backup_file: UploadFile = File(...)):
    require_auth(request, config)
    tmp_path = f"/tmp/upload-restore-{backup_file.filename}"
    try:
        with open(tmp_path, "wb") as f:
            shutil.copyfileobj(backup_file.file, f)
        res = restore_backup(tmp_path)
        if res["success"]:
            return RedirectResponse(url=f"/backups?msg={urllib.parse.quote(res['message'])}", status_code=status.HTTP_302_FOUND)
        return RedirectResponse(url=f"/backups?err={urllib.parse.quote(res['message'])}", status_code=status.HTTP_302_FOUND)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@app.post("/api/backups/restore-stored")
async def api_restore_stored_backup(request: Request, filename: str = Form(...)):
    require_auth(request, config)
    clean_name = os.path.basename(filename)
    fpath = os.path.join(BACKUP_DIR, clean_name)
    return restore_backup(fpath)


# -----------------------------------------------------------------------------
# ⚡ Ações Rápidas de Sistema & Mini Web Terminal
# -----------------------------------------------------------------------------
@app.post("/api/system/drop-caches")
async def api_drop_caches(request: Request):
    require_auth(request, config)
    return drop_caches()


@app.post("/api/system/reboot")
async def api_reboot(request: Request):
    require_auth(request, config)
    return reboot_system()


@app.post("/api/system/terminal/exec")
async def api_terminal_exec(request: Request, command: str = Form(...)):
    require_auth(request, config)
    return execute_terminal_command(command)


# -----------------------------------------------------------------------------
# 🌐 Git Webhooks & Deploy Automático
# -----------------------------------------------------------------------------
@app.post("/api/git/setup")
async def api_git_setup(request: Request, domain: str = Form(...), repo_url: str = Form(...), branch: str = Form("main")):
    require_auth(request, config)
    site_path = f"/var/www/{domain.strip()}"
    res = setup_git_repo(site_path, repo_url.strip(), branch.strip())
    # Save git info in config
    if "sites_git" not in config:
        config["sites_git"] = {}
    config["sites_git"][domain.strip()] = {
        "repo_url": repo_url.strip(),
        "branch": branch.strip(),
        "webhook_token": generate_webhook_token()
    }
    save_config(config)
    return res


@app.post("/api/git/pull")
async def api_git_pull(request: Request, domain: str = Form(...)):
    require_auth(request, config)
    site_path = f"/var/www/{domain.strip()}"
    git_info = config.get("sites_git", {}).get(domain.strip(), {})
    branch = git_info.get("branch", "main")
    return git_pull(site_path, branch)


@app.post("/api/webhooks/git")
async def api_git_webhook(request: Request, domain: str, token: str):
    """
    Public Webhook endpoint for GitHub/GitLab commits.
    """
    git_info = config.get("sites_git", {}).get(domain.strip(), {})
    saved_token = git_info.get("webhook_token")
    if not saved_token or saved_token != token.strip():
        raise HTTPException(status_code=403, detail="Token de webhook inválido.")

    site_path = f"/var/www/{domain.strip()}"
    branch = git_info.get("branch", "main")
    return git_pull(site_path, branch)


# -----------------------------------------------------------------------------
# 🪄 WordPress Lite 1-Clique
# -----------------------------------------------------------------------------
@app.post("/api/sites/install-wordpress")
async def api_install_wordpress(request: Request, domain: str = Form(...)):
    require_auth(request, config)
    domain = domain.strip().lower()
    site_path = f"/var/www/{domain}"
    db_name = "wp_" + "".join(c for c in domain if c.isalnum())[:16]
    db_user = "usr_" + "".join(c for c in domain if c.isalnum())[:12]
    import secrets
    db_pass = secrets.token_hex(8)

    # 1. Create site in Nginx if not exists
    create_site(domain=domain, site_type="php", port=80, config=config)

    # 2. Create MariaDB database and user if MariaDB is active
    if is_mariadb_active():
        create_mariadb_database(db_name, db_user, db_pass)

    # 3. Install WordPress
    res = install_wordpress(domain, db_name, db_user, db_pass, site_path)
    return res



# -----------------------------------------------------------------------------
# 🤖 Agente Tomate IA (Web Developer Agent)
# -----------------------------------------------------------------------------
@app.get("/ai-agent", response_class=HTMLResponse)
async def ai_agent_page(request: Request, site: Optional[str] = None):
    require_auth(request, config)
    all_sites = list_sites(config)
    selected_site = site or (all_sites[0]["domain"] if all_sites else "")
    cfg = load_config()
    current_model = cfg.get("ai_model", "cohere/north-mini-code:free")
    raw_key = cfg.get("openrouter_api_key", "")
    masked = mask_api_key(raw_key) if raw_key else ""
    current_provider = cfg.get("ai_provider", "openrouter")
    ollama_url = cfg.get("ollama_base_url", "http://127.0.0.1:11434")

    context = get_template_context(request, {
        "page": "ai_agent",
        "sites": all_sites,
        "selected_site": selected_site,
        "popular_models": POPULAR_MODELS,
        "current_model": current_model,
        "masked_key": masked,
        "current_provider": current_provider,
        "ollama_url": ollama_url,
    })
    return templates.TemplateResponse(request=request, name="ai_agent.html", context=context)


@app.get("/api/ai/config")
async def api_ai_get_config(request: Request):
    require_auth(request, config)
    cfg = load_config()
    raw_key = cfg.get("openrouter_api_key", "")
    return {
        "success": True,
        "provider": cfg.get("ai_provider", "openrouter"),
        "model": cfg.get("ai_model", "cohere/north-mini-code:free"),
        "masked_key": mask_api_key(raw_key) if raw_key else "",
        "ollama_base_url": cfg.get("ollama_base_url", "http://127.0.0.1:11434"),
        "popular_models": POPULAR_MODELS,
    }


@app.post("/api/ai/config")
async def api_ai_save_config(request: Request):
    require_auth(request, config)
    try:
        data = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"success": False, "message": "JSON inválido."})

    cfg = load_config()
    if "ai_provider" in data:
        cfg["ai_provider"] = data["ai_provider"]
    if "ai_model" in data and data["ai_model"]:
        cfg["ai_model"] = data["ai_model"].strip()
    if "ollama_base_url" in data and data["ollama_base_url"]:
        cfg["ollama_base_url"] = data["ollama_base_url"].strip()

    new_key = data.get("openrouter_api_key", "").strip()
    if new_key and not new_key.startswith("sk-or-...") and not new_key.startswith("****"):
        cfg["openrouter_api_key"] = new_key

    save_config(cfg)
    config.clear()
    config.update(cfg)

    return {"success": True, "message": "Configurações de IA salvas com sucesso!"}


@app.post("/api/ai/chat")
async def api_ai_chat(request: Request):
    require_auth(request, config)
    try:
        data = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"success": False, "message": "JSON inválido."})

    site = (data.get("site") or "").strip()
    prompt = (data.get("prompt") or "").strip()
    history = data.get("history") or []

    if not site:
        return JSONResponse(status_code=400, content={"success": False, "message": "Nenhum site selecionado."})
    if not prompt:
        return JSONResponse(status_code=400, content={"success": False, "message": "Prompt vazio."})

    root = get_site_root(site)
    if not root:
        return JSONResponse(status_code=404, content={"success": False, "message": f"Diretório do site '{site}' não encontrado."})

    site_files = scan_site_files(root, max_files=40)
    files_summary = "\n".join([f"- {f['path']} ({f['size']} bytes)" for f in site_files[:30]])
    if not files_summary:
        files_summary = "(Site vazio ou nenhum arquivo encontrado)"

    common_files = ["index.html", "index.php", "style.css", "styles.css", "main.css", "app.js", "main.js", "script.js"]
    loaded_contents = []
    total_bytes = 0
    max_total_bytes = 25000

    for cf in common_files:
        if total_bytes >= max_total_bytes:
            break
        text = read_text_safe(root, cf, max_bytes=8000)
        if text:
            loaded_contents.append(f"--- INÍCIO DE {cf} ---\n{text}\n--- FIM DE {cf} ---")
            total_bytes += len(text.encode("utf-8"))

    for f in site_files:
        p = f["path"]
        if p not in common_files and p.lower() in prompt.lower() and total_bytes < max_total_bytes:
            text = read_text_safe(root, p, max_bytes=10000)
            if text:
                loaded_contents.append(f"--- INÍCIO DE {p} ---\n{text}\n--- FIM DE {p} ---")
                total_bytes += len(text.encode("utf-8"))

    context_str = "\n\n".join(loaded_contents) if loaded_contents else "(Nenhum arquivo comum encontrado ainda. Você pode criar novos arquivos!)"

    system_prompt = f"""Você é o Agente Tomate IA, o assistente programador web do painel TomateCP.
Você roda diretamente na Box Linux do usuário gerenciando o site '{site}'.
Você é um desenvolvedor full-stack experiente, focado em código limpo, moderno, responsivo e sem dependências pesadas desnecessárias.

Arquivos existentes no site '{site}':
{files_summary}

Conteúdo dos arquivos atuais do site:
{context_str}

DIRETRIZES DE RESPOSTA:
1. Explique brevemente o que você fez ou propôs de forma educada, clara e direta em Português (Brasil).
2. Se você criar ou alterar arquivos, você DEVE OBRIGATORIAMENTE formatar o arquivo completo dentro de um bloco no seguinte formato exato:
```FILE: caminho/do/arquivo.ext
conteudo completo do arquivo aqui
```
3. NUNCA coloque código parcial ou com reticências dentro do bloco ```FILE: ...```. Forneça o arquivo COMPLETO para que ele possa ser salvo diretamente no servidor.
4. Você pode sugerir múltiplos blocos ```FILE: ...``` se precisar alterar HTML, CSS e JS juntos.
5. Seja objetivo, criativo e priorize alta qualidade estética e usabilidade."""

    cfg = load_config()
    try:
        reply = await call_llm(prompt, system_prompt, history, cfg)
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "message": f"Erro na IA: {str(e)}"})

    proposals = extract_file_proposals(reply)
    changes = []
    for prop in proposals:
        rel = prop["path"].lstrip("/")
        new_text = prop["content"]
        old_text = read_text_safe(root, rel) or ""
        diff_text = generate_diff(old_text, new_text, rel)
        changes.append({
            "path": rel,
            "content": new_text,
            "diff": diff_text,
            "is_new": not bool(old_text),
            "exists": bool(old_text)
        })

    return {
        "success": True,
        "reply": reply,
        "changes": changes
    }


@app.post("/api/ai/apply")
async def api_ai_apply(request: Request):
    require_auth(request, config)
    try:
        data = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"success": False, "message": "JSON inválido."})

    site = (data.get("site") or "").strip()
    changes = data.get("changes") or []

    if not site:
        return JSONResponse(status_code=400, content={"success": False, "message": "Site não especificado."})
    if not changes:
        return JSONResponse(status_code=400, content={"success": False, "message": "Nenhuma alteração para aplicar."})

    root = get_site_root(site)
    if not root:
        return JSONResponse(status_code=404, content={"success": False, "message": f"Site '{site}' não encontrado."})

    applied_count = 0
    for ch in changes:
        rel_path = ch.get("path", "").lstrip("/")
        content = ch.get("content", "")
        if not rel_path:
            continue
        backup_file(root, rel_path)
        ok = write_text_safe(root, rel_path, content)
        if ok:
            applied_count += 1

    return {
        "success": True,
        "message": f"Sucesso! {applied_count} arquivo(s) atualizado(s) no site '{site}'."
    }


@app.post("/api/ai/rollback")
async def api_ai_rollback(request: Request):
    require_auth(request, config)
    try:
        data = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"success": False, "message": "JSON inválido."})

    site = (data.get("site") or "").strip()
    path = (data.get("path") or "").lstrip("/")

    if not site or not path:
        return JSONResponse(status_code=400, content={"success": False, "message": "Site e caminho são obrigatórios."})

    root = get_site_root(site)
    if not root:
        return JSONResponse(status_code=404, content={"success": False, "message": f"Site '{site}' não encontrado."})

    msg = rollback_file(root, path)
    if msg:
        return {"success": True, "message": f"Arquivo '{path}' restaurado para a versão anterior com sucesso!"}
    else:
        return JSONResponse(status_code=400, content={"success": False, "message": f"Nenhum backup encontrado para '{path}'."})



if __name__ == "__main__":
    import uvicorn
    port = int(config.get("port", 8888))
    host = config.get("host", "0.0.0.0")
    print(f"🍅 TomateCP iniciando em http://{host}:{port}")
    uvicorn.run("app.main:app", host=host, port=port, reload=True)

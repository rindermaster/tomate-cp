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
from app.sites import (
    list_sites, create_site, toggle_site, delete_site, 
    extract_zip_to_site, reload_nginx, test_nginx_syntax
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
if __name__ == "__main__":
    import uvicorn
    port = int(config.get("port", 8888))
    host = config.get("host", "0.0.0.0")
    print(f"🍅 TomateCP iniciando em http://{host}:{port}")
    uvicorn.run("app.main:app", host=host, port=port, reload=True)

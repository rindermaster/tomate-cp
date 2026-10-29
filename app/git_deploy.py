import os
import subprocess
import secrets
from typing import Dict, Any

def generate_webhook_token() -> str:
    return secrets.token_hex(16)

def git_pull(site_path: str, branch: str = "main") -> Dict[str, Any]:
    """
    Executes git pull in the website directory.
    """
    if not os.path.exists(site_path):
        return {"success": False, "message": "Diretório do site não encontrado."}

    git_dir = os.path.join(site_path, ".git")
    if not os.path.exists(git_dir):
        return {"success": False, "message": "Este diretório não é um repositório Git (.git ausente)."}

    try:
        # Pull latest commits
        cmd = f"git -C {site_path} pull origin {branch}"
        proc = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30)

        # Fix permissions
        subprocess.run(["chown", "-R", "www-data:www-data", site_path], timeout=10)

        if proc.returncode == 0:
            return {
                "success": True,
                "output": proc.stdout.strip(),
                "message": "Site atualizado com sucesso via Git!"
            }
        else:
            return {
                "success": False,
                "output": proc.stderr.strip() or proc.stdout.strip(),
                "message": f"Falha no Git Pull: {proc.stderr.strip()}"
            }
    except Exception as e:
        return {"success": False, "message": f"Erro ao executar git pull: {str(e)}"}

def setup_git_repo(site_path: str, repo_url: str, branch: str = "main") -> Dict[str, Any]:
    """
    Clones or links a remote Git repository to the site folder.
    """
    repo_url = repo_url.strip()
    if not repo_url:
        return {"success": False, "message": "URL do repositório é obrigatória."}

    os.makedirs(site_path, exist_ok=True)
    git_dir = os.path.join(site_path, ".git")

    try:
        # If folder is empty, clone directly
        existing_files = os.listdir(site_path)
        if not existing_files:
            cmd = f"git clone -b {branch} {repo_url} {site_path}"
            proc = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60)
            if proc.returncode == 0:
                subprocess.run(["chown", "-R", "www-data:www-data", site_path], timeout=10)
                return {"success": True, "message": "Repositório clonado com sucesso!"}
            else:
                return {"success": False, "message": proc.stderr.strip()}

        # If already has .git, update remote
        if os.path.exists(git_dir):
            subprocess.run(f"git -C {site_path} remote set-url origin {repo_url}", shell=True, timeout=10)
            return git_pull(site_path, branch)

        # If has existing files but no .git, init and fetch
        init_cmds = [
            f"git -C {site_path} init",
            f"git -C {site_path} remote add origin {repo_url}",
            f"git -C {site_path} fetch origin",
            f"git -C {site_path} checkout -f -B {branch} origin/{branch}"
        ]
        full_cmd = " && ".join(init_cmds)
        proc = subprocess.run(full_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60)
        subprocess.run(["chown", "-R", "www-data:www-data", site_path], timeout=10)

        if proc.returncode == 0:
            return {"success": True, "message": "Repositório vinculado e sincronizado com sucesso!"}
        else:
            return {"success": False, "message": proc.stderr.strip() or proc.stdout.strip()}
    except Exception as e:
        return {"success": False, "message": f"Erro na configuração do Git: {str(e)}"}

"""
🍅 TomateCP - AI Agent Service (Agente Tomate IA)
Ultra-lightweight conversational website editor & developer agent.
Connects to OpenRouter (Cohere, DeepSeek, Llama, Qwen, Claude, GPT), Ollama local, or Groq.
"""

import os
import json
import difflib
import time
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional
import httpx

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config" / "config.json"
BACKUP_DIR = Path("/tmp/tomate_ai_backups")
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {
    ".html", ".htm", ".css", ".js", ".php", ".json", ".txt", ".md",
    ".svg", ".xml", ".sql", ".conf", ".env", ".yaml", ".yml"
}

IGNORED_DIRS = {
    ".git", "node_modules", "vendor", "venv", ".idea", ".vscode",
    "__pycache__", "cache", "uploads", "logs"
}

POPULAR_MODELS = [
    {
        "id": "cohere/north-mini-code:free",
        "name": "Cohere North Mini Code (Grátis)",
        "badge": "100% Grátis",
        "description": "Modelo de código rápido e eficiente do OpenRouter com cota gratuita diária."
    },
    {
        "id": "google/gemma-4-26b-a4b-it:free",
        "name": "Google Gemma 4 26B (Grátis)",
        "badge": "100% Grátis",
        "description": "Excelente para lógica de programação e estruturação web."
    },
    {
        "id": "meta-llama/llama-3.3-70b-instruct:free",
        "name": "Meta Llama 3.3 70B (Grátis)",
        "badge": "100% Grátis",
        "description": "Modelo poderoso de 70 bilhões de parâmetros da Meta."
    },
    {
        "id": "deepseek/deepseek-chat",
        "name": "DeepSeek V3 (Recomendado)",
        "badge": "Super Barato",
        "description": "Excelente raciocínio e código por centavos por milhão de tokens."
    },
    {
        "id": "qwen/qwen-2.5-coder-32b-instruct",
        "name": "Qwen 2.5 Coder 32B",
        "badge": "Especialista em Código",
        "description": "Um dos melhores modelos de código abertos do mundo."
    },
    {
        "id": "openai/gpt-4o-mini",
        "name": "OpenAI GPT-4o Mini",
        "badge": "Rápido & Inteligente",
        "description": "Modelo veloz e refinado da OpenAI via OpenRouter."
    },
    {
        "id": "anthropic/claude-3.5-sonnet",
        "name": "Anthropic Claude 3.5 Sonnet",
        "badge": "Padrão Ouro",
        "description": "Líder absoluto em engenharia de software e design de interfaces."
    }
]

def load_config() -> Dict[str, Any]:
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_config(cfg: Dict[str, Any]):
    os.makedirs(CONFIG_PATH.parent, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

def mask_api_key(key: str) -> str:
    if not key or len(key) < 10:
        return ""
    return f"{key[:7]}...{key[-4:]}"

def get_site_root(domain: str) -> Optional[Path]:
    cfg = load_config()
    www_root = Path(cfg.get("www_root_dir", "/var/www"))
    
    # 1. Direct path /var/www/domain
    candidate = www_root / domain
    if candidate.exists() and candidate.is_dir():
        return candidate
        
    # 2. Check in /var/www root itself if special
    if domain in ("_root", "www", "global"):
        return www_root
        
    # 3. If exists anywhere in www_root
    for p in www_root.iterdir():
        if p.is_dir() and p.name == domain:
            return p
            
    return candidate if candidate.exists() else None

def scan_site_files(root: Path, max_files: int = 60) -> List[Dict[str, Any]]:
    results = []
    if not root.exists():
        return results
        
    for p in root.rglob("*"):
        if p.is_dir():
            continue
        rel = p.relative_to(root)
        if any(part in IGNORED_DIRS for part in rel.parts):
            continue
        if p.suffix.lower() in ALLOWED_EXTENSIONS:
            try:
                results.append({
                    "path": str(rel),
                    "size": p.stat().st_size,
                    "ext": p.suffix.lower()
                })
            except Exception:
                continue
        if len(results) >= max_files:
            break
            
    # Sort with index.html, style.css, script.js first
    def priority_sort(item):
        path = item["path"].lower()
        if "index.html" in path: return 0
        if "style.css" in path: return 1
        if "main.js" in path or "script.js" in path: return 2
        return 10
        
    results.sort(key=priority_sort)
    return results

def read_text_safe(root: Path, rel_path: str, max_bytes: int = 40000) -> Optional[str]:
    target = (root / rel_path).resolve()
    # Path traversal protection
    if not str(target).startswith(str(root.resolve())):
        return None
    if not target.exists() or not target.is_file():
        return None
    try:
        with open(target, "r", encoding="utf-8", errors="replace") as f:
            return f.read(max_bytes)
    except Exception:
        return None

def write_text_safe(root: Path, rel_path: str, content: str) -> bool:
    target = (root / rel_path).resolve()
    if not str(target).startswith(str(root.resolve())):
        return False
        
    # Backup before write
    backup_file(root, rel_path)
    
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        f.write(content)
        
    # Set proper permissions (0644) and www-data ownership if on Linux
    try:
        os.chmod(target, 0o644)
        shutil.chown(target, user="www-data", group="www-data")
    except Exception:
        pass
    return True

def backup_file(root: Path, rel_path: str):
    target = root / rel_path
    if not target.exists():
        return
    site_name = root.name
    site_backup_dir = BACKUP_DIR / site_name
    site_backup_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = int(time.time())
    safe_name = rel_path.replace("/", "_")
    bak_path = site_backup_dir / f"{safe_name}.{timestamp}.bak"
    try:
        shutil.copy2(target, bak_path)
        # Keep last 15 backups
        baks = sorted(site_backup_dir.glob(f"{safe_name}.*.bak"), key=lambda x: x.stat().st_mtime)
        if len(baks) > 15:
            for old in baks[:-15]:
                try: old.unlink()
                except Exception: pass
    except Exception:
        pass

def rollback_file(root: Path, rel_path: str) -> Optional[str]:
    site_name = root.name
    site_backup_dir = BACKUP_DIR / site_name
    safe_name = rel_path.replace("/", "_")
    baks = sorted(site_backup_dir.glob(f"{safe_name}.*.bak"), key=lambda x: x.stat().st_mtime)
    if not baks:
        return None
    latest_bak = baks[-1]
    target = root / rel_path
    shutil.copy2(latest_bak, target)
    try: latest_bak.unlink()
    except Exception: pass
    return str(target)

def generate_diff(old_content: str, new_content: str, filename: str) -> str:
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)
    diff = difflib.unified_diff(
        old_lines, new_lines,
        fromfile=f"a/{filename}",
        tofile=f"b/{filename}",
        n=3
    )
    return "".join(diff)

async def call_llm(
    prompt: str,
    system_prompt: str,
    chat_history: List[Dict[str, str]],
    config: Dict[str, Any]
) -> str:
    provider = config.get("ai_provider", "openrouter")
    model = config.get("ai_model", "cohere/north-mini-code:free")
    api_key = config.get("openrouter_api_key", "").strip()
    
    messages = [{"role": "system", "content": system_prompt}]
    for msg in chat_history[-6:]:
        messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})
    messages.append({"role": "user", "content": prompt})

    if provider == "openrouter":
        if not api_key:
            raise ValueError("Chave de API do OpenRouter não configurada. Insira sua chave nas configurações.")
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://tomatecp.zipdigital.site",
            "X-Title": "TomateCP Mini Server AI Agent"
        }
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.2
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code != 200:
                err_data = resp.json().get("error", {}) if resp.text.startswith("{") else {}
                err_msg = err_data.get("message", resp.text)
                raise RuntimeError(f"OpenRouter Error ({resp.status_code}): {err_msg}")
            data = resp.json()
            return data["choices"][0]["message"]["content"]
            
    elif provider == "ollama":
        base_url = config.get("ollama_base_url", "http://127.0.0.1:11434").rstrip("/")
        url = f"{base_url}/v1/chat/completions"
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.2
        }
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code != 200:
                raise RuntimeError(f"Ollama Error ({resp.status_code}): {resp.text}")
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    else:
        raise ValueError(f"Provedor '{provider}' não suportado.")

def extract_file_proposals(llm_output: str) -> List[Dict[str, str]]:
    """
    Find blocks of format:
    ```FILE: path/to/file.ext
    ...content...
    ```
    """
    proposals = []
    lines = llm_output.split("\n")
    in_file = False
    current_path = ""
    current_content = []
    
    for line in lines:
        stripped = line.strip()
        if not in_file:
            if stripped.startswith("```FILE:") or stripped.startswith("```file:") or stripped.startswith("### FILE:"):
                current_path = stripped.split(":", 1)[1].strip()
                in_file = True
                current_content = []
        else:
            if stripped == "```":
                in_file = False
                proposals.append({
                    "path": current_path,
                    "content": "\n".join(current_content)
                })
                current_path = ""
                current_content = []
            else:
                current_content.append(line)
                
    return proposals

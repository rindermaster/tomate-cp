"""
🍅 TomateCP - AI Agent Service (Agente Tomate IA)
Ultra-lightweight conversational website editor & developer agent.
Connects to OpenRouter (Cohere, DeepSeek, Llama, Qwen, Claude, GPT), Ollama local, or Groq.
"""

import os
import re
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
        if p.name.endswith(".min.js") or p.name.endswith(".min.css") or p.name.endswith(".map"):
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

def read_text_safe(root: Path, rel_path: str, max_bytes: int = 150000) -> Optional[str]:
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
    
    pattern = re.compile(r"^[\\`#*\s]*(?:[a-zA-Z0-9_-]+\s+)?FILE:\s*([^\s`]+)", re.IGNORECASE)

    for line in lines:
        stripped = line.strip()
        if not in_file:
            m = pattern.match(stripped)
            if m:
                current_path = m.group(1).strip("`* :")
                in_file = True
                current_content = []
        else:
            if stripped.startswith("```") or stripped.startswith("\\```") or (stripped.startswith("###") and "FILE:" in stripped):
                in_file = False
                proposals.append({
                    "path": current_path,
                    "content": "\n".join(current_content)
                })
                current_path = ""
                current_content = []
                # Check if this line starts another file proposal immediately
                m = pattern.match(stripped)
                if m:
                    current_path = m.group(1).strip("`* :")
                    in_file = True
            else:
                current_content.append(line)

    if in_file and current_content:
        proposals.append({
            "path": current_path,
            "content": "\n".join(current_content)
        })

    return proposals


LAZY_PLACEHOLDER_REGEX = re.compile(
    r"(?:<!--|/\*|//|\.\.\.)\s*(?:rest|restante|demais|continua|permanece|resto da página|rest of code)\b",
    re.IGNORECASE
)

def apply_search_replace(original_text: str, search: str, replace: str) -> tuple[str, bool]:
    """
    Aplica substituição cirúrgica com 4 níveis de tolerância:
    1. Match exato
    2. Normalização CRLF/LF
    3. Tolerância a espaços no fim de linha (rstrip)
    4. Tolerância a indentação (strip)
    """
    if not search:
        return original_text, False

    # 1. Match exato
    if search in original_text:
        return original_text.replace(search, replace, 1), True

    # 2. Normalização de quebras de linha
    norm_orig = original_text.replace("\r\n", "\n")
    norm_search = search.replace("\r\n", "\n")
    norm_replace = replace.replace("\r\n", "\n")
    if norm_search in norm_orig:
        return norm_orig.replace(norm_search, norm_replace, 1), True

    # 3. Tolerância a espaços em branco no final de linhas
    search_lines = [l.rstrip() for l in norm_search.split("\n")]
    orig_lines = [l.rstrip() for l in norm_orig.split("\n")]
    actual_orig_lines = norm_orig.split("\n")
    
    n_search = len(search_lines)
    if n_search <= len(orig_lines):
        for i in range(len(orig_lines) - n_search + 1):
            if orig_lines[i:i + n_search] == search_lines:
                before = actual_orig_lines[:i]
                after = actual_orig_lines[i + n_search:]
                res = "\n".join(before + [norm_replace] + after)
                return res, True

    # 4. Tolerância a indentação geral
    stripped_search = [l.strip() for l in search_lines if l.strip()]
    if stripped_search:
        n_strip = len(stripped_search)
        for i in range(len(orig_lines) - n_strip + 1):
            sub = [orig_lines[i + k].strip() for k in range(n_strip)]
            if sub == stripped_search:
                before = actual_orig_lines[:i]
                after = actual_orig_lines[i + n_strip:]
                res = "\n".join(before + [norm_replace] + after)
                return res, True

    return original_text, False

def process_ai_proposals(reply: str, root: Path) -> List[Dict[str, Any]]:
    """
    Extrai e processa tanto edições pontuais (SEARCH/REPLACE) quanto criação/substituição total (FILE:).
    Garante que arquivos existentes não sejam corrompidos nem apagados.
    """
    changes_by_file: Dict[str, Dict[str, Any]] = {}

    # 1. Procurar blocos SEARCH/UPDATE/PATCH
    block_pattern = re.compile(
        r"[\\`#*\s]*(?:SEARCH|UPDATE|PATCH):\s*([^\s`\n]+)([\s\S]*?)(?=(?:```[a-zA-Z0-9_-]*\r?\n[\\`#*\s]*(?:SEARCH|UPDATE|PATCH|FILE):|[\\`#*\s]*(?:SEARCH|UPDATE|PATCH|FILE):|\Z))",
        re.IGNORECASE
    )
    pair_pattern = re.compile(
        r"(?:<{5,}\s*SEARCH\r?\n)?([\s\S]*?)\r?\n={5,}\r?\n([\s\S]*?)(?=\r?\n>{5,}\s*REPLACE|\r?\n```|\Z)",
        re.IGNORECASE
    )

    for m in block_pattern.finditer(reply):
        path = m.group(1).strip("`* :").lstrip("/")
        body = m.group(2)
        pairs = list(pair_pattern.finditer(body))
        if not pairs:
            continue
        if path not in changes_by_file:
            changes_by_file[path] = {"type": "patch", "pairs": []}
        for p in pairs:
            s_text = p.group(1)
            r_text = p.group(2)
            # Remove any trailing fence if captured
            r_text = re.sub(r"\n```\s*$", "", r_text)
            if s_text.strip() and r_text.strip():
                changes_by_file[path]["pairs"].append({
                    "search": s_text,
                    "replace": r_text
                })

    # Fallback para <<<<<<< SEARCH arquivo.ext
    generic_sr = re.compile(
        r"<{5,}\s*SEARCH\s+([^\s\n]+)\r?\n([\s\S]*?)\r?\n={5,}\r?\n([\s\S]*?)\r?\n>{5,}\s*REPLACE",
        re.IGNORECASE
    )
    for m in generic_sr.finditer(reply):
        path = m.group(1).strip("`* :").lstrip("/")
        if path not in changes_by_file:
            changes_by_file[path] = {"type": "patch", "pairs": []}
        changes_by_file[path]["pairs"].append({
            "search": m.group(2),
            "replace": m.group(3)
        })

    # 2. Procurar blocos FILE: (para novos arquivos ou regravação completa)
    file_pattern = re.compile(
        r"[\\`#*\s]*(?:CREATE\s+)?FILE:\s*([^\s`\n]+)\r?\n([\s\S]*?)(?=\r?\n[\\`#*\s]*(?:FILE:|SEARCH:|UPDATE:|PATCH:|$)|```|\Z)",
        re.IGNORECASE
    )
    for m in file_pattern.finditer(reply):
        path = m.group(1).strip("`* :").lstrip("/")
        content = m.group(2).strip("\r\n")
        content = re.sub(r"\n```\s*$", "", content)
        if path not in changes_by_file:
            changes_by_file[path] = {
                "type": "file",
                "content": content
            }

    results = []
    for rel_path, data in changes_by_file.items():
        old_text = read_text_safe(root, rel_path, max_bytes=250000) or ""

        if data["type"] == "patch":
            current_text = old_text
            matched_count = 0
            failed_count = 0
            for pair in data["pairs"]:
                current_text, ok = apply_search_replace(current_text, pair["search"], pair["replace"])
                if ok:
                    matched_count += 1
                else:
                    failed_count += 1

            diff_text = generate_diff(old_text, current_text, rel_path)
            results.append({
                "path": rel_path,
                "content": current_text,
                "diff": diff_text,
                "is_new": not bool(old_text),
                "exists": bool(old_text),
                "edit_mode": "patch",
                "matched_blocks": matched_count,
                "failed_blocks": failed_count,
                "has_lazy_placeholder": False
            })
        else:
            new_text = data["content"]
            has_lazy = False
            if old_text and len(old_text) > 400:
                if LAZY_PLACEHOLDER_REGEX.search(new_text) or (len(new_text) < len(old_text) * 0.35 and len(new_text) < 1000):
                    has_lazy = True

            diff_text = generate_diff(old_text, new_text, rel_path)
            results.append({
                "path": rel_path,
                "content": new_text,
                "diff": diff_text,
                "is_new": not bool(old_text),
                "exists": bool(old_text),
                "edit_mode": "full",
                "matched_blocks": 1,
                "failed_blocks": 0,
                "has_lazy_placeholder": has_lazy
            })

    return results

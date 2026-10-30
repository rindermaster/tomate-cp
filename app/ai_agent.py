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

PROVIDERS_CONFIG = {
    "groq": {
        "id": "groq",
        "name": "Groq Cloud (100% Gratuito & Ultra-Rápido)",
        "badge": "Recomendado Grátis",
        "description": "Velocidade extrema de até 500 tokens/segundo. Cota gratuita sem necessidade de cartão de crédito.",
        "api_url": "https://api.groq.com/openai/v1/chat/completions",
        "key_field": "groq_api_key",
        "key_name": "Chave de API do Groq",
        "key_placeholder": "gsk_...",
        "key_url": "https://console.groq.com/keys",
        "key_help": "Crie sua conta gratuita no Groq Cloud e gere uma chave de API em menos de 1 minuto sem cartão de crédito.",
        "default_model": "qwen/qwen3.8-27b",
        "models": [
            {
                "id": "qwen/qwen3.8-27b",
                "name": "Qwen 3.8 27B (Recomendado)",
                "badge": "100% Grátis • Especialista em Código",
                "description": "Última geração Qwen no Groq. Excelente raciocínio e síntese de código para desenvolvimento web."
            },
            {
                "id": "openai/gpt-oss-120b",
                "name": "OpenAI GPT OSS 120B",
                "badge": "100% Grátis • Raciocínio Profundo",
                "description": "Modelo massivo de 120B parâmetros de código aberto no Groq para problemas complexos."
            },
            {
                "id": "openai/gpt-oss-20b",
                "name": "OpenAI GPT OSS 20B",
                "badge": "100% Grátis • Super Veloz",
                "description": "Respostas ultrarrápidas em milissegundos para correções pontuais e edições de código."
            }
        ]
    },
    "openrouter": {
        "id": "openrouter",
        "name": "OpenRouter (Grátis + Modelos Comerciais)",
        "badge": "Múltiplos Modelos",
        "description": "Hub completo com modelos 100% gratuitos (:free) e líderes mundiais (Claude 3.5, GPT-4o, DeepSeek).",
        "api_url": "https://openrouter.ai/api/v1/chat/completions",
        "key_field": "openrouter_api_key",
        "key_name": "Chave de API do OpenRouter",
        "key_placeholder": "sk-or-v1-...",
        "key_url": "https://openrouter.ai/keys",
        "key_help": "Gere sua chave no OpenRouter. Modelos com sufixo :free são 100% gratuitos.",
        "default_model": "meta-llama/llama-3.3-70b-instruct:free",
        "models": [
            {
                "id": "meta-llama/llama-3.3-70b-instruct:free",
                "name": "Meta Llama 3.3 70B (Grátis)",
                "badge": "100% Grátis",
                "description": "Modelo poderoso de 70 bilhões de parâmetros da Meta sem custo."
            },
            {
                "id": "google/gemma-4-26b-a4b-it:free",
                "name": "Google Gemma 4 26B (Grátis)",
                "badge": "100% Grátis",
                "description": "Excelente para lógica de programação e estruturação web."
            },
            {
                "id": "cohere/north-mini-code:free",
                "name": "Cohere North Mini Code (Grátis)",
                "badge": "100% Grátis",
                "description": "Modelo de código rápido e eficiente com cota diária gratuita."
            },
            {
                "id": "deepseek/deepseek-chat",
                "name": "DeepSeek V3 (Recomendado)",
                "badge": "Super Barato",
                "description": "Excelente raciocínio e código por centavos por milhão de tokens."
            },
            {
                "id": "anthropic/claude-3.5-sonnet",
                "name": "Anthropic Claude 3.5 Sonnet",
                "badge": "Padrão Ouro",
                "description": "Líder absoluto em engenharia de software e design de interfaces."
            },
            {
                "id": "openai/gpt-4o-mini",
                "name": "OpenAI GPT-4o Mini",
                "badge": "Rápido & Inteligente",
                "description": "Modelo veloz e refinado da OpenAI."
            }
        ]
    },
    "gemini": {
        "id": "gemini",
        "name": "Google Gemini (Gratuito no Google AI Studio)",
        "badge": "Grátis no AI Studio",
        "description": "Conexão direta com a API do Google Gemini com limites gratuitos generosos de uso.",
        "api_url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "key_field": "gemini_api_key",
        "key_name": "Chave de API do Google AI Studio",
        "key_placeholder": "AIzaSy...",
        "key_url": "https://aistudio.google.com/app/apikey",
        "key_help": "Gere sua API key gratuitamente no Google AI Studio (requer conta Google).",
        "default_model": "gemini-1.5-flash",
        "models": [
            {
                "id": "gemini-1.5-flash",
                "name": "Google Gemini 1.5 Flash",
                "badge": "Grátis • Super Veloz",
                "description": "Velocidade impressionante com janela de contexto enorme."
            },
            {
                "id": "gemini-2.0-flash-exp",
                "name": "Google Gemini 2.0 Flash (Experimental)",
                "badge": "Nova Geração • Grátis",
                "description": "Último lançamento do Google, altamente capaz para programação."
            },
            {
                "id": "gemini-1.5-pro",
                "name": "Google Gemini 1.5 Pro",
                "badge": "Raciocínio Avançado",
                "description": "Alta capacidade analítica para arquitetura de projetos e código complexo."
            }
        ]
    },
    "deepseek": {
        "id": "deepseek",
        "name": "DeepSeek Oficial (api.deepseek.com)",
        "badge": "Super Econômico",
        "description": "Acesso direto à API original da DeepSeek com custo irrisório e alta qualidade.",
        "api_url": "https://api.deepseek.com/chat/completions",
        "key_field": "deepseek_api_key",
        "key_name": "Chave de API da DeepSeek",
        "key_placeholder": "sk-...",
        "key_url": "https://platform.deepseek.com/api_keys",
        "key_help": "Adicione créditos na plataforma oficial da DeepSeek (R$ 10 duram meses).",
        "default_model": "deepseek-chat",
        "models": [
            {
                "id": "deepseek-chat",
                "name": "DeepSeek V3 (Chat / Coder)",
                "badge": "Melhor Custo-Benefício",
                "description": "Modelo de 671B parâmetros de última geração."
            },
            {
                "id": "deepseek-reasoner",
                "name": "DeepSeek R1 (Raciocínio Profundo)",
                "badge": "Pensamento Passo a Passo",
                "description": "Gera cadeia de raciocínio antes de produzir o código final."
            }
        ]
    },
    "xai": {
        "id": "xai",
        "name": "xAI Grok Oficial (api.x.ai)",
        "badge": "Grok Oficial",
        "description": "API oficial do Grok desenvolvida pela xAI de Elon Musk.",
        "api_url": "https://api.x.ai/v1/chat/completions",
        "key_field": "xai_api_key",
        "key_name": "Chave de API da xAI",
        "key_placeholder": "xai-...",
        "key_url": "https://console.x.ai/",
        "key_help": "Gere sua chave de API no console oficial da xAI.",
        "default_model": "grok-2-latest",
        "models": [
            {
                "id": "grok-2-latest",
                "name": "Grok 2 Latest",
                "badge": "Poderoso & Atual",
                "description": "Modelo topo de linha da xAI para desenvolvimento e raciocínio."
            },
            {
                "id": "grok-beta",
                "name": "Grok Beta",
                "badge": "Rápido",
                "description": "Versão otimizada para respostas rápidas de código."
            }
        ]
    },
    "ollama": {
        "id": "ollama",
        "name": "Ollama (Servidor Local na Rede)",
        "badge": "Rede Local",
        "description": "Conecta a qualquer computador na sua rede local (ex: seu PC ou Mac) rodando Ollama.",
        "api_url": "",
        "key_field": "",
        "key_name": "",
        "key_placeholder": "",
        "key_url": "https://ollama.com",
        "key_help": "Instale o Ollama no seu PC/Mac e execute 'ollama run qwen2.5-coder:7b'. Insira o IP do seu PC.",
        "default_model": "qwen2.5-coder:7b",
        "models": [
            {
                "id": "qwen2.5-coder:7b",
                "name": "Qwen 2.5 Coder 7B (Local)",
                "badge": "Especialista em Código",
                "description": "Roda no seu PC/Mac conectado na mesma rede."
            },
            {
                "id": "deepseek-coder:6.7b",
                "name": "DeepSeek Coder 6.7B (Local)",
                "badge": "Código",
                "description": "Modelo clássico de código aberto."
            },
            {
                "id": "llama3.2:3b",
                "name": "Llama 3.2 3B (Local)",
                "badge": "Leve",
                "description": "Modelo ultraleve para PCs mais modestos."
            }
        ]
    }
}

# Backward compatibility alias
POPULAR_MODELS = PROVIDERS_CONFIG["groq"]["models"] + PROVIDERS_CONFIG["openrouter"]["models"]

DEPRECATED_MODELS_FALLBACK = {
    "llama-3.3-70b-versatile": "qwen/qwen3.8-27b",
    "qwen-2.5-coder-32b": "qwen/qwen3.8-27b",
    "llama-3.1-8b-instant": "openai/gpt-oss-20b",
    "llama-3.1-70b-versatile": "openai/gpt-oss-120b",
    "llama3-70b-8192": "openai/gpt-oss-120b",
    "llama3-8b-8192": "openai/gpt-oss-20b",
    "mixtral-8x7b-32768": "qwen/qwen3.8-27b",
    "gemma-7b-it": "qwen/qwen3.8-27b",
    "gemma2-9b-it": "qwen/qwen3.8-27b",
}

def has_configured_key(cfg: Dict[str, Any], provider: str) -> bool:
    if provider == "ollama":
        return True
    prov = PROVIDERS_CONFIG.get(provider)
    if not prov:
        return False
    field = prov.get("key_field", f"{provider}_api_key")
    key = (cfg.get(field) or "").strip()
    if not key and provider == "openrouter":
        key = (cfg.get("openrouter_api_key") or "").strip()
    return bool(key)

def get_masked_keys(cfg: Dict[str, Any]) -> Dict[str, str]:
    res = {}
    for pid, pdata in PROVIDERS_CONFIG.items():
        field = pdata.get("key_field")
        if field:
            val = (cfg.get(field) or "").strip()
            if not val and pid == "openrouter":
                val = (cfg.get("openrouter_api_key") or "").strip()
            res[pid] = mask_api_key(val) if val else ""
    return res


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
    provider = config.get("ai_provider", "groq")
    if provider not in PROVIDERS_CONFIG:
        provider = "groq"
    prov_meta = PROVIDERS_CONFIG[provider]

    model = config.get("ai_model")
    if not model or model == "custom":
        model = prov_meta.get("default_model", "qwen/qwen3.8-27b")

    if provider == "groq" and model in DEPRECATED_MODELS_FALLBACK:
        model = DEPRECATED_MODELS_FALLBACK[model]

    messages = [{"role": "system", "content": system_prompt}]
    for msg in chat_history[-6:]:
        messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.2
    }

    if provider == "ollama":
        base_url = config.get("ollama_base_url", "http://127.0.0.1:11434").rstrip("/")
        url = f"{base_url}/v1/chat/completions"
        async with httpx.AsyncClient(timeout=90.0) as client:
            try:
                resp = await client.post(url, json=payload, headers={"Content-Type": "application/json"})
            except Exception as conn_err:
                raise RuntimeError(
                    f"Não foi possível conectar ao servidor Ollama em '{base_url}'. "
                    f"Verifique se o Ollama está rodando no computador da rede e se o firewall permite a porta 11434. ({conn_err})"
                )
            if resp.status_code != 200:
                raise RuntimeError(f"Ollama Error ({resp.status_code}): {resp.text}")
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    # Provedores de API na Nuvem (Groq, OpenRouter, Gemini, DeepSeek, xAI)
    field = prov_meta.get("key_field", f"{provider}_api_key")
    api_key = (config.get(field) or "").strip()
    if not api_key and provider == "openrouter":
        api_key = (config.get("openrouter_api_key") or "").strip()

    if not api_key:
        prov_name = prov_meta.get("name", provider)
        key_url = prov_meta.get("key_url", "")
        raise ValueError(
            f"⚠️ Chave de API não configurada para o provedor '{prov_name}'.\n"
            f"Por favor, abra as Configurações de IA (⚙️) no topo do painel e insira sua chave gratuita ou comercial.\n"
            f"Link para obter sua chave: {key_url}"
        )

    url = prov_meta.get("api_url")
    if not url:
        raise ValueError(f"URL de API não definida para o provedor '{provider}'.")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    if provider == "openrouter":
        headers["HTTP-Referer"] = "https://tomatecp.zipdigital.site"
        headers["X-Title"] = "TomateCP Mini Server AI Agent"

    async with httpx.AsyncClient(timeout=90.0) as client:
        try:
            resp = await client.post(url, json=payload, headers=headers)
        except Exception as net_err:
            raise RuntimeError(f"Erro de conexão com o provedor {prov_meta.get('name')}: {str(net_err)}")

        if resp.status_code in (400, 404) and provider == "groq" and model != "qwen/qwen3.8-27b":
            # Auto-recuperação: se o Groq desativou o modelo, tenta automaticamente o Qwen 3.8 27B
            fallback_model = "qwen/qwen3.8-27b"
            retry_payload = {**payload, "model": fallback_model}
            try:
                retry_resp = await client.post(url, json=retry_payload, headers=headers)
                if retry_resp.status_code == 200:
                    try:
                        cfg = load_config()
                        cfg["ai_model"] = fallback_model
                        save_config(cfg)
                    except Exception:
                        pass
                    data = retry_resp.json()
                    return data["choices"][0]["message"]["content"]
            except Exception:
                pass

        if resp.status_code != 200:
            err_data = resp.json().get("error", {}) if resp.text.startswith("{") else {}
            if isinstance(err_data, dict):
                err_msg = err_data.get("message", resp.text)
            else:
                err_msg = str(err_data) or resp.text
            raise RuntimeError(f"{prov_meta.get('name', provider)} Error ({resp.status_code}): {err_msg}")

        data = resp.json()
        return data["choices"][0]["message"]["content"]

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
    Aplica substituição cirúrgica com múltiplos níveis de tolerância:
    1. Match exato
    2. Normalização CRLF/LF
    3. Tolerância a quebras de linha nas bordas do bloco (strip)
    4. Tolerância a espaços no fim de linha (rstrip)
    5. Tolerância a indentação geral (strip por linha)
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

    # 3. Tolerância a quebras de linha / espaços extras no topo ou base do search
    trimmed_search = norm_search.strip("\r\n")
    if trimmed_search and trimmed_search in norm_orig:
        return norm_orig.replace(trimmed_search, norm_replace.strip("\r\n"), 1), True

    # 4. Tolerância a espaços em branco no final de linhas
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

    # 5. Tolerância a indentação geral
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

    # 1. Procurar blocos SEARCH/UPDATE/PATCH:
    block_pattern = re.compile(
        r"[\\`#*\s]*(?:SEARCH|UPDATE|PATCH):\s*([^\s`\n]+)([\s\S]*?)(?=(?:```[a-zA-Z0-9_-]*\r?\n[\\`#*\s]*(?:SEARCH|UPDATE|PATCH|FILE):|[\\`#*\s]*(?:SEARCH|UPDATE|PATCH|FILE):|\Z))",
        re.IGNORECASE
    )
    pair_pattern = re.compile(
        r"[ \t]*<{3,}\s*SEARCH[^\n]*\r?\n([\s\S]*?)\r?\n[ \t]*={3,}\r?\n([\s\S]*?)(?=\r?\n[ \t]*>{3,}\s*REPLACE|\r?\n```|\Z)",
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
            # Remove qualquer fechamento residual de replace ou fence
            r_text = re.sub(r"\r?\n[ \t]*>{3,}\s*REPLACE[^\n]*$", "", r_text, flags=re.IGNORECASE)
            r_text = re.sub(r"\r?\n```\s*$", "", r_text)
            if s_text.strip() and r_text.strip():
                changes_by_file[path]["pairs"].append({
                    "search": s_text,
                    "replace": r_text
                })

    # Fallback para <<<<<<< SEARCH arquivo.ext
    generic_sr = re.compile(
        r"[ \t]*<{3,}\s*SEARCH\s+([^\s\n]+)\r?\n([\s\S]*?)\r?\n[ \t]*={3,}\r?\n([\s\S]*?)(?=\r?\n[ \t]*>{3,}\s*REPLACE|\r?\n```|\Z)",
        re.IGNORECASE
    )
    for m in generic_sr.finditer(reply):
        path = m.group(1).strip("`* :").lstrip("/")
        if path not in changes_by_file:
            changes_by_file[path] = {"type": "patch", "pairs": []}
        changes_by_file[path]["pairs"].append({
            "search": m.group(2),
            "replace": re.sub(r"\r?\n[ \t]*>{3,}\s*REPLACE[^\n]*$", "", m.group(3), flags=re.IGNORECASE)
        })

    # Fallback para SEARCH/REPLACE sem nome de arquivo explícito
    if not changes_by_file:
        unnamed_sr = re.compile(
            r"[ \t]*<{3,}\s*SEARCH\s*\r?\n([\s\S]*?)\r?\n[ \t]*={3,}\r?\n([\s\S]*?)(?=\r?\n[ \t]*>{3,}\s*REPLACE|\r?\n```|\Z)",
            re.IGNORECASE
        )
        unnamed_pairs = list(unnamed_sr.finditer(reply))
        if unnamed_pairs:
            default_path = "index.html"
            changes_by_file[default_path] = {"type": "patch", "pairs": []}
            for p in unnamed_pairs:
                changes_by_file[default_path]["pairs"].append({
                    "search": p.group(1),
                    "replace": re.sub(r"\r?\n[ \t]*>{3,}\s*REPLACE[^\n]*$", "", p.group(2), flags=re.IGNORECASE)
                })

    # 2. Procurar blocos FILE: (para novos arquivos ou regravação completa)
    file_pattern = re.compile(
        r"(?:```[a-zA-Z0-9_-]*\s*)?[\\`#*\s]*(?:CREATE\s+)?FILE:\s*([^\s`\n]+)\r?\n([\s\S]*?)(?=\r?\n[\\`#*\s]*(?:FILE:|SEARCH:|UPDATE:|PATCH:|$)|```|\Z)",
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

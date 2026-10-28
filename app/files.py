"""
TomateCP File Manager & Code Editor Service
Zero-bloat, secure file operations for web hosting environments.
"""

import os
import shutil
import zipfile
import datetime
from typing import Tuple, List, Dict, Any, Optional, Union

DEFAULT_ALLOWED_ROOTS = ["/var/www", "/etc/nginx/sites-available"]

# Text extensions allowed for web code editor
EDITABLE_EXTENSIONS = {
    ".html", ".htm", ".css", ".scss", ".less", ".js", ".mjs", ".ts",
    ".json", ".php", ".phtml", ".py", ".txt", ".md", ".env", ".conf",
    ".nginx", ".yml", ".yaml", ".xml", ".svg", ".sh", ".ini", ".htaccess",
    ".sql", ".log"
}

IMAGE_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico", ".bmp"
}

MODE_MAP = {
    ".html": "htmlmixed",
    ".htm": "htmlmixed",
    ".phtml": "php",
    ".php": "php",
    ".js": "javascript",
    ".mjs": "javascript",
    ".ts": "javascript",
    ".json": "javascript",
    ".css": "css",
    ".scss": "css",
    ".less": "css",
    ".py": "python",
    ".conf": "nginx",
    ".nginx": "nginx",
    ".md": "markdown",
    ".xml": "xml",
    ".svg": "xml",
    ".sh": "shell",
}


def format_size(size_bytes: int) -> str:
    """Formats file size into human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def is_safe_path(target_path: str, allowed_roots: Optional[List[str]] = None) -> bool:
    """
    Validates that target_path is within one of the allowed roots,
    preventing directory traversal attacks.
    """
    if allowed_roots is None:
        allowed_roots = DEFAULT_ALLOWED_ROOTS

    try:
        resolved_target = os.path.realpath(target_path)
    except Exception:
        return False

    for root in allowed_roots:
        resolved_root = os.path.realpath(root)
        # Check if resolved_target is the root or inside the root
        if resolved_target == resolved_root:
            return True
        try:
            if os.path.commonpath([resolved_target, resolved_root]) == resolved_root:
                return True
        except ValueError:
            # Different drives on Windows or invalid paths
            continue

    return False


def get_file_type_info(filename: str, is_dir: bool) -> Dict[str, Any]:
    """Returns classification, editor eligibility, and icon category for UI."""
    if is_dir:
        return {
            "type": "folder",
            "is_editable": False,
            "is_image": False,
            "icon_color": "#F59E0B"
        }

    ext = os.path.splitext(filename)[1].lower()
    is_editable = ext in EDITABLE_EXTENSIONS
    is_image = ext in IMAGE_EXTENSIONS

    icon_color = "#94A3B8"
    if ext in [".html", ".htm"]:
        icon_color = "#F97316"
    elif ext in [".css", ".scss"]:
        icon_color = "#38BDF8"
    elif ext in [".js", ".mjs", ".ts", ".json"]:
        icon_color = "#FACC15"
    elif ext in [".php", ".phtml"]:
        icon_color = "#A855F7"
    elif ext in [".py"]:
        icon_color = "#22C55E"
    elif ext in [".zip", ".tar", ".gz", ".xz"]:
        icon_color = "#EF4444"
    elif is_image:
        icon_color = "#EC4899"

    return {
        "type": ext.lstrip(".") or "file",
        "is_editable": is_editable,
        "is_image": is_image,
        "icon_color": icon_color
    }


def list_directory(target_path: str, allowed_roots: Optional[List[str]] = None) -> Tuple[bool, Union[Dict[str, Any], str]]:
    """Lists files and folders inside target_path with security validation."""
    if not is_safe_path(target_path, allowed_roots):
        return False, "Acesso negado: o caminho solicitado está fora dos diretórios permitidos."

    if not os.path.exists(target_path):
        return False, f"O caminho '{target_path}' não existe."

    if not os.path.isdir(target_path):
        return False, f"'{target_path}' não é um diretório."

    resolved_path = os.path.realpath(target_path)
    
    # Calculate parent path if not at the absolute root of allowed paths
    parent_path = None
    dir_above = os.path.dirname(resolved_path)
    if is_safe_path(dir_above, allowed_roots) and dir_above != resolved_path:
        parent_path = dir_above

    # Build breadcrumbs
    parts = [p for p in resolved_path.split(os.sep) if p]
    breadcrumbs = []
    accum = ""
    for part in parts:
        accum += os.sep + part
        breadcrumbs.append({"name": part, "path": accum})

    items = []
    try:
        with os.scandir(resolved_path) as entries:
            for entry in entries:
                try:
                    stat = entry.stat(follow_symlinks=False)
                    is_dir = entry.is_dir(follow_symlinks=False)
                    info = get_file_type_info(entry.name, is_dir)
                    
                    size = stat.st_size if not is_dir else 0
                    mtime_dt = datetime.datetime.fromtimestamp(stat.st_mtime)
                    mtime_fmt = mtime_dt.strftime("%d/%m/%Y %H:%M")

                    items.append({
                        "name": entry.name,
                        "path": entry.path,
                        "is_dir": is_dir,
                        "size": size,
                        "size_fmt": format_size(size) if not is_dir else "-",
                        "mtime": stat.st_mtime,
                        "mtime_fmt": mtime_fmt,
                        "ext": os.path.splitext(entry.name)[1].lower(),
                        "type": info["type"],
                        "is_editable": info["is_editable"],
                        "is_image": info["is_image"],
                        "icon_color": info["icon_color"],
                    })
                except (PermissionError, FileNotFoundError):
                    continue
    except PermissionError:
        return False, "Permissão negada ao listar o diretório."
    except Exception as e:
        return False, f"Erro ao acessar diretório: {str(e)}"

    # Sort directories first, then alphabetical by name
    items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))

    return True, {
        "current_path": resolved_path,
        "parent_path": parent_path,
        "breadcrumbs": breadcrumbs,
        "items": items,
        "total_items": len(items)
    }


def read_file(file_path: str, max_size_mb: int = 5, allowed_roots: Optional[List[str]] = None) -> Tuple[bool, Union[Dict[str, Any], str]]:
    """Reads a text file for the web code editor."""
    if not is_safe_path(file_path, allowed_roots):
        return False, "Acesso negado: arquivo fora dos diretórios permitidos."

    if not os.path.exists(file_path):
        return False, "Arquivo não encontrado."

    if not os.path.isfile(file_path):
        return False, "O caminho especificado não é um arquivo."

    file_size = os.path.getsize(file_path)
    if file_size > max_size_mb * 1024 * 1024:
        return False, f"Arquivo muito grande ({format_size(file_size)}). O limite do editor é de {max_size_mb} MB."

    ext = os.path.splitext(file_path)[1].lower()
    mode = MODE_MAP.get(ext, "text/plain")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except UnicodeDecodeError:
        try:
            with open(file_path, "r", encoding="latin-1") as f:
                content = f.read()
        except Exception as e:
            return False, f"Não foi possível decodificar o arquivo de texto: {str(e)}"
    except Exception as e:
        return False, f"Erro ao ler arquivo: {str(e)}"

    return True, {
        "path": os.path.realpath(file_path),
        "name": os.path.basename(file_path),
        "content": content,
        "size": file_size,
        "size_fmt": format_size(file_size),
        "mode": mode,
        "ext": ext
    }


def save_file(file_path: str, content: str, allowed_roots: Optional[List[str]] = None) -> Tuple[bool, str]:
    """Saves text content to a file with security checks and safe atomic replacement."""
    if not is_safe_path(file_path, allowed_roots):
        return False, "Acesso negado: caminho fora dos diretórios permitidos."

    parent_dir = os.path.dirname(file_path)
    if not os.path.exists(parent_dir):
        try:
            os.makedirs(parent_dir, exist_ok=True)
        except Exception as e:
            return False, f"Não foi possível criar o diretório pai: {str(e)}"

    temp_path = f"{file_path}.tmp_tomate_{os.getpid()}"
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(content)
        
        # Atomic rename
        os.replace(temp_path, file_path)

        # Set www-data ownership if possible
        try:
            shutil.chown(file_path, user="www-data", group="www-data")
        except Exception:
            pass

        return True, "Arquivo salvo com sucesso!"
    except Exception as e:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        return False, f"Erro ao salvar arquivo: {str(e)}"


def create_file(parent_dir: str, filename: str, allowed_roots: Optional[List[str]] = None) -> Tuple[bool, str]:
    """Creates a new empty file in parent_dir."""
    filename = filename.strip()
    if not filename or "/" in filename or "\\" in filename or ".." in filename:
        return False, "Nome de arquivo inválido."

    target_path = os.path.join(parent_dir, filename)
    if not is_safe_path(target_path, allowed_roots):
        return False, "Acesso negado: caminho fora dos diretórios permitidos."

    if os.path.exists(target_path):
        return False, "Já existe um arquivo ou pasta com este nome."

    try:
        with open(target_path, "w", encoding="utf-8") as f:
            f.write("")
        try:
            shutil.chown(target_path, user="www-data", group="www-data")
        except Exception:
            pass
        return True, f"Arquivo '{filename}' criado com sucesso!"
    except Exception as e:
        return False, f"Erro ao criar arquivo: {str(e)}"


def create_directory(parent_dir: str, dirname: str, allowed_roots: Optional[List[str]] = None) -> Tuple[bool, str]:
    """Creates a new directory inside parent_dir."""
    dirname = dirname.strip()
    if not dirname or "/" in dirname or "\\" in dirname or ".." in dirname:
        return False, "Nome de pasta inválido."

    target_path = os.path.join(parent_dir, dirname)
    if not is_safe_path(target_path, allowed_roots):
        return False, "Acesso negado: caminho fora dos diretórios permitidos."

    if os.path.exists(target_path):
        return False, "Já existe uma pasta ou arquivo com este nome."

    try:
        os.makedirs(target_path, exist_ok=False)
        try:
            shutil.chown(target_path, user="www-data", group="www-data")
        except Exception:
            pass
        return True, f"Pasta '{dirname}' criada com sucesso!"
    except Exception as e:
        return False, f"Erro ao criar pasta: {str(e)}"


def rename_item(item_path: str, new_name: str, allowed_roots: Optional[List[str]] = None) -> Tuple[bool, str]:
    """Renames a file or folder."""
    new_name = new_name.strip()
    if not new_name or "/" in new_name or "\\" in new_name or ".." in new_name:
        return False, "Novo nome inválido."

    if not is_safe_path(item_path, allowed_roots):
        return False, "Acesso negado: caminho de origem inválido."

    if not os.path.exists(item_path):
        return False, "Item não encontrado."

    parent_dir = os.path.dirname(item_path)
    target_path = os.path.join(parent_dir, new_name)

    if not is_safe_path(target_path, allowed_roots):
        return False, "Acesso negado: destino inválido."

    if os.path.exists(target_path):
        return False, f"Já existe um item chamado '{new_name}'."

    try:
        os.rename(item_path, target_path)
        return True, f"Item renomeado para '{new_name}' com sucesso!"
    except Exception as e:
        return False, f"Erro ao renomear: {str(e)}"


def delete_item(item_path: str, allowed_roots: Optional[List[str]] = None) -> Tuple[bool, str]:
    """Deletes a file or directory with safeguards."""
    if not is_safe_path(item_path, allowed_roots):
        return False, "Acesso negado: caminho fora dos diretórios permitidos."

    resolved = os.path.realpath(item_path)
    # Prevent deleting critical roots
    for root in (allowed_roots or DEFAULT_ALLOWED_ROOTS):
        if resolved == os.path.realpath(root):
            return False, "Operação proibida: não é permitido excluir o diretório raiz."

    if not os.path.exists(resolved):
        return False, "Item não encontrado."

    try:
        name = os.path.basename(resolved)
        if os.path.isdir(resolved):
            shutil.rmtree(resolved)
            return True, f"Pasta '{name}' excluída com sucesso."
        else:
            os.remove(resolved)
            return True, f"Arquivo '{name}' excluído com sucesso."
    except Exception as e:
        return False, f"Erro ao excluir: {str(e)}"


def upload_to_directory(parent_dir: str, filename: str, content_bytes: bytes, unzip: bool = False, allowed_roots: Optional[List[str]] = None) -> Tuple[bool, str]:
    """Saves uploaded file into parent_dir, with optional safe zip extraction."""
    filename = os.path.basename(filename).strip()
    if not filename or ".." in filename:
        return False, "Nome de arquivo inválido."

    if not is_safe_path(parent_dir, allowed_roots):
        return False, "Acesso negado: diretório de destino inválido."

    if not os.path.exists(parent_dir) or not os.path.isdir(parent_dir):
        return False, "Diretório de destino não existe."

    dest_path = os.path.join(parent_dir, filename)

    try:
        with open(dest_path, "wb") as f:
            f.write(content_bytes)

        if unzip and filename.lower().endswith(".zip"):
            try:
                with zipfile.ZipFile(dest_path, "r") as zip_ref:
                    for member in zip_ref.namelist():
                        member_name = os.path.basename(member)
                        if not member_name:
                            continue
                        target = os.path.abspath(os.path.join(parent_dir, member))
                        if not target.startswith(os.path.abspath(parent_dir)):
                            return False, "Arquivo ZIP contém caminhos de segurança inválidos."
                    zip_ref.extractall(parent_dir)
                
                # Delete original zip after extraction
                try:
                    os.remove(dest_path)
                except Exception:
                    pass

                try:
                    shutil.chown(parent_dir, user="www-data", group="www-data")
                except Exception:
                    pass
                return True, f"Arquivo '{filename}' enviado e descompactado com sucesso!"
            except Exception as e:
                return False, f"Arquivo salvo, mas falha ao descompactar: {str(e)}"

        try:
            shutil.chown(dest_path, user="www-data", group="www-data")
        except Exception:
            pass

        return True, f"Arquivo '{filename}' enviado com sucesso!"
    except Exception as e:
        return False, f"Erro ao salvar arquivo enviado: {str(e)}"

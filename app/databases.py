import os
import sqlite3
import subprocess
import shutil
import time
from typing import Dict, Any, List

def list_sqlite_databases(base_dir: str = "/var/www") -> List[Dict[str, Any]]:
    """
    Finds all SQLite databases (.sqlite, .sqlite3, .db) inside the web root.
    Zero RAM overhead when idle.
    """
    results = []
    if not os.path.exists(base_dir):
        return results

    valid_exts = {".sqlite", ".sqlite3", ".db"}

    for root, dirs, files in os.walk(base_dir):
        # Ignore git and temp folders
        if ".git" in root or "node_modules" in root:
            continue
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in valid_exts:
                full_path = os.path.join(root, file)
                try:
                    st = os.stat(full_path)
                    # Attempt quick read-only connection to count tables
                    tables = []
                    conn = sqlite3.connect(f"file:{full_path}?mode=ro", uri=True)
                    cursor = conn.cursor()
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
                    tables = [row[0] for row in cursor.fetchall()]
                    conn.close()

                    rel_path = os.path.relpath(full_path, base_dir)
                    results.append({
                        "filename": file,
                        "filepath": full_path,
                        "rel_path": rel_path,
                        "size_kb": round(st.st_size / 1024, 1),
                        "modified": time.strftime("%d/%m/%Y %H:%M", time.localtime(st.st_mtime)),
                        "tables": tables,
                        "table_count": len(tables)
                    })
                except Exception:
                    # Not a valid sqlite file or permission error
                    pass
    return results

def create_sqlite_database(folder_path: str, filename: str) -> Dict[str, Any]:
    """
    Initializes a new empty SQLite database.
    """
    if not filename.endswith(".sqlite") and not filename.endswith(".db"):
        filename += ".sqlite"

    clean_name = os.path.basename(filename)
    full_path = os.path.join(folder_path, clean_name)

    if os.path.exists(full_path):
        return {"success": False, "message": "Já existe um arquivo com esse nome."}

    try:
        os.makedirs(folder_path, exist_ok=True)
        conn = sqlite3.connect(full_path)
        # Create metadata comment/table
        conn.execute("CREATE TABLE IF NOT EXISTS _tomate_meta (id INTEGER PRIMARY KEY, created_at TEXT);")
        conn.execute("INSERT INTO _tomate_meta (created_at) VALUES (datetime('now'));")
        conn.commit()
        conn.close()

        # Fix permissions
        subprocess.run(["chown", "www-data:www-data", full_path], timeout=3)
        return {"success": True, "filepath": full_path, "filename": clean_name, "message": "Banco SQLite criado com sucesso!"}
    except Exception as e:
        return {"success": False, "message": f"Erro ao criar banco SQLite: {str(e)}"}

def execute_sqlite_query(db_path: str, query: str, limit: int = 50) -> Dict[str, Any]:
    """
    Runs a SQL statement on a local SQLite file.
    """
    if not os.path.exists(db_path):
        return {"success": False, "message": "Arquivo de banco de dados não encontrado."}

    query = query.strip()
    if not query:
        return {"success": False, "message": "Instrução SQL vazia."}

    start_time = time.time()
    try:
        conn = sqlite3.connect(db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(query)

        is_select = query.strip().upper().startswith("SELECT") or query.strip().upper().startswith("PRAGMA")
        if is_select:
            rows_data = cursor.fetchmany(limit)
            columns = [col[0] for col in cursor.description] if cursor.description else []
            rows = [dict(r) for r in rows_data]
            duration_ms = int((time.time() - start_time) * 1000)
            conn.close()
            return {
                "success": True,
                "is_select": True,
                "columns": columns,
                "rows": rows,
                "row_count": len(rows),
                "duration_ms": duration_ms,
                "message": f"Consulta executada com sucesso ({len(rows)} linhas)."
            }
        else:
            conn.commit()
            affected = cursor.rowcount
            duration_ms = int((time.time() - start_time) * 1000)
            conn.close()
            return {
                "success": True,
                "is_select": False,
                "affected_rows": affected,
                "duration_ms": duration_ms,
                "message": f"Comando executado com sucesso! ({affected} linhas afetadas)."
            }
    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        return {
            "success": False,
            "message": f"Erro SQL: {str(e)}",
            "duration_ms": duration_ms
        }

# ==============================================================================
# MariaDB Ultra-Leve (Tuned for TV Box 1GB RAM)
# ==============================================================================

def is_mariadb_installed() -> bool:
    return shutil.which("mariadb") is not None or shutil.which("mysql") is not None

def is_mariadb_active() -> bool:
    if not is_mariadb_installed():
        return False
    try:
        res = subprocess.run(["systemctl", "is-active", "mariadb"], stdout=subprocess.PIPE, text=True, timeout=2)
        return res.stdout.strip() == "active"
    except Exception:
        return False

def list_mariadb_databases() -> List[Dict[str, Any]]:
    """
    Lists customer/user databases in MariaDB.
    """
    if not is_mariadb_active():
        return []

    system_dbs = {"information_schema", "performance_schema", "mysql", "sys"}
    results = []

    try:
        cmd = "mysql -N -e 'SHOW DATABASES;'"
        proc = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, text=True, timeout=5)
        for line in proc.stdout.splitlines():
            db_name = line.strip()
            if db_name and db_name not in system_dbs:
                # Query size in MB
                size_cmd = f"mysql -N -e \"SELECT ROUND(SUM(data_length + index_length) / 1024 / 1024, 2) FROM information_schema.TABLES WHERE table_schema = '{db_name}';\""
                size_proc = subprocess.run(size_cmd, shell=True, stdout=subprocess.PIPE, text=True, timeout=5)
                size_mb = size_proc.stdout.strip() or "0.00"
                if size_mb == "NULL":
                    size_mb = "0.00"
                results.append({
                    "name": db_name,
                    "size_mb": size_mb
                })
    except Exception as e:
        print("Error listing mariadb databases:", e)

    return results

def create_mariadb_database(db_name: str, username: str = None, password: str = None) -> Dict[str, Any]:
    """
    Creates a database and optionally a user with privileges.
    """
    if not is_mariadb_active():
        return {"success": False, "message": "MariaDB não está em execução."}

    # Sanitize db_name and username (alphanumeric and underscore only)
    db_name = "".join(c for c in db_name if c.isalnum() or c == "_")
    if not db_name:
        return {"success": False, "message": "Nome de banco de dados inválido."}

    try:
        sql = f"CREATE DATABASE IF NOT EXISTS `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
        if username and password:
            username = "".join(c for c in username if c.isalnum() or c == "_")
            sql += f" CREATE USER IF NOT EXISTS '{username}'@'localhost' IDENTIFIED BY '{password}';"
            sql += f" GRANT ALL PRIVILEGES ON `{db_name}`.* TO '{username}'@'localhost';"
            sql += " FLUSH PRIVILEGES;"

        cmd = f"mysql -e \"{sql}\""
        proc = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
        if proc.returncode == 0:
            return {
                "success": True,
                "db_name": db_name,
                "username": username or "root",
                "message": f"Banco de dados '{db_name}' criado com sucesso!"
            }
        else:
            return {"success": False, "message": f"Erro do MariaDB: {proc.stderr}"}
    except Exception as e:
        return {"success": False, "message": str(e)}

def delete_mariadb_database(db_name: str) -> Dict[str, Any]:
    """
    Drops a database safely.
    """
    if not is_mariadb_active():
        return {"success": False, "message": "MariaDB não está em execução."}

    db_name = "".join(c for c in db_name if c.isalnum() or c == "_")
    system_dbs = {"information_schema", "performance_schema", "mysql", "sys"}
    if db_name in system_dbs:
        return {"success": False, "message": "Não é permitido excluir bancos de dados do sistema."}

    try:
        cmd = f"mysql -e 'DROP DATABASE IF EXISTS `{db_name}`;'"
        proc = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
        if proc.returncode == 0:
            return {"success": True, "message": f"Banco '{db_name}' removido com sucesso."}
        else:
            return {"success": False, "message": proc.stderr}
    except Exception as e:
        return {"success": False, "message": str(e)}

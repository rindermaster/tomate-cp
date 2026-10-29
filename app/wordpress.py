import os
import shutil
import tarfile
import urllib.request
import subprocess
import secrets
from typing import Dict, Any

WP_TARBALL_URL = "https://pt.wordpress.org/latest-pt_BR.tar.gz"
WP_CACHE_PATH = "/tmp/wordpress-latest-pt_BR.tar.gz"

def is_php_installed() -> bool:
    return shutil.which("php") is not None

def download_wordpress_tarball() -> str:
    """
    Downloads or uses cached WordPress tarball.
    """
    if os.path.exists(WP_CACHE_PATH) and os.path.getsize(WP_CACHE_PATH) > 10 * 1024 * 1024:
        return WP_CACHE_PATH

    print("Downloading WordPress pt_BR...")
    urllib.request.urlretrieve(WP_TARBALL_URL, WP_CACHE_PATH)
    return WP_CACHE_PATH

def generate_wp_config(db_name: str, db_user: str, db_pass: str, db_host: str = "localhost") -> str:
    """
    Generates a production-ready wp-config.php with random salts and low-memory tuning.
    """
    def rand_salt():
        return secrets.token_urlsafe(48)

    config_template = f"""<?php
/**
 * Configuração automática gerada pelo TomateCP
 */

define( 'DB_NAME', '{db_name}' );
define( 'DB_USER', '{db_user}' );
define( 'DB_PASSWORD', '{db_pass}' );
define( 'DB_HOST', '{db_host}' );
define( 'DB_CHARSET', 'utf8mb4' );
define( 'DB_COLLATE', '' );

// Chaves de segurança e autenticação (Salts)
define( 'AUTH_KEY',         '{rand_salt()}' );
define( 'SECURE_AUTH_KEY',  '{rand_salt()}' );
define( 'LOGGED_IN_KEY',    '{rand_salt()}' );
define( 'NONCE_KEY',        '{rand_salt()}' );
define( 'AUTH_SALT',        '{rand_salt()}' );
define( 'SECURE_AUTH_SALT', '{rand_salt()}' );
define( 'LOGGED_IN_SALT',   '{rand_salt()}' );
define( 'NONCE_SALT',       '{rand_salt()}' );

// Prefixo das tabelas
$table_prefix = 'wp_';

// Otimizações de memória para TV Box / Dispositivos Leves
define( 'WP_MEMORY_LIMIT', '128M' );
define( 'WP_MAX_MEMORY_LIMIT', '256M' );
define( 'WP_POST_REVISIONS', 5 );
define( 'AUTOSAVE_INTERVAL', 160 );
define( 'EMPTY_TRASH_DAYS', 7 );
define( 'DISABLE_WP_CRON', false );

define( 'WP_DEBUG', false );

if ( ! defined( 'ABSPATH' ) ) {{
	define( 'ABSPATH', __DIR__ . '/' );
}}

require_once ABSPATH . 'wp-settings.php';
"""
    return config_template

def install_wordpress(domain: str, db_name: str, db_user: str, db_pass: str, site_path: str) -> Dict[str, Any]:
    """
    Installs WordPress Lite into site_path with configured wp-config.php.
    """
    os.makedirs(site_path, exist_ok=True)

    try:
        tar_path = download_wordpress_tarball()

        # Extract to temporary dir
        extract_tmp = f"/tmp/wp-extract-{secrets.token_hex(4)}"
        os.makedirs(extract_tmp, exist_ok=True)

        with tarfile.open(tar_path, "r:gz") as tar:
            tar.extractall(path=extract_tmp)

        extracted_wp = os.path.join(extract_tmp, "wordpress")
        if not os.path.exists(extracted_wp):
            return {"success": False, "message": "Falha ao descompactar pacote do WordPress."}

        # Copy WordPress files into site_path
        for item in os.listdir(extracted_wp):
            src = os.path.join(extracted_wp, item)
            dst = os.path.join(site_path, item)
            if os.path.isdir(src):
                if os.path.exists(dst):
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)

        # Cleanup extract tmp
        shutil.rmtree(extract_tmp, ignore_errors=True)

        # Write wp-config.php
        wp_config_content = generate_wp_config(db_name, db_user, db_pass)
        with open(os.path.join(site_path, "wp-config.php"), "w", encoding="utf-8") as f:
            f.write(wp_config_content)

        # Fix permissions
        subprocess.run(["chown", "-R", "www-data:www-data", site_path], timeout=10)
        subprocess.run(["find", site_path, "-type", "d", "-exec", "chmod", "755", "{}", "+"], timeout=10)
        subprocess.run(["find", site_path, "-type", "f", "-exec", "chmod", "644", "{}", "+"], timeout=10)

        return {
            "success": True,
            "domain": domain,
            "message": f"WordPress instalado com sucesso em {domain}! Banco: {db_name}"
        }
    except Exception as e:
        return {"success": False, "message": f"Erro na instalação do WordPress: {str(e)}"}

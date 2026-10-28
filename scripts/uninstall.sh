#!/usr/bin/env bash
# ==============================================================================
# 🍅 TomateCP Uninstaller
# ==============================================================================

set -e

if [ "$(id -u)" -ne 0 ]; then
    echo "[ERRO] Este script precisa ser executado como root."
    exit 1
fi

echo "Parando e desabilitando o serviço tomate-cp..."
systemctl stop tomate-cp.service 2>/dev/null || true
systemctl disable tomate-cp.service 2>/dev/null || true

if [ -f /etc/systemd/system/tomate-cp.service ]; then
    rm /etc/systemd/system/tomate-cp.service
    systemctl daemon-reload
fi

read -p "Deseja remover também a pasta /opt/tomate-cp? (s/N): " confirm
if [[ "$confirm" =~ ^[sS]$ ]]; then
    rm -rf /opt/tomate-cp
    echo "Pasta /opt/tomate-cp removida."
fi

echo "TomateCP desinstalado com sucesso."

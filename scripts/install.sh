#!/usr/bin/env bash
# ==============================================================================
# 🍅 TomateCP Universal Installer
# Compatible with Debian 11/12, Armbian, Ubuntu 20.04/22.04/24.04
# Supports ARMv7 (32-bit), ARM64 (64-bit), and x86_64
# ==============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${RED}"
echo "  _____                      _        _____ _____  "
echo " |_   _|                    | |      / ____|  __ \ "
echo "   | | ___  _ __ ___   __ _| |_ ___| |    | |__) |"
echo "   | |/ _ \| '_ \` _ \ / _\` | __/ _ \ |    |  ___/ "
echo "   | | (_) | | | | | | (_| | ||  __/ |____| |     "
echo "   |_|\___/|_| |_| |_|\__,_|\__\___|\_____|_|     "
echo -e "${NC}"
echo -e "${CYAN}>>> Instalador Automático do TomateCP (Ultra-Lightweight Web Panel)${NC}"
echo "------------------------------------------------------------------"

# 1. Check Root
if [ "$(id -u)" -ne 0 ]; then
    echo -e "${RED}[ERRO] Este instalador precisa ser executado como root (sudo).${NC}"
    exit 1
fi

ARCH=$(uname -m)
echo -e "${GREEN}[+] Arquitetura detectada:${NC} ${ARCH}"

# 2. Install System Dependencies
echo -e "${GREEN}[+] Atualizando repositórios e instalando dependências do sistema...${NC}"
apt-get update -y
apt-get install -y nginx python3 python3-pip python3-venv curl unzip ufw

# 3. Setup Installation Directory
INSTALL_DIR="/opt/tomate-cp"
echo -e "${GREEN}[+] Configurando pasta de instalação em ${INSTALL_DIR}...${NC}"

# If script is run inside the repo, copy files from current dir
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ -f "${SCRIPT_DIR}/app/main.py" ]; then
    mkdir -p "${INSTALL_DIR}"
    cp -r "${SCRIPT_DIR}/app" "${INSTALL_DIR}/"
    cp -r "${SCRIPT_DIR}/scripts" "${INSTALL_DIR}/"
    cp "${SCRIPT_DIR}/requirements.txt" "${INSTALL_DIR}/"
    cp "${SCRIPT_DIR}/config.example.json" "${INSTALL_DIR}/"
    if [ -d "${SCRIPT_DIR}/design-system" ]; then
        cp -r "${SCRIPT_DIR}/design-system" "${INSTALL_DIR}/"
    fi
else
    # Clone from GitHub
    echo -e "${GREEN}[+] Clonando repositório oficial do GitHub...${NC}"
    rm -rf "${INSTALL_DIR}"
    git clone https://github.com/roberto-oliveira/tomate-cp.git "${INSTALL_DIR}"
fi

# 4. Setup Python Virtual Environment
echo -e "${GREEN}[+] Criando ambiente virtual Python isolado...${NC}"
python3 -m venv "${INSTALL_DIR}/venv"
"${INSTALL_DIR}/venv/bin/pip" install --upgrade pip
"${INSTALL_DIR}/venv/bin/pip" install -r "${INSTALL_DIR}/requirements.txt"

# 5. Initialize Config
if [ ! -f "${INSTALL_DIR}/config/config.json" ]; then
    mkdir -p "${INSTALL_DIR}/config"
    cp "${INSTALL_DIR}/config.example.json" "${INSTALL_DIR}/config/config.json"
fi

# Ensure web directories exist
mkdir -p /var/www
chown -R www-data:www-data /var/www 2>/dev/null || true

# 6. Install Systemd Service
echo -e "${GREEN}[+] Configurando serviço do sistema (systemd)...${NC}"
cp "${INSTALL_DIR}/scripts/tomate-cp.service" /etc/systemd/system/tomate-cp.service
systemctl daemon-reload
systemctl enable tomate-cp.service
systemctl restart tomate-cp.service

# 7. Configure Firewall
if command -v ufw >/dev/null 2>&1; then
    ufw allow 80/tcp >/dev/null 2>&1 || true
    ufw allow 8888/tcp >/dev/null 2>&1 || true
fi

# 8. Get LAN IP
LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
if [ -z "$LOCAL_IP" ]; then
    LOCAL_IP="127.0.0.1"
fi

echo ""
echo "=================================================================="
echo -e "${GREEN}🎉 TomateCP instalado e rodando com sucesso!${NC}"
echo "=================================================================="
echo -e "Acesse no navegador: ${CYAN}http://${LOCAL_IP}:8888${NC}"
echo -e "Usuário padrão:       ${YELLOW}admin${NC}"
echo -e "Senha padrão:         ${YELLOW}admin${NC} (Altere em Configurações)"
echo ""
echo -e "Para gerenciar o serviço:"
echo "  systemctl status tomate-cp"
echo "  systemctl restart tomate-cp"
echo "=================================================================="

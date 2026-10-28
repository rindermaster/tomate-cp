# 🍅 TomateCP (Tomate Control Panel)

> **O painel de hospedagem web ultra-leve para TV Boxes, SBCs e dispositivos de baixo consumo.**  
> Projetado para velocidade máxima, consumo mínimo de memória (< 30MB RAM) e compatibilidade total (ARMv7, ARM64, x86_64).

---

## 🎯 Visão do Projeto

O **TomateCP** nasceu para transformar hardware antigo ou subutilizado (como TV Boxes Rockchip/Allwinner/Amlogic, celulares Android antigos com Linux e Raspberry Pis) em **servidores web profissionais de alta performance**.

Diferente de painéis tradicionais (cPanel, aaPanel, CyberPanel) que consomem de 1GB a 4GB de RAM e exigem processadores 64-bit caros, o TomateCP foi arquitetado do zero para ser:
1. **Ultra Leve:** Roda diretamente sobre o Nginx e Python 3 nativo, gastando menos de 30MB de memória RAM.
2. **Zero Bloat:** Sem Docker pesado, sem serviços de e-mail desnecessários (Postfix/Dovecot), sem bancos de dados gigantes em background.
3. **100% White-Label:** Código limpo e modular para você alterar logo, cores, títulos e menus em segundos.
4. **Instalação em 1 Comando:** Transforma qualquer Debian, Armbian ou Ubuntu recém-instalado em um servidor web pronto com `curl -sSL ... | bash`.

---

## 🚀 Arquitetura & Stack Técnica

* **Backend:** Python 3 (FastAPI / Uvicorn assíncrono) — execução nativa, consumo mínimo de CPU.
* **Web Server:** Nginx (Proxy reverso, compressão Gzip/Brotli, cache de arquivos estáticos).
* **Frontend:** Interface moderna construída com o design system do **`ui-ux-pro-max`**:
  * Dark Mode de alta performance com toques de glassmorphism sutis.
  * Tipografia: *Plus Jakarta Sans*.
  * Cores Semânticas: Fundo Slate escuro (`#0F172A`), Cards (`#1E293B`), Acento Tomate (`#EF4444`) e Status Verde Esmeralda (`#22C55E`).
  * Ícones: SVG vetoriais embutidos (Lucide / Phosphor), sem dependência de fontes externas pesadas.
* **Telemetria de Hardware:** Leitura direta de `/sys/class/thermal/` (temperatura de TV Box sem ventoinha!), `/proc/meminfo`, `/proc/loadavg` e `df`.

---

## 📦 Estrutura de Diretórios Planejada

```text
tomate-cp/
├── app/
│   ├── main.py              # Servidor API FastAPI & Rotas
│   ├── system.py            # Módulo de telemetria (CPU, RAM, Temp, Disco)
│   ├── sites.py             # Gerenciador de vhosts Nginx (/etc/nginx/)
│   ├── templates/           # HTML moderno (Dashboard, Sites, Deploy, Config)
│   │   ├── base.html
│   │   ├── dashboard.html
│   │   ├── sites.html
│   │   └── settings.html
│   └── static/              # CSS com variáveis de design system, SVGs e JS
│       ├── css/style.css
│       ├── js/app.js
│       └── img/logo.svg
├── scripts/
│   ├── install.sh           # Instalador automático para Debian/Armbian/Ubuntu
│   ├── uninstall.sh         # Desinstalador limpo
│   └── tomate-cp.service    # Definição de serviço systemd
├── design-system/
│   └── tomatecp/
│       └── MASTER.md        # Especificações completas de UI/UX
├── config.example.json      # Configuração customizável de branding e portas
└── README.md
```

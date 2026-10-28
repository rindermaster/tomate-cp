# 🍅 TomateCP — Plano de Implementação & Arquitetura

> **O painel de hospedagem web ultra-leve para TV Boxes, SBCs e dispositivos de baixo consumo.**  
> Projetado para velocidade máxima, consumo mínimo de memória (< 30MB RAM) e compatibilidade universal (ARMv7 32-bit, ARM64, x86_64).

---

## 1. Visão Geral & Filosofia

O **TomateCP** é um painel de controle e gerenciador de hospedagem criado para transformar dispositivos de baixo custo e baixo consumo de energia (como TV Boxes Rockchip RK3228A/RK3229, Allwinner H3/H616, Amlogic S905, celulares Android antigos e Raspberry Pis) em **servidores web de alta performance**.

### Princípios Fundamentais:
1. **Zero Bloatware:** Sem Docker obrigatório (que consome mais de 150MB de RAM sozinho), sem serviços de e-mail pesados (Postfix/Dovecot), sem bancos de dados gigantes em background.
2. **Consumo de Memória < 30MB:** Roda nativamente sobre Python 3 e Nginx, consumindo uma fração minúscula do 1GB de RAM da TV Box.
3. **100% White-Label & Customizável:** Desenvolvido em arquivos limpos e legíveis para que qualquer desenvolvedor possa alterar logo, cores, remover menus ou reescrever funções sem necessidade de ferramentas de compilação complexas.
4. **Instalação em 1 Comando:** Pronto para qualquer distribuição baseada em Debian/Ubuntu/Armbian via `curl -fsSL ... | bash`.

---

## 2. Especificação de UI/UX (Baseado no `ui-ux-pro-max`)

O visual e a experiência do usuário seguem as diretrizes geradas pelo skill **`ui-ux-pro-max`** (persistidas no repositório em `design-system/tomatecp/MASTER.md`):

* **Estilo Visual:** Deep Tech Dark Mode com toques sutis de Glassmorphism (efeito vidro fosco translúcido).
* **Tipografia:** *Plus Jakarta Sans* (moderna, geométrica e com excelente legibilidade para dados técnicos).
* **Paleta de Cores Semântica:**
  * **Fundo (Background):** `#0F172A` (Slate 900)
  * **Superfícies / Cards:** `#1E293B` (Slate 800) com borda suave `1px solid rgba(255, 255, 255, 0.08)`
  * **Destaque da Marca (Tomato Accent):** `#EF4444` (Vermelho Tomate vibrante)
  * **Status Online / Saudável:** `#22C55E` (Verde Esmeralda)
  * **Status Alerta / Atenção:** `#F59E0B` (Âmbar / Amarelo)
  * **Status Crítico / Erro:** `#DC2626` (Vermelho Escuro)
  * **Texto Principal:** `#F8FAFC` (Slate 50)
  * **Texto Secundário / Muted:** `#94A3B8` (Slate 400)
* **Ícones:** SVG vetoriais embutidos (família Lucide / Phosphor Icons), sem carregar emojis ou bibliotecas pesadas de fontes externas.
* **Layout:** Bento Grid responsivo (adaptável para telas de 375px até desktops 4K).

---

## 3. Módulos do Sistema

### 📊 Módulo 1: Telemetria & Monitoramento em Tempo Real
Essencial para dispositivos passivos (sem ventilador como a TV Box Tomate):
* **Temperatura do Processador:** Leitura direta de `/sys/class/thermal/thermal_zone*/temp`.
  * `< 60°C`: Badge Verde (Normal)
  * `60°C - 75°C`: Badge Amarelo (Aqueceu)
  * `> 75°C`: Badge Vermelho piscante (Crítico / Throttling)
* **Uso de CPU:** Cálculo instantâneo da carga e Load Average (1m, 5m, 15m).
* **Memória RAM & zRAM/Swap:**
  * Divisão visual: RAM em Uso, Cache de Disco e RAM Livre.
  * Monitor do zRAM comprimido ativo (512MB na nossa TV Box).
* **Armazenamento eMMC / MicroSD:**
  * Barra de ocupação de disco da partição raiz `/` e espaço em gigabytes.
* **Informações do Dispositivo:** Modelo do SoC, Versão do Kernel, Uptime (tempo ligado sem reiniciar) e IP de rede local.

### 🌐 Módulo 2: Gerenciador de Sites & VHosts Nginx
* **Adicionar Novo Site (Wizard em 2 Passos):**
  1. *Nome do Domínio:* Ex: `meusite.com.br`, `cliente.zipdigital.site`, `loja.local`.
  2. *Tipo de Site:*
     * **Site Estático (HTML/CSS/JS):** Cria `/var/www/<dominio>/` com uma página inicial padrão e configura cache de assets estáticos no Nginx.
     * **Proxy Reverso (Node.js/Python/Go/Docker/Porta):** Redireciona o tráfego daquele domínio para uma porta local interna (ex: `http://127.0.0.1:3000`).
     * **PHP-FPM:** Configura socket FastCGI caso o PHP esteja habilitado.
* **Controle de Estado do Site:**
  * Botão Ligar/Desligar (ativa ou desativa o symlink em `/etc/nginx/sites-enabled/` sem apagar arquivos).
* **Validador de Sintaxe Nginx (`nginx -t`):**
  * Nenhuma configuração é recarregada se houver erro de sintaxe, impedindo que o servidor web caia.
* **Exclusão Segura:**
  * Opção de excluir apenas o vhost do Nginx ou também remover os arquivos da pasta `/var/www/<dominio>`.

### 📁 Módulo 3: Deploy Fácil & Upload de Arquivos
* **Upload de ZIP via Navegador:**
  * O usuário arrasta o arquivo `.zip` do site para a área de deploy.
  * O painel extrai os arquivos diretamente dentro de `/var/www/<dominio>/` e aplica as permissões corretas (`www-data:www-data`).
* **Upload Individual:** Envio de arquivos individuais (HTML, CSS, imagens).
* **Mini Editor de Código:** Editor simples integrado para pequenas correções no `index.html` ou arquivos de texto sem precisar de SSH.

### 🔒 Módulo 4: SSL & Túneis
* **Integração com Cloudflare Tunnel:**
  * Instruções e assistente para adicionar o novo domínio nas regras de Ingress do túnel sem precisar abrir portas 80/443 no roteador.
* **SSL Let's Encrypt / Certbot:**
  * Botão de 1 clique para emissão de certificado HTTPS para quem possui IP público direto.

### ⚙️ Módulo 5: Controle de Serviços do Sistema
* **Ações Rápidas de Manutenção:**
  * *Recarregar Nginx* (`systemctl reload nginx`)
  * *Reiniciar Nginx* (`systemctl restart nginx`)
  * *Reiniciar Painel TomateCP*
  * *Reiniciar TV Box* (`reboot`)
* **Visualizador de Logs:**
  * Últimas 50 linhas do `access.log` e `error.log` do Nginx com pesquisa e filtro.

### 🏷️ Módulo 6: White-Label & Customização Rápida
* Arquivo `config.json` centralizado:
  ```json
  {
    "panel_name": "TomateCP",
    "company_name": "ZipDigital",
    "accent_color": "#EF4444",
    "port": 8888,
    "logo_path": "/static/img/logo.svg",
    "footer_text": "Powered by Tomate Mini Server"
  }
  ```
* Edição simples de templates HTML (Jinja2) e CSS sem compilação.

---

## 4. Estrutura do Código no Repositório

```text
tomate-cp/
├── app/
│   ├── __init__.py
│   ├── main.py              # Ponto de entrada FastAPI & Rotas HTTP
│   ├── system.py            # Coleta de telemetria (CPU, Temp, RAM, Disco)
│   ├── sites.py             # Manipulação de Vhosts Nginx & Diretórios
│   ├── auth.py              # Autenticação e sessão simples
│   ├── templates/           # Templates HTML com Jinja2
│   │   ├── base.html        # Layout mestre com sidebar e navegação
│   │   ├── dashboard.html   # Bento Grid de telemetria e atalhos
│   │   ├── sites.html       # Tabela de sites, modais de criação e status
│   │   ├── deploy.html      # Área de upload de ZIP e gerenciamento de arquivos
│   │   ├── logs.html        # Leitor de logs do Nginx
│   │   └── settings.html    # Configurações do painel e personalização
│   └── static/
│       ├── css/
│       │   └── style.css    # Design System ui-ux-pro-max puro (sem dependências externas)
│       ├── js/
│       │   └── app.js       # Polling de telemetria assíncrono e interatividade dos modais
│       └── img/
│           └── logo.svg     # Logo Tomate personalizável
├── scripts/
│   ├── install.sh           # Instalador automático para Debian/Ubuntu/Armbian
│   ├── uninstall.sh         # Desinstalador
│   └── tomate-cp.service    # Arquivo de serviço systemd
├── design-system/
│   └── tomatecp/
│       └── MASTER.md        # Tokens de design e guia visual do ui-ux-pro-max
├── config.example.json      # Modelo de configuração
├── requirements.txt         # fastapi, uvicorn, jinja2, python-multipart
├── LICENSE                  # Licença MIT Open Source
└── README.md                # Documentação completa para o GitHub
```

---

## 5. Fases de Execução do Roadmap

| Fase | Etapa | Descrição |
|:---:|:---|:---|
| **1** | **Scaffolding & Core Backend** | Criar a estrutura de pastas em `tomate-cp/`, configurar o `requirements.txt` e desenvolver o módulo de telemetria `system.py` que lê `/sys/class/thermal/`, `/proc/meminfo` e `/proc/loadavg`. |
| **2** | **Nginx Engine (`sites.py`)** | Desenvolver os geradores de configuração Nginx para sites estáticos e proxy reverso, com teste de sintaxe (`nginx -t`) e recarregamento seguro. |
| **3** | **Interface Visual (`ui-ux-pro-max`)** | Criar os templates HTML e CSS com o design system Dark Mode Glassmorphism, cards de métricas em tempo real e modais de criação de sites. |
| **4** | **Deploy & Upload de ZIP** | Implementar a rota de upload e descompactação automática de arquivos `.zip` para publicação instantânea de sites. |
| **5** | **Deploy na TV Box Tomate** | Enviar e instalar o TomateCP na TV Box via SSH, configurar o serviço `tomate-cp.service` e apontar o subdomínio no Cloudflare Tunnel (ex: `painel.zipdigital.site`). |
| **6** | **Instalador Universal & GitHub** | Criar o `install.sh` de 1 linha e preparar o repositório Git com commits limpos para publicação aberta. |

#!/bin/bash
# =============================================================================
# BTExtract — Setup automatizado para Oracle Cloud ARM A1 (Ubuntu 22.04)
# =============================================================================
# Execute na VM Oracle Cloud como usuário 'ubuntu':
#   chmod +x setup_oracle.sh && ./setup_oracle.sh
# =============================================================================

set -euo pipefail

REPO_URL="https://github.com/MatGarciaBertoi/BTExtract.git"
APP_DIR="/opt/btextract"
SERVICE_NAME="btextract"
VENV_DIR="$APP_DIR/venv"
DATA_DIR="/opt/btextract_data"

# ── Cores para output ──────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()    { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
ask()     { echo -e "${YELLOW}[?]${NC} $1"; }

# ── 1. Atualizar sistema ───────────────────────────────────────────────────
info "Atualizando sistema..."
sudo apt-get update -qq
sudo apt-get upgrade -y -qq
sudo apt-get install -y -qq \
    python3.12 python3.12-venv python3.12-dev \
    python3-pip git nginx certbot python3-certbot-nginx \
    curl ufw build-essential libffi-dev libssl-dev

info "Sistema atualizado ✓"

# ── 2. Configurar firewall ─────────────────────────────────────────────────
info "Configurando firewall (ufw)..."
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw --force enable
info "Firewall configurado ✓"

# ── 3. Liberar portas no iptables (necessário na Oracle Cloud) ────────────
info "Liberando portas no iptables do Oracle..."
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save 2>/dev/null || sudo apt-get install -y -qq iptables-persistent && sudo netfilter-persistent save
info "Portas 80 e 443 liberadas ✓"

# ── 4. Criar diretórios ────────────────────────────────────────────────────
info "Criando diretórios..."
sudo mkdir -p "$APP_DIR" "$DATA_DIR"
sudo chown ubuntu:ubuntu "$APP_DIR" "$DATA_DIR"

# ── 5. Clonar repositório ──────────────────────────────────────────────────
info "Clonando repositório..."
if [ -d "$APP_DIR/.git" ]; then
    warn "Repositório já existe. Atualizando..."
    cd "$APP_DIR" && git pull
else
    git clone "$REPO_URL" "$APP_DIR"
fi
info "Repositório clonado ✓"

# ── 6. Criar ambiente virtual e instalar dependências ─────────────────────
info "Criando ambiente virtual Python 3.12..."
python3.12 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --upgrade pip -q
"$VENV_DIR/bin/pip" install -r "$APP_DIR/requirements.txt" -q
info "Dependências instaladas ✓"

# ── 7. Coletar variáveis de ambiente ──────────────────────────────────────
echo ""
echo "============================================================"
echo "  Configure as variáveis de ambiente do BTExtract"
echo "============================================================"
echo ""

ask "SECRET_KEY (deixe em branco para gerar automaticamente):"
read -r SECRET_KEY_INPUT
if [ -z "$SECRET_KEY_INPUT" ]; then
    SECRET_KEY=$("$VENV_DIR/bin/python" -c "import secrets; print(secrets.token_hex(32))")
    info "SECRET_KEY gerado automaticamente"
else
    SECRET_KEY="$SECRET_KEY_INPUT"
fi

ask "SUPERADMIN_EMAIL (seu e-mail):"
read -r SUPERADMIN_EMAIL

ask "SUPERADMIN_PASSWORD (senha forte):"
read -rs SUPERADMIN_PASSWORD
echo ""

ask "GEMINI_API_KEY (chave do Google AI Studio):"
read -r GEMINI_API_KEY

ask "Configurar e-mail SMTP? (s/n):"
read -r SMTP_RESP
SMTP_HOST=""
SMTP_PORT=""
SMTP_USER=""
SMTP_PASSWORD=""
SMTP_FROM=""
if [[ "$SMTP_RESP" =~ ^[Ss]$ ]]; then
    ask "SMTP_HOST (ex: smtp.gmail.com):"
    read -r SMTP_HOST
    SMTP_PORT="587"
    ask "SMTP_USER (seu e-mail Gmail):"
    read -r SMTP_USER
    ask "SMTP_PASSWORD (senha de app do Gmail):"
    read -rs SMTP_PASSWORD
    echo ""
    SMTP_FROM="BTExtract <$SMTP_USER>"
fi

# ── 8. Criar arquivo .env ──────────────────────────────────────────────────
info "Criando arquivo .env..."
cat > "$APP_DIR/.env" << EOF
# BTExtract — Variáveis de ambiente
SECRET_KEY=$SECRET_KEY
SUPERADMIN_EMAIL=$SUPERADMIN_EMAIL
SUPERADMIN_PASSWORD=$SUPERADMIN_PASSWORD
GEMINI_API_KEY=$GEMINI_API_KEY
BT_DB_PATH=$DATA_DIR/btextract.db

# SMTP (deixe vazio se não usar e-mail)
SMTP_HOST=$SMTP_HOST
SMTP_PORT=$SMTP_PORT
SMTP_USER=$SMTP_USER
SMTP_PASSWORD=$SMTP_PASSWORD
SMTP_FROM=$SMTP_FROM
EOF
chmod 600 "$APP_DIR/.env"
info "Arquivo .env criado ✓"

# ── 9. Criar serviço systemd ───────────────────────────────────────────────
info "Criando serviço systemd..."
sudo bash -c "cat > /etc/systemd/system/${SERVICE_NAME}.service" << EOF
[Unit]
Description=BTExtract FastAPI
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$VENV_DIR/bin/uvicorn main:app --host 127.0.0.1 --port 8080 --workers 2 --log-level warning
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl start "$SERVICE_NAME"
info "Serviço systemd criado e iniciado ✓"

# ── 10. Configurar nginx (HTTP primeiro, SSL depois com certbot) ───────────
ask "Qual é o seu domínio/subdomínio? (ex: btextract.duckdns.org):"
read -r DOMAIN

info "Configurando nginx para $DOMAIN..."
sudo bash -c "cat > /etc/nginx/sites-available/btextract" << EOF
server {
    listen 80;
    server_name $DOMAIN;

    # Upload de arquivos grandes (PDF, DOCX)
    client_max_body_size 50m;

    # Timeout longo para chamadas ao Gemini AI
    proxy_read_timeout    180s;
    proxy_connect_timeout  60s;
    proxy_send_timeout    180s;

    location / {
        proxy_pass         http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header   Host              \$host;
        proxy_set_header   X-Real-IP         \$remote_addr;
        proxy_set_header   X-Forwarded-For   \$proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto \$scheme;
    }
}
EOF

sudo ln -sf /etc/nginx/sites-available/btextract /etc/nginx/sites-enabled/btextract
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
info "nginx configurado ✓"

# ── 11. Configurar SSL com certbot ─────────────────────────────────────────
ask "Configurar HTTPS com certbot agora? (s/n) — precisa que o domínio já aponte para este IP:"
read -r CERTBOT_RESP
if [[ "$CERTBOT_RESP" =~ ^[Ss]$ ]]; then
    ask "Seu e-mail para o certbot:"
    read -r CERTBOT_EMAIL
    sudo certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "$CERTBOT_EMAIL"
    info "SSL configurado ✓ — HTTPS ativo!"
else
    warn "SSL não configurado. Execute depois: sudo certbot --nginx -d $DOMAIN"
fi

# ── 12. Status final ────────────────────────────────────────────────────────
echo ""
echo "============================================================"
echo -e "${GREEN}  ✓ BTExtract instalado com sucesso!${NC}"
echo "============================================================"
echo ""
info "Status do serviço:"
sudo systemctl status "$SERVICE_NAME" --no-pager -l | head -20
echo ""
IP=$(curl -s ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')
echo -e "  ${GREEN}URL HTTP:${NC}  http://$DOMAIN"
echo -e "  ${GREEN}Health:${NC}    http://$DOMAIN/health"
echo ""
echo "Comandos úteis:"
echo "  sudo systemctl status $SERVICE_NAME   # Ver status"
echo "  sudo journalctl -u $SERVICE_NAME -f   # Ver logs em tempo real"
echo "  sudo systemctl restart $SERVICE_NAME  # Reiniciar"
echo ""
echo "Para atualizar o código:"
echo "  cd $APP_DIR && git pull && sudo systemctl restart $SERVICE_NAME"
echo "============================================================"

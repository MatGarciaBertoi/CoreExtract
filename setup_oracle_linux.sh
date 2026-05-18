#!/bin/bash
# =============================================================================
# BTExtract — Setup para Oracle Cloud (Oracle Linux 9)
# Execute como usuário 'opc':
#   curl -O https://raw.githubusercontent.com/MatGarciaBertoi/BTExtract/master/setup_oracle_linux.sh
#   chmod +x setup_oracle_linux.sh && ./setup_oracle_linux.sh
# =============================================================================

set -euo pipefail

REPO_URL="https://github.com/MatGarciaBertoi/BTExtract.git"
APP_DIR="/opt/btextract"
DATA_DIR="/opt/btextract_data"
VENV_DIR="$APP_DIR/venv"
SERVICE_NAME="btextract"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info() { echo -e "${GREEN}[INFO]${NC} $1"; }
ask()  { echo -e "${YELLOW}[?]${NC} $1"; }

# ── 1. Atualizar sistema ───────────────────────────────────────────────────
info "Atualizando Oracle Linux..."
sudo dnf update -y -q
sudo dnf install -y -q git python3.11 python3.11-pip nginx certbot python3-certbot-nginx
info "Sistema atualizado ✓"

# ── 2. Firewall (firewalld + iptables Oracle Cloud) ────────────────────────
info "Configurando firewall..."
sudo systemctl enable --now firewalld
sudo firewall-cmd --add-service=http  --permanent
sudo firewall-cmd --add-service=https --permanent
sudo firewall-cmd --add-service=ssh   --permanent
sudo firewall-cmd --reload

# Oracle Cloud tem regras iptables extras — precisamos liberar as portas
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80  -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo sh -c 'iptables-save > /etc/iptables/rules.v4' 2>/dev/null || true

# SELinux: permite nginx conectar ao backend
sudo setsebool -P httpd_can_network_connect 1
info "Firewall configurado ✓"

# ── 3. Criar diretórios ────────────────────────────────────────────────────
info "Criando diretórios..."
sudo mkdir -p "$APP_DIR" "$DATA_DIR"
sudo chown opc:opc "$APP_DIR" "$DATA_DIR"

# ── 4. Clonar repositório ──────────────────────────────────────────────────
info "Clonando repositório..."
if [ -d "$APP_DIR/.git" ]; then
    cd "$APP_DIR" && git pull
else
    git clone "$REPO_URL" "$APP_DIR"
fi
info "Repositório clonado ✓"

# ── 5. Ambiente virtual Python ─────────────────────────────────────────────
info "Criando ambiente virtual..."
python3.11 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --upgrade pip -q
"$VENV_DIR/bin/pip" install -r "$APP_DIR/requirements.txt" -q
info "Dependências instaladas ✓"

# ── 6. Variáveis de ambiente ───────────────────────────────────────────────
echo ""
echo "============================================================"
echo "  Configure as variáveis de ambiente do BTExtract"
echo "============================================================"

ask "SECRET_KEY (Enter para gerar automaticamente):"
read -r SECRET_KEY_INPUT
if [ -z "$SECRET_KEY_INPUT" ]; then
    SECRET_KEY=$("$VENV_DIR/bin/python" -c "import secrets; print(secrets.token_hex(32))")
    info "SECRET_KEY gerado automaticamente"
else
    SECRET_KEY="$SECRET_KEY_INPUT"
fi

ask "SUPERADMIN_EMAIL:"
read -r SUPERADMIN_EMAIL

ask "SUPERADMIN_PASSWORD:"
read -rs SUPERADMIN_PASSWORD; echo ""

ask "GEMINI_API_KEY:"
read -r GEMINI_API_KEY

ask "Configurar SMTP Gmail? (s/n):"
read -r SMTP_RESP
SMTP_HOST=""; SMTP_PORT=""; SMTP_USER=""; SMTP_PASSWORD=""; SMTP_FROM=""
if [[ "$SMTP_RESP" =~ ^[Ss]$ ]]; then
    SMTP_HOST="smtp.gmail.com"; SMTP_PORT="587"
    ask "Gmail (SMTP_USER):"; read -r SMTP_USER
    ask "Senha de app Gmail:"; read -rs SMTP_PASSWORD; echo ""
    SMTP_FROM="BTExtract <$SMTP_USER>"
fi

# ── 7. Criar .env ──────────────────────────────────────────────────────────
cat > "$APP_DIR/.env" << EOF
SECRET_KEY=$SECRET_KEY
SUPERADMIN_EMAIL=$SUPERADMIN_EMAIL
SUPERADMIN_PASSWORD=$SUPERADMIN_PASSWORD
GEMINI_API_KEY=$GEMINI_API_KEY
BT_DB_PATH=$DATA_DIR/btextract.db
SMTP_HOST=$SMTP_HOST
SMTP_PORT=$SMTP_PORT
SMTP_USER=$SMTP_USER
SMTP_PASSWORD=$SMTP_PASSWORD
SMTP_FROM=$SMTP_FROM
EOF
chmod 600 "$APP_DIR/.env"
info ".env criado ✓"

# ── 8. Serviço systemd ─────────────────────────────────────────────────────
sudo tee /etc/systemd/system/${SERVICE_NAME}.service > /dev/null << EOF
[Unit]
Description=BTExtract FastAPI
After=network.target

[Service]
Type=simple
User=opc
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$VENV_DIR/bin/uvicorn main:app --host 127.0.0.1 --port 8080 --workers 1 --log-level warning
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now "$SERVICE_NAME"
info "Serviço systemd ✓"

# ── 9. nginx ───────────────────────────────────────────────────────────────
ask "Seu domínio DuckDNS (ex: btextract-bertoi.duckdns.org):"
read -r DOMAIN

sudo tee /etc/nginx/conf.d/btextract.conf > /dev/null << EOF
server {
    listen 80;
    server_name $DOMAIN;
    client_max_body_size 50m;
    proxy_read_timeout    180s;
    proxy_connect_timeout  60s;

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
sudo systemctl enable --now nginx
sudo nginx -t && sudo systemctl reload nginx
info "nginx configurado ✓"

# ── 10. SSL ────────────────────────────────────────────────────────────────
ask "Configurar HTTPS agora? (s/n):"
read -r CERT_RESP
if [[ "$CERT_RESP" =~ ^[Ss]$ ]]; then
    ask "Seu e-mail:"; read -r CERT_EMAIL
    sudo certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "$CERT_EMAIL"
    info "SSL ✓"
fi

# ── Status final ───────────────────────────────────────────────────────────
echo ""
echo "============================================================"
echo -e "${GREEN}  ✓ BTExtract instalado com sucesso!${NC}"
echo "============================================================"
sudo systemctl status "$SERVICE_NAME" --no-pager -l | head -15
echo ""
echo "  URL: http://$DOMAIN"
echo "  Health: http://$DOMAIN/health"
echo ""
echo "Atualizar: cd $APP_DIR && git pull && sudo systemctl restart $SERVICE_NAME"
echo "Logs:      sudo journalctl -u $SERVICE_NAME -f"
echo "============================================================"

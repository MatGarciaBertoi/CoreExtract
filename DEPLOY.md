# Deploy CoreExtract — Fly.io + Streamlit Cloud

## Visão Geral da Arquitetura

```
GitHub (repositório)
    │
    ├── Fly.io ──────────── FastAPI + SQLite (volume persistente)
    │                        https://coreextract-bertoi.fly.dev
    │
    └── Streamlit Cloud ─── Dashboard (dashboard.py)
                             https://coreextract-bertoi.streamlit.app
```

---

## PARTE 1 — Subir código para o GitHub

### 1.1 Criar repositório no GitHub

1. Acesse https://github.com/new
2. Nome sugerido: `coreextract`
3. Deixe **Privado** (seus dados de clientes ficam protegidos)
4. Clique em "Create repository"

### 1.2 Enviar o código

Abra o terminal na pasta `C:\CoreExtract` e execute:

```bash
git init
git add .
git commit -m "deploy: CoreExtract v2 — Fly.io + Streamlit Cloud"
git branch -M main
git remote add origin https://github.com/SEU_USUARIO/coreextract.git
git push -u origin main
```

---

## PARTE 2 — Deploy FastAPI no Fly.io

### 2.1 Instalar o CLI do Fly.io

```bash
# Windows (PowerShell como Administrador)
iwr https://fly.io/install.ps1 -useb | iex
```

### 2.2 Criar conta e fazer login

```bash
fly auth signup     # Cria conta (pede cartão — não cobra no free tier)
# ou
fly auth login      # Se já tiver conta
```

### 2.3 Criar o app e o volume

```bash
cd C:\CoreExtract

# Criar o app com o nome definido no fly.toml
fly launch --no-deploy --copy-config

# Criar o volume persistente para o SQLite
fly volumes create coreextract_data --region gru --size 1
```

### 2.4 Configurar as variáveis de ambiente secretas

```bash
# OBRIGATÓRIAS:
fly secrets set SECRET_KEY="cole-aqui-uma-chave-de-64-caracteres-aleatoria"
fly secrets set SUPERADMIN_EMAIL="seu@email.com"
fly secrets set SUPERADMIN_PASSWORD="sua-senha-forte"
fly secrets set GEMINI_API_KEY="sua-chave-gemini"

# SE USAR E-MAIL (SMTP Gmail):
fly secrets set SMTP_HOST="smtp.gmail.com"
fly secrets set SMTP_PORT="587"
fly secrets set SMTP_USER="seu@gmail.com"
fly secrets set SMTP_PASSWORD="senha-de-app-do-gmail"
fly secrets set SMTP_FROM="CoreExtract <seu@gmail.com>"
```

> **Como gerar o SECRET_KEY:**
> ```bash
> python -c "import secrets; print(secrets.token_hex(32))"
> ```

### 2.5 Deploy!

```bash
fly deploy
```

Aguarde o build (2–5 minutos). Ao final você verá:
```
✓ Machine started in 4s
Visit your newly deployed app at https://coreextract-bertoi.fly.dev
```

### 2.6 Verificar se está funcionando

```bash
fly status
fly logs           # Ver logs em tempo real
```

Acesse `https://coreextract-bertoi.fly.dev/health` — deve retornar `{"status":"ok"}`.

---

## PARTE 3 — Deploy Dashboard no Streamlit Cloud

### 3.1 Acessar o Streamlit Community Cloud

1. Acesse https://share.streamlit.io
2. Faça login com sua conta GitHub
3. Clique em **"New app"**

### 3.2 Configurar o app

Preencha os campos:
- **Repository:** `SEU_USUARIO/coreextract`
- **Branch:** `main`
- **Main file path:** `dashboard.py`
- **App URL:** escolha um nome (ex: `coreextract-bertoi`)

Clique em **"Advanced settings"** e em **Secrets** cole:

```toml
API_BASE_URL = "https://coreextract-bertoi.fly.dev"
```

### 3.3 Deploy!

Clique em **"Deploy!"** — o Streamlit Cloud instala as dependências de
`requirements-dashboard.txt` automaticamente.

Após 2–3 minutos, o dashboard estará em:
`https://coreextract-bertoi.streamlit.app`

---

## PARTE 4 — Atualizar o link do Dashboard no CoreExtract

Depois que o Streamlit Cloud gerar a URL definitiva, atualize o link no frontend.

Em `C:\CoreExtract\templates\frontend.html`, localize a função `_initDashboardBtn`:

```javascript
btn.href = isLocal
  ? `http://${window.location.hostname}:8081`
  : (window.location.origin + '/dashboard/');   // ← TROCAR ESTA LINHA
```

Troque por:

```javascript
btn.href = isLocal
  ? `http://${window.location.hostname}:8081`
  : 'https://coreextract-bertoi.streamlit.app';  // ← URL real do Streamlit
```

Depois faça commit e redeploy:

```bash
git add templates/frontend.html
git commit -m "fix: atualiza URL do dashboard para Streamlit Cloud"
git push
fly deploy
```

---

## Resumo de URLs após deploy

| Serviço | URL |
|---|---|
| CoreExtract (FastAPI) | https://coreextract-bertoi.fly.dev |
| Dashboard (Streamlit) | https://coreextract-bertoi.streamlit.app |
| Health check | https://coreextract-bertoi.fly.dev/health |
| Docs API | https://coreextract-bertoi.fly.dev/docs |

---

## Operações de manutenção

```bash
# Ver logs
fly logs

# Reiniciar app
fly apps restart coreextract-bertoi

# Escalar máquina (se precisar mais RAM)
fly scale memory 512

# Acessar banco via SSH
fly ssh console
sqlite3 /data/coreextract.db

# Fazer backup do banco
fly ssh sftp get /data/coreextract.db ./backup_$(date +%Y%m%d).db

# Atualizar deploy após mudanças no código
git push && fly deploy
```

---

## Fluxo de atualização contínua

```
Edita código local → git push → fly deploy   (FastAPI)
                              → Streamlit Cloud faz redeploy automático (dashboard)
```

# Deploy CoreExtract — Oracle Cloud Always Free ARM A1

## Por que Oracle Cloud?

| Recurso | Fly.io (gratuito) | Oracle Cloud (sempre gratuito) |
|---|---|---|
| RAM | 256MB | **12GB** (até 24GB) |
| CPU | 1 shared vCPU | **2 ARM OCPUs** |
| Armazenamento | 1GB volume | **200GB boot disk** |
| Custo mensal | $0 | **$0 para sempre** |

---

## PARTE 1 — Criar conta na Oracle Cloud

1. Acesse: **https://www.oracle.com/cloud/free/**
2. Clique em **"Start for free"**
3. Preencha com seus dados (pede cartão de crédito — **não cobra nada**, só valida identidade)
4. Escolha a região mais próxima: **Brazil East (São Paulo)**
5. Confirme o e-mail e faça login no Console

> **Sobre o cartão:** Oracle Cloud é Always Free — diferente de "free trial". Os recursos A1 ARM nunca expiram e nunca cobram. O cartão é só para verificação de identidade.

---

## PARTE 2 — Criar a VM (Instância ARM A1)

### 2.1 Acessar Compute

No menu do Console Oracle (☰):
> **Compute → Instances → Create Instance**

### 2.2 Configurar a instância

| Campo | Valor |
|---|---|
| **Name** | `coreextract-vm` |
| **Image** | Ubuntu 22.04 (clique em "Change image") |
| **Shape** | VM.Standard.A1.Flex (clique em "Change shape") |
| **OCPUs** | `2` |
| **Memory** | `12` GB |

### 2.3 Configurar SSH

- Em **"Add SSH keys"** → selecione **"Generate a key pair for me"**
- Clique em **"Save Private Key"** — salve o arquivo `.key` no seu computador
- (Guarde bem esse arquivo — é a única forma de acessar a VM)

### 2.4 Criar

Clique em **"Create"** e aguarde ~2 minutos até o status ficar verde (**Running**).

Anote o **IP Público** que aparece nos detalhes da instância.

---

## PARTE 3 — Abrir as portas (Firewall Oracle)

Por padrão, Oracle bloqueia todas as portas. Precisamos abrir 80 e 443.

1. Na página da instância, clique no link **"Subnet"** (ou vá em Networking → Virtual Cloud Networks)
2. Clique na sua **VCN** → **Security Lists** → **Default Security List**
3. Clique em **"Add Ingress Rules"** e adicione **duas regras**:

**Regra 1 — HTTP:**
- Source CIDR: `0.0.0.0/0`
- IP Protocol: `TCP`
- Destination Port: `80`

**Regra 2 — HTTPS:**
- Source CIDR: `0.0.0.0/0`
- IP Protocol: `TCP`
- Destination Port: `443`

Clique em **"Add Ingress Rules"**.

---

## PARTE 4 — Domínio gratuito (DuckDNS)

Precisamos de um domínio para o HTTPS funcionar.

1. Acesse: **https://www.duckdns.org/**
2. Faça login com Google/GitHub
3. Crie um subdomínio: `coreextract-bertoi` (ou o nome que quiser)
4. Em **"current ip"**, coloque o **IP Público** da sua VM Oracle
5. Clique em **"update ip"**

Você terá um domínio tipo: `coreextract-bertoi.duckdns.org`

> **Aguarde 1-2 minutos** para o DNS propagar antes de continuar.

---

## PARTE 5 — Conectar na VM e rodar o setup

### 5.1 Conectar via SSH

**No Windows**, abra o PowerShell:

```powershell
# Ajustar permissões do arquivo .key (necessário)
icacls "C:\Users\SEU_USUARIO\Downloads\ssh-key-XXXX.key" /inheritance:r /grant:r "$env:USERNAME:(R)"

# Conectar
ssh -i "C:\Users\SEU_USUARIO\Downloads\ssh-key-XXXX.key" ubuntu@IP_DA_VM
```

Quando perguntar "Are you sure you want to continue connecting?", digite `yes`.

### 5.2 Baixar e executar o script de setup

Já conectado na VM:

```bash
# Baixar o script de setup diretamente do seu repositório
curl -O https://raw.githubusercontent.com/MatGarciaBertoi/CoreExtract/master/setup_oracle.sh

# Dar permissão de execução
chmod +x setup_oracle.sh

# Executar
./setup_oracle.sh
```

O script vai:
1. ✅ Atualizar o Ubuntu
2. ✅ Instalar Python 3.12, nginx, certbot
3. ✅ Clonar seu repositório
4. ✅ Instalar todas as dependências
5. ✅ Pedir suas variáveis de ambiente (SECRET_KEY, Gemini API, SMTP etc)
6. ✅ Criar serviço systemd (auto-start, auto-restart)
7. ✅ Configurar nginx
8. ✅ Configurar HTTPS com certbot

Quando ele perguntar o domínio, coloque: `coreextract-bertoi.duckdns.org`

---

## PARTE 6 — Atualizar Streamlit Cloud

Após o CoreExtract estar rodando em `https://coreextract-bertoi.duckdns.org`:

1. Acesse **https://share.streamlit.io**
2. Clique em **"⋮"** no seu app → **"Settings"**
3. Vá em **"Secrets"** e atualize:

```toml
API_BASE_URL = "https://coreextract-bertoi.duckdns.org"
```

4. Clique em **"Save"** → **"Reboot app"**

---

## PARTE 7 — Atualizar link do Dashboard no frontend

No arquivo `C:\CoreExtract\templates\frontend.html`, na função `_initDashboardBtn`:

```javascript
btn.href = isLocal
  ? `http://${window.location.hostname}:8081`
  : 'https://coreextract-bertoi.streamlit.app';
```

Depois faça commit e push (o Oracle já atualiza automaticamente via `git pull`):

```bash
git add templates/frontend.html
git commit -m "fix: atualiza URL do dashboard para Streamlit Cloud"
git push
```

Na VM Oracle:
```bash
cd /opt/coreextract && git pull && sudo systemctl restart coreextract
```

---

## Resumo de URLs após migração

| Serviço | URL |
|---|---|
| CoreExtract (FastAPI) | https://coreextract-bertoi.duckdns.org |
| Dashboard (Streamlit) | https://coreextract-bertoi.streamlit.app |
| Health check | https://coreextract-bertoi.duckdns.org/health |

---

## Comandos de manutenção na VM

```bash
# Ver status do CoreExtract
sudo systemctl status coreextract

# Ver logs em tempo real
sudo journalctl -u coreextract -f

# Reiniciar
sudo systemctl restart coreextract

# Atualizar código após git push
cd /opt/coreextract && git pull && sudo systemctl restart coreextract

# Ver uso de memória e CPU
htop

# Acessar banco SQLite
sqlite3 /opt/coreextract_data/coreextract.db

# Fazer backup do banco
cp /opt/coreextract_data/coreextract.db ~/backup_$(date +%Y%m%d).db
```

---

## Renovação automática do SSL

O certbot já configura renovação automática (cron). Para verificar:

```bash
sudo certbot renew --dry-run
```

---

## Migrar banco de dados do Fly.io (opcional)

Se quiser trazer o banco existente do Fly.io:

```bash
# No seu computador Windows (PowerShell):
fly ssh sftp get /data/coreextract.db ./coreextract_backup.db

# Enviar para a VM Oracle:
scp -i "ssh-key-XXXX.key" coreextract_backup.db ubuntu@IP_DA_VM:/opt/coreextract_data/coreextract.db

# Na VM, reiniciar:
sudo systemctl restart coreextract
```

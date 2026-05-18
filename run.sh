#!/bin/bash
# ══════════════════════════════════════════════════════════
#  BTExtract — Inicialização no Linux/macOS
# ══════════════════════════════════════════════════════════
set -euo pipefail

# Verifica se o .env existe
if [ ! -f ".env" ]; then
    echo "[AVISO] Arquivo .env não encontrado. Copiando .env.example..."
    cp .env.example .env
    echo "IMPORTANTE: Edite o .env e adicione sua GROQ_API_KEY antes de continuar."
    echo "  nano .env   ou   code .env"
    exit 1
fi

# Cria venv se não existir
if [ ! -d "venv" ]; then
    echo "[1/3] Criando ambiente virtual Python..."
    python3 -m venv venv
fi

echo "[2/3] Ativando ambiente e instalando dependências..."
source venv/bin/activate
pip install -r requirements.txt --quiet

echo "[3/3] Iniciando BTExtract em http://localhost:8080"
echo ""
echo "  Acesse: http://localhost:8080"
echo "  Pressione Ctrl+C para parar"
echo ""

python main.py

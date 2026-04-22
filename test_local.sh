#!/bin/bash
# =============================================================================
# Testa o CoreExtract localmente com functions-framework
# =============================================================================
# Uso: bash test_local.sh caminho/para/curriculo.pdf [email@destino.com]
# =============================================================================

FILE=${1:-""}
EMAIL=${2:-""}

if [ -z "$FILE" ]; then
  echo "Uso: bash test_local.sh <arquivo> [email_destino]"
  exit 1
fi

# Inicia o servidor local em background (se não estiver rodando)
if ! lsof -i:8080 -t >/dev/null 2>&1; then
  echo "Iniciando functions-framework na porta 8080..."
  GCP_PROJECT_ID="local-test" \
  GCP_REGION="us-central1" \
    functions-framework --target=extract --port=8080 &
  SERVER_PID=$!
  sleep 2
fi

FILENAME=$(basename "$FILE")

# Monta os campos do e-mail se fornecido
EMAIL_FIELDS=""
if [ -n "$EMAIL" ]; then
  EMAIL_FIELDS="-F send_email=true \
    -F destinatario=${EMAIL} \
    -F tema=Triagem+de+Currículos \
    -F nome_recrutador=Recrutador+CoreExtract"
fi

echo "Enviando ${FILENAME} para http://localhost:8080..."
curl -s -X POST "http://localhost:8080" \
  -F "files=@${FILE};filename=${FILENAME}" \
  $EMAIL_FIELDS \
  | python3 -m json.tool

# Limpa o processo se foi iniciado por este script
[ -n "${SERVER_PID:-}" ] && kill "$SERVER_PID" 2>/dev/null

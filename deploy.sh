#!/bin/bash
# =============================================================================
# CoreExtract — Deploy para Google Cloud Functions (2ª geração)
# =============================================================================
# Pré-requisitos:
#   gcloud auth login
#   gcloud config set project SEU_PROJETO
#   gcloud services enable cloudfunctions.googleapis.com \
#     run.googleapis.com aiplatform.googleapis.com \
#     secretmanager.googleapis.com storage.googleapis.com
# =============================================================================

set -euo pipefail

PROJECT_ID="seu-projeto-gcp"
REGION="us-central1"
FUNCTION_NAME="coreextract-api"
BUCKET="coreextract-uploads"
SENDGRID_SECRET="sendgrid-api-key"

# 1. Cria o bucket de uploads (se não existir)
gcloud storage buckets create "gs://${BUCKET}" \
  --project="${PROJECT_ID}" \
  --location="${REGION}" \
  --uniform-bucket-level-access \
  2>/dev/null || echo "Bucket já existe, continuando..."

# 2. Armazena a API Key do SendGrid no Secret Manager
echo "Cole sua SendGrid API Key e pressione ENTER:"
read -rs SENDGRID_KEY
echo "${SENDGRID_KEY}" | gcloud secrets create "${SENDGRID_SECRET}" \
  --project="${PROJECT_ID}" \
  --data-file=- \
  2>/dev/null || \
  echo "${SENDGRID_KEY}" | gcloud secrets versions add "${SENDGRID_SECRET}" \
    --project="${PROJECT_ID}" \
    --data-file=-

# 3. Deploy da Cloud Function (HTTP trigger)
gcloud functions deploy "${FUNCTION_NAME}" \
  --gen2 \
  --runtime=python312 \
  --region="${REGION}" \
  --source=. \
  --entry-point=extract \
  --trigger-http \
  --allow-unauthenticated \
  --memory=1Gi \
  --cpu=1 \
  --timeout=120s \
  --min-instances=0 \
  --max-instances=10 \
  --concurrency=5 \
  --set-env-vars="GCP_PROJECT_ID=${PROJECT_ID},GCP_REGION=${REGION},GCS_BUCKET=${BUCKET}" \
  --project="${PROJECT_ID}"

echo ""
echo "✓ Deploy concluído!"
echo "URL da função:"
gcloud functions describe "${FUNCTION_NAME}" \
  --gen2 --region="${REGION}" --project="${PROJECT_ID}" \
  --format="value(serviceConfig.uri)"

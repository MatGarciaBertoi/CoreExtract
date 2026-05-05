#!/bin/bash
set -e

# ── Environment defaults ────────────────────────────────────────────────────
export CE_DB_PATH="${CE_DB_PATH:-/data/coreextract.db}"
export PORT="${PORT:-8080}"

echo "============================================================"
echo "  CoreExtract - RH Inteligente"
echo "  DB   : $CE_DB_PATH"
echo "  PORT : $PORT"
echo "============================================================"

# ── Generate nginx config with actual PORT ──────────────────────────────────
envsubst '${PORT}' < /app/nginx.conf.template > /tmp/nginx.conf

# ── Start all services via supervisord ─────────────────────────────────────
exec supervisord -n -c /app/supervisord.conf

#!/bin/bash
set -e

# ── Environment defaults ────────────────────────────────────────────────────
export BT_DB_PATH="${BT_DB_PATH:-/data/btextract.db}"
export PORT="${PORT:-8080}"

echo "============================================================"
echo "  BTExtract - RH Inteligente"
echo "  DB   : $BT_DB_PATH"
echo "  PORT : $PORT"
echo "============================================================"

# ── Generate nginx config with actual PORT ──────────────────────────────────
envsubst '${PORT}' < /app/nginx.conf.template > /tmp/nginx.conf

# ── Start all services via supervisord ─────────────────────────────────────
exec supervisord -n -c /app/supervisord.conf

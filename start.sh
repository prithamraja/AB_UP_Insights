#!/usr/bin/env bash
# Railway entrypoint for the AB-UP dashboard frontend.
# Builds the Vite app on first boot, then serves it on $PORT.

set -euo pipefail

cd frontend/ab-dashboard-main

if [ ! -d "node_modules" ]; then
  echo "[start.sh] Installing dependencies..."
  npm ci --legacy-peer-deps || npm install --legacy-peer-deps
fi

if [ ! -d "dist" ]; then
  echo "[start.sh] Building production bundle..."
  npm run build
fi

PORT="${PORT:-8080}"
echo "[start.sh] Serving on 0.0.0.0:${PORT}"
exec npx vite preview --host 0.0.0.0 --port "${PORT}"

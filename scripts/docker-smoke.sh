#!/usr/bin/env bash
# Smoke-test the Docker stack on a fresh machine.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  echo "✗ Missing .env — run: cp .env.example .env && fill in Phoenix, Supabase, Gemini keys"
  exit 1
fi

echo "=== Building & starting docker compose ==="
docker compose up --build -d

echo "=== Waiting for backend health ==="
for i in {1..30}; do
  if curl -sf http://localhost:8000/health >/dev/null; then
    echo "✓ backend healthy"
    break
  fi
  sleep 2
  if [[ $i -eq 30 ]]; then
    echo "✗ backend did not become healthy"
    docker compose logs backend
    exit 1
  fi
done

echo "=== Health payload ==="
curl -s http://localhost:8000/health | python3 -m json.tool

echo "=== Frontend reachable ==="
if curl -sf http://localhost:5173 >/dev/null; then
  echo "✓ frontend responding on http://localhost:5173"
else
  echo "⚠ frontend not ready yet — check: docker compose logs frontend"
fi

echo ""
echo "Open http://localhost:5173 — click Sync ERP, open ticket 7001, run the agent loop."
echo "Stop stack: docker compose down"

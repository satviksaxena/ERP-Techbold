#!/usr/bin/env bash
# Stable backend for demos — no --reload (reload kills in-flight SSH/Gemini and sticks the UI).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/backend"
export LLM_PRIMARY=gemini
exec .venv312/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000

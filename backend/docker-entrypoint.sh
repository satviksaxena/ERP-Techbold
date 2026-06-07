#!/bin/sh
set -e

missing=""
for var in SUPABASE_URL SUPABASE_SERVICE_ROLE_KEY PHOENIX_API_BASE_URL PHOENIX_API_TOKEN; do
  eval "val=\${$var:-}"
  if [ -z "$val" ]; then
    missing="$missing  - $var\n"
  fi
done

if [ -n "$missing" ]; then
  echo "ERROR: Required variables missing from .env:"
  printf "%b" "$missing"
  echo "Copy .env.example to .env and fill in values before running docker compose."
  exit 1
fi

if [ ! -f "${SSH_PRIVATE_KEY_PATH:-/keys/case1_key.pem}" ]; then
  echo "ERROR: SSH key not found at ${SSH_PRIVATE_KEY_PATH:-/keys/case1_key.pem}"
  echo "Place case1_key.pem … case5_key.pem in tb-hackathon-ssh/ (see tb-hackathon-ssh/README.txt)."
  exit 1
fi

if [ -z "${GEMINI_API_KEY:-}" ]; then
  echo "WARNING: GEMINI_API_KEY is not set — AI command proposals will use rule-based fallbacks only."
fi

export LLM_PRIMARY=gemini

exec uvicorn app.main:app --host 0.0.0.0 --port 8000

#!/usr/bin/env bash
# One-command start for recipients — requires .env + tb-hackathon-ssh/*.pem only.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  echo "Missing .env — copy .env.example to .env and fill in credentials."
  exit 1
fi

if ! compgen -G "tb-hackathon-ssh/*.pem" >/dev/null; then
  echo "Missing SSH keys in tb-hackathon-ssh/ — see tb-hackathon-ssh/README.txt"
  exit 1
fi

echo "Building and starting AI Service Desk Autopilot..."
docker compose up --build "$@"

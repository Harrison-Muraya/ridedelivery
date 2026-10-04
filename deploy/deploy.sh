#!/usr/bin/env bash
# Build and (re)start the production stack on the VPS.
# Usage (from repo root):
#   ./deploy/deploy.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  echo "Missing .env — copy .env.production.example and fill in secrets:"
  echo "  cp .env.production.example .env"
  exit 1
fi

# shellcheck disable=SC1091
set -a
source .env
set +a

if [[ -z "${POSTGRES_PASSWORD:-}" || "${POSTGRES_PASSWORD}" == "change-me-strong-db-password" ]]; then
  echo "Set a real POSTGRES_PASSWORD in .env before deploying."
  exit 1
fi

if [[ -z "${SECRET_KEY:-}" || "${SECRET_KEY}" == "change-me-to-a-long-random-string" ]]; then
  echo "Set a real SECRET_KEY in .env before deploying."
  exit 1
fi

chmod +x deploy/entrypoint.sh

echo "==> Building images"
docker compose -f docker-compose.prod.yml build

echo "==> Starting stack"
docker compose -f docker-compose.prod.yml up -d

echo "==> Status"
docker compose -f docker-compose.prod.yml ps

echo
echo "API is bound to http://127.0.0.1:8000"
echo "Health check: curl -s http://127.0.0.1:8000/health"
echo "Put Nginx/Certbot in front for public HTTPS (deploy/nginx/ridedelivery.conf)."

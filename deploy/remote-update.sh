#!/usr/bin/env bash
# Pulled/run by GitHub Actions CD over SSH.
# Expects the repo already cloned at DEPLOY_PATH (default /opt/ridedelivery).

set -euo pipefail

DEPLOY_PATH="${DEPLOY_PATH:-/opt/ridedelivery}"
cd "$DEPLOY_PATH"

echo "==> Updating code"
git fetch --all --prune
git reset --hard "origin/${DEPLOY_BRANCH:-main}"

# shellcheck disable=SC1091
set -a
source .env
set +a

APP_IMAGE="${APP_IMAGE:-ghcr.io/harrison-muraya/ridedelivery:latest}"
export APP_IMAGE

if [[ -n "${GHCR_TOKEN:-}" ]]; then
  echo "==> Logging in to ghcr.io"
  echo "$GHCR_TOKEN" | docker login ghcr.io -u "${GHCR_USER:-harrison-muraya}" --password-stdin
fi

echo "==> Pulling image ${APP_IMAGE}"
docker compose -f docker-compose.prod.yml pull api worker-rides worker-notifications worker-payments || true

echo "==> Recreating app containers"
docker compose -f docker-compose.prod.yml up -d --remove-orphans

echo "==> Pruning old images"
docker image prune -f >/dev/null || true

echo "==> Health check"
sleep 5
curl -fsS http://127.0.0.1:8000/health || {
  echo "Health check failed — recent api logs:"
  docker compose -f docker-compose.prod.yml logs --tail=80 api
  exit 1
}

echo "Deploy OK"
docker compose -f docker-compose.prod.yml ps

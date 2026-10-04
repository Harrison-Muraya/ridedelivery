#!/usr/bin/env bash
# One-time bootstrap on the Ubuntu VPS (run as harr after SSH login).
# Usage:
#   curl -fsSL ... | bash
# or from a cloned repo:
#   chmod +x deploy/bootstrap-vps.sh && ./deploy/bootstrap-vps.sh

set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/Harrison-Muraya/ridedelivery.git}"
DEPLOY_PATH="${DEPLOY_PATH:-/opt/ridedelivery}"
DOMAIN="${DOMAIN:-}"   # optional: api.example.com

echo "==> Installing Docker / Nginx / Certbot (if needed)"
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker "$USER"
fi
sudo apt-get update -y
sudo apt-get install -y git nginx certbot python3-certbot-nginx ufw curl

echo "==> Firewall"
sudo ufw allow OpenSSH || true
sudo ufw allow 1515/tcp || true
sudo ufw allow 'Nginx Full' || true
sudo ufw --force enable || true

echo "==> Clone / update repo at ${DEPLOY_PATH}"
if [[ ! -d "${DEPLOY_PATH}/.git" ]]; then
  sudo mkdir -p "$(dirname "$DEPLOY_PATH")"
  sudo git clone "$REPO_URL" "$DEPLOY_PATH"
  sudo chown -R "$USER:$USER" "$DEPLOY_PATH"
else
  git -C "$DEPLOY_PATH" pull --ff-only || true
fi
cd "$DEPLOY_PATH"
chmod +x deploy/*.sh deploy/entrypoint.sh || true

if [[ ! -f .env ]]; then
  cp .env.production.example .env
  SECRET="$(openssl rand -hex 32)"
  DBPASS="$(openssl rand -hex 16)"
  sed -i "s/change-me-to-a-long-random-string/${SECRET}/" .env
  sed -i "s/change-me-strong-db-password/${DBPASS}/g" .env
  echo "Created .env with generated SECRET_KEY and POSTGRES_PASSWORD"
  echo "Edit M-Pesa keys before going live: nano ${DEPLOY_PATH}/.env"
fi

# Prefer GHCR image when CD is configured; first boot can also build locally.
if ! grep -q '^APP_IMAGE=' .env 2>/dev/null; then
  echo 'APP_IMAGE=ghcr.io/harrison-muraya/ridedelivery:latest' >> .env
fi

echo "==> First start (may build if image pull fails)"
./deploy/deploy.sh || {
  echo "Pull failed or image private — building on the VPS instead..."
  sed -i '/^APP_IMAGE=/d' .env || true
  ./deploy/deploy.sh
}

if [[ -n "$DOMAIN" ]]; then
  echo "==> Configuring Nginx for ${DOMAIN}"
  sudo sed "s/api.yourdomain.com/${DOMAIN}/g" deploy/nginx/ridedelivery.conf \
    | sudo tee /etc/nginx/sites-available/ridedelivery >/dev/null
  sudo ln -sf /etc/nginx/sites-available/ridedelivery /etc/nginx/sites-enabled/
  sudo rm -f /etc/nginx/sites-enabled/default
  sudo nginx -t && sudo systemctl reload nginx
  sudo certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "admin@${DOMAIN}" || \
    echo "Certbot needs a valid DNS A record for ${DOMAIN}. Run certbot manually later."
fi

echo
echo "Bootstrap complete."
echo "Health: curl -s http://127.0.0.1:8000/health"
echo "If you are not in the docker group yet, run: newgrp docker"
echo "Then add the GitHub deploy public key to ~/.ssh/authorized_keys (see deploy/VPS_CD.md)."

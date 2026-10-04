#!/usr/bin/env bash
# Run once on a fresh Ubuntu Server as a sudo-capable user:
#   curl -fsSL ... | bash
# or:
#   chmod +x deploy/setup-ubuntu.sh && ./deploy/setup-ubuntu.sh

set -euo pipefail

if [[ "${EUID}" -eq 0 ]]; then
  echo "Run this script as a normal user with sudo, not as root."
  exit 1
fi

echo "==> Updating apt"
sudo apt-get update -y
sudo apt-get upgrade -y

echo "==> Installing Docker"
sudo apt-get install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
if [[ ! -f /etc/apt/keyrings/docker.gpg ]]; then
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  sudo chmod a+r /etc/apt/keyrings/docker.gpg
fi

. /etc/os-release
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update -y
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

echo "==> Allowing ${USER} to run docker"
sudo usermod -aG docker "$USER"

echo "==> Installing nginx + certbot"
sudo apt-get install -y nginx certbot python3-certbot-nginx git ufw

echo "==> Configuring firewall (OpenSSH, HTTP, HTTPS)"
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw --force enable

echo
echo "Done. Log out and back in (or run: newgrp docker), then:"
echo "  1. Clone the repo to /opt/ridedelivery (or any path)"
echo "  2. cp .env.production.example .env  &&  edit secrets"
echo "  3. ./deploy/deploy.sh"
echo "  4. Configure nginx + certbot (see deploy/nginx/ridedelivery.conf)"

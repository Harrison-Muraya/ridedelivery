#!/usr/bin/env bash
# Replace the default Nginx site with the RideDelivery API on port 80.
# Run on the VPS:
#   sudo bash /opt/ridedelivery/deploy/switch-to-port80.sh

set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo bash $0"
  exit 1
fi

SITE_SRC="/opt/ridedelivery/deploy/nginx/ridedelivery.conf"
SITE_AVAIL="/etc/nginx/sites-available/ridedelivery"
SITE_ENABLED="/etc/nginx/sites-enabled/ridedelivery"

# Proxy by IP or any Host header on port 80
cat > "$SITE_AVAIL" <<'EOF'
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;

    client_max_body_size 10m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Connection "";
        proxy_read_timeout 120s;
    }
}
EOF

# Remove other enabled sites (keeps files in sites-available)
rm -f /etc/nginx/sites-enabled/default
rm -f /etc/nginx/sites-enabled/*
ln -sf "$SITE_AVAIL" "$SITE_ENABLED"

# API only needs to listen locally when Nginx fronts it
if [[ -f /opt/ridedelivery/docker-compose.prod.yml ]]; then
  sed -i 's/0.0.0.0:8000:8000/127.0.0.1:8000:8000/' /opt/ridedelivery/docker-compose.prod.yml || true
  sed -i 's/"8000:8000"/"127.0.0.1:8000:8000"/' /opt/ridedelivery/docker-compose.prod.yml || true
fi

nginx -t
systemctl reload nginx

# Ensure API is up and bound for the proxy
cd /opt/ridedelivery
sudo -u harr docker compose -f docker-compose.prod.yml up -d api

ufw allow 'Nginx Full' || true
ufw allow OpenSSH || true
ufw allow 1515/tcp || true
ufw --force enable || true

sleep 2
echo "=== Local via Nginx ==="
curl -sS http://127.0.0.1/health || true
echo
echo "Done. Router maps external 1516 -> internal 80."
echo "Public health: http://197.248.201.233:1516/health"
echo "Public docs:   http://197.248.201.233:1516/docs"
echo "API base:      http://197.248.201.233:1516/api/v1/"

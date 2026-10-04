#!/usr/bin/env bash
# Replace default Nginx welcome page with FastAPI reverse proxy.
# Uses Docker (no sudo password). Run as harr:
#   bash /opt/ridedelivery/deploy/force-nginx-api.sh

set -euo pipefail
cd /opt/ridedelivery

CONF_SRC="/opt/ridedelivery/deploy/nginx/ridedelivery-port80.conf"

echo "==> Installing Nginx site via Docker volume mount"
docker run --rm \
  -v "$CONF_SRC:/tmp/ridedelivery.conf:ro" \
  -v /etc/nginx:/etc/nginx \
  alpine:3.20 sh -c '
set -e
cp /tmp/ridedelivery.conf /etc/nginx/sites-available/ridedelivery
rm -f /etc/nginx/sites-enabled/default
rm -f /etc/nginx/sites-enabled/*
ln -sf /etc/nginx/sites-available/ridedelivery /etc/nginx/sites-enabled/ridedelivery
ls -la /etc/nginx/sites-enabled/
cat /etc/nginx/sites-enabled/ridedelivery
'

echo "==> Ensuring API listens on 127.0.0.1:8000"
sed -i 's/0.0.0.0:8000:8000/127.0.0.1:8000:8000/' docker-compose.prod.yml || true
docker compose -f docker-compose.prod.yml up -d api
sleep 4
curl -fsS http://127.0.0.1:8000/health
echo

echo "==> Testing and reloading host Nginx"
docker run --rm --privileged --pid=host alpine:3.20 \
  nsenter -t 1 -m -u -i -n sh -c 'nginx -t && nginx -s reload'

sleep 2
echo "==> Via Nginx :80"
curl -fsS http://127.0.0.1/health
echo
curl -fsS -o /dev/null -w "docs:%{http_code}\n" http://127.0.0.1/docs

echo
echo "Open:   http://197.248.201.233:1516/docs"
echo "Health: http://197.248.201.233:1516/health"

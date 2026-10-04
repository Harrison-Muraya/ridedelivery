# VPS continuous deployment

Target server:

- Host: `197.248.201.233`
- User: `harr`
- Port: `1515`
- App path: `/opt/ridedelivery`

## 1. One-time: install the deploy public key on the VPS

From your PC (password login once):

```bash
ssh -p 1515 harr@197.248.201.233
```

On the VPS:

```bash
mkdir -p ~/.ssh && chmod 700 ~/.ssh
echo 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIK3tsu12EZ0WkvzovSULpp0gW5njbSl8vT5jpvFdvsF8 ridedelivery-github-actions-cd' >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

## 2. One-time: bootstrap the app

Still on the VPS (or after reconnecting):

```bash
# Option A — clone then bootstrap
git clone https://github.com/Harrison-Muraya/ridedelivery.git /tmp/ridedelivery-bootstrap
sudo mkdir -p /opt
sudo mv /tmp/ridedelivery-bootstrap /opt/ridedelivery
sudo chown -R harr:harr /opt/ridedelivery
cd /opt/ridedelivery
chmod +x deploy/*.sh
./deploy/bootstrap-vps.sh
# optional domain:
# DOMAIN=api.yourdomain.com ./deploy/bootstrap-vps.sh
```

Edit M-Pesa + callback URL:

```bash
nano /opt/ridedelivery/.env
```

If the GHCR image is private, create a GitHub PAT with `read:packages` and add to `.env`:

```bash
GHCR_USER=Harrison-Muraya
GHCR_TOKEN=ghp_xxx
APP_IMAGE=ghcr.io/harrison-muraya/ridedelivery:latest
```

## 3. One-time: GitHub Actions secrets / variables

Repo → **Settings → Secrets and variables → Actions**

| Name | Type | Value |
|------|------|-------|
| `VPS_SSH_KEY` | Secret | Full private key from `~/.ssh/ridedelivery_vps_deploy` on your PC |
| `VPS_HOST` | Variable or secret | `197.248.201.233` |
| `VPS_USER` | Variable or secret | `harr` |
| `VPS_PORT` | Variable or secret | `1515` |
| `GHCR_PULL_TOKEN` | Secret (if private image) | PAT with `read:packages` |
| `GHCR_USER` | Secret (optional) | `Harrison-Muraya` |

Private key path on your Windows PC:

`C:\Users\hezro\.ssh\ridedelivery_vps_deploy`

## 4. Make it live with Nginx

Point DNS A record → `197.248.201.233`, then:

```bash
sudo sed 's/api.yourdomain.com/YOUR_DOMAIN/g' /opt/ridedelivery/deploy/nginx/ridedelivery.conf \
  | sudo tee /etc/nginx/sites-available/ridedelivery
sudo ln -sf /etc/nginx/sites-available/ridedelivery /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d YOUR_DOMAIN
```

## 5. How CD works after that

1. Push to `main` → **CI** runs tests  
2. On CI success → **CD** builds/pushes `ghcr.io/harrison-muraya/ridedelivery:latest`  
3. CD SSHs into the VPS and runs `deploy/remote-update.sh` (pull image + restart)

Manual deploy from your PC after key auth works:

```bash
ssh -i ~/.ssh/ridedelivery_vps_deploy -p 1515 harr@197.248.201.233 'cd /opt/ridedelivery && ./deploy/remote-update.sh'
```

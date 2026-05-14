#!/usr/bin/env bash
# install_dashboard.sh — отдельно ставит дашборд (Node 22 + Caddy + frontend
# build + systemd unit для FastAPI server).
#
# Запускать ПОСЛЕ scripts/deploy/install.sh (бот уже стоит).
#
#   sudo bash /opt/crypto/scripts/deploy/install_dashboard.sh
#
# После этого:
#   - FastAPI на 127.0.0.1:8081 (systemd: crypto-dashboard.service)
#   - Caddy на :80 (статика из /opt/crypto/web/dist + reverse /api → 8081)
#   - Открой в Safari: http://<VPS_IP>/

set -euo pipefail

INSTALL_DIR="/opt/crypto"
USER_NAME="crypto"

if [[ "${EUID}" -ne 0 ]]; then
  echo "ERROR: run with sudo" >&2
  exit 1
fi

if [[ ! -d "${INSTALL_DIR}" ]]; then
  echo "ERROR: ${INSTALL_DIR} не найден — сначала запусти install.sh" >&2
  exit 1
fi

echo "==> [1/6] Node.js 22 + npm"
if ! command -v node >/dev/null 2>&1 || [[ "$(node -v 2>/dev/null | cut -d. -f1 | tr -d v)" -lt 22 ]]; then
  # Node 22 LTS из NodeSource
  curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
  apt-get install -y -qq nodejs
fi
node --version
npm --version

echo "==> [2/6] Build frontend (Vite)"
cd "${INSTALL_DIR}/web"
sudo -u "${USER_NAME}" npm install --no-audit --no-fund --silent
sudo -u "${USER_NAME}" npm run build
ls -lh dist/
cd -

echo "==> [3/6] Install fastapi + uvicorn в python venv"
sudo -u "${USER_NAME}" "${INSTALL_DIR}/.venv/bin/pip" install -q -e "${INSTALL_DIR}[dashboard]"

echo "==> [4/6] Systemd unit crypto-dashboard"
install -m 644 "${INSTALL_DIR}/scripts/deploy/crypto-dashboard.service" \
  /etc/systemd/system/crypto-dashboard.service
systemctl daemon-reload
systemctl enable --now crypto-dashboard
sleep 2
systemctl status crypto-dashboard --no-pager -l | head -10

echo "==> [5/6] Caddy reverse proxy + static"
if ! command -v caddy >/dev/null 2>&1; then
  apt-get install -y -qq debian-keyring debian-archive-keyring apt-transport-https curl
  curl -fsSL https://dl.cloudsmith.io/public/caddy/stable/gpg.key \
    | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -fsSL https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt \
    | tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
  apt-get update -qq
  apt-get install -y -qq caddy
fi
mkdir -p /var/log/caddy
chown caddy:caddy /var/log/caddy

# Copy наш Caddyfile, оставляя бэкап существующего
if [[ -f /etc/caddy/Caddyfile && ! -f /etc/caddy/Caddyfile.orig ]]; then
  cp /etc/caddy/Caddyfile /etc/caddy/Caddyfile.orig
fi
install -m 644 "${INSTALL_DIR}/scripts/deploy/Caddyfile" /etc/caddy/Caddyfile

systemctl restart caddy
sleep 2
systemctl status caddy --no-pager -l | head -10

echo "==> [6/6] ufw: open port 80"
ufw allow 80/tcp || true
# Если будет домен с HTTPS:
# ufw allow 443/tcp

cat <<EOF

================================================================================
DASHBOARD DEPLOYED.

Открой в Safari (Mac или iPhone):
  http://$(curl -fsSL -m 3 ifconfig.me 2>/dev/null || echo "<VPS_IP>")/

Проверки:
  sudo systemctl status crypto-dashboard
  sudo systemctl status caddy
  curl -fsSL http://127.0.0.1:8081/api/health
  curl -fsSL http://127.0.0.1/

Когда подключишь домен (например crypto.example.com → твой IP в DNS):
  1. Edit /etc/caddy/Caddyfile — замени ':80' на 'crypto.example.com'
  2. sudo systemctl reload caddy
  3. sudo ufw allow 443/tcp
  Caddy сам возьмёт Let's Encrypt сертификат → HTTPS заработает.

================================================================================
EOF

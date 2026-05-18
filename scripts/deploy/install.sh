#!/usr/bin/env bash
# install.sh — идемпотентная установка crypto-бота на Ubuntu 24.04 LTS.
#
# Запуск (НА VPS, под root через sudo):
#   sudo bash install.sh
#
# Что делает:
# 1. apt-get update + install Python 3.12, git, ufw, fail2ban
# 2. Создаёт системного пользователя `crypto`
# 3. Клонирует репо в /opt/crypto (если ещё нет)
# 4. Создаёт venv + ставит зависимости
# 5. Создаёт /etc/crypto/.env шаблон (chmod 600)
# 6. Создаёт /var/lib/crypto (для journal/metrics)
# 7. Ставит systemd unit + logrotate config
# 8. Включает ufw (только SSH + healthz)
# 9. Включает fail2ban
#
# НЕ запускает раннеры — это делает пользователь после заполнения .env:
#   sudo systemctl enable --now crypto-runner@BTC-USDT
#   sudo systemctl enable --now crypto-runner@ETH-USDT
#   sudo systemctl enable --now crypto-runner@XRP-USDT

set -euo pipefail

REPO_URL="https://github.com/stupolus/Crypto.git"
INSTALL_DIR="/opt/crypto"
DATA_DIR="/var/lib/crypto"
ENV_DIR="/etc/crypto"
USER_NAME="crypto"

# ── 0. Pre-flight ────────────────────────────────────────────────────────────
if [[ "${EUID}" -ne 0 ]]; then
  echo "ERROR: run with sudo (need root for apt/systemd)" >&2
  exit 1
fi

if [[ ! -f /etc/os-release ]]; then
  echo "ERROR: /etc/os-release missing — unsupported OS" >&2
  exit 1
fi
. /etc/os-release
if [[ "${ID:-}" != "ubuntu" && "${ID:-}" != "debian" ]]; then
  echo "WARNING: tested on Ubuntu/Debian, you have ${ID:-unknown}. Continuing..." >&2
fi

echo "==> [1/9] apt-get install dependencies"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
# Ubuntu 24.04 LTS shipping python3.12; Ubuntu 25.10+ shipping python3.13.
# Codebase requires 3.12+, обе версии работают. Выбираем доступное.
if apt-cache show python3.12 >/dev/null 2>&1; then
  PYTHON_PKGS="python3.12 python3.12-venv python3.12-dev"
  PYTHON_BIN="python3.12"
else
  PYTHON_PKGS="python3 python3-venv python3-dev"
  PYTHON_BIN="python3"
  echo "    (using system python3 — python3.12 not available in this Ubuntu)"
fi
# shellcheck disable=SC2086
apt-get install -y -qq ${PYTHON_PKGS} git curl ufw fail2ban logrotate

echo "==> [2/9] create user '${USER_NAME}'"
if ! id "${USER_NAME}" >/dev/null 2>&1; then
  useradd -r -m -d "${INSTALL_DIR}" -s /bin/bash "${USER_NAME}"
fi

echo "==> [3/9] clone repo to ${INSTALL_DIR}"
if [[ ! -d "${INSTALL_DIR}/.git" ]]; then
  sudo -u "${USER_NAME}" git clone "${REPO_URL}" "${INSTALL_DIR}"
else
  sudo -u "${USER_NAME}" git -C "${INSTALL_DIR}" pull origin main
fi

echo "==> [4/9] venv + dependencies (${PYTHON_BIN})"
if [[ ! -d "${INSTALL_DIR}/.venv" ]]; then
  sudo -u "${USER_NAME}" "${PYTHON_BIN}" -m venv "${INSTALL_DIR}/.venv"
fi
sudo -u "${USER_NAME}" "${INSTALL_DIR}/.venv/bin/pip" install -q --upgrade pip
sudo -u "${USER_NAME}" "${INSTALL_DIR}/.venv/bin/pip" install -q -e "${INSTALL_DIR}[dev]"

echo "==> [5/9] create ${ENV_DIR}/.env template"
mkdir -p "${ENV_DIR}"
chmod 750 "${ENV_DIR}"
chown root:"${USER_NAME}" "${ENV_DIR}"
if [[ ! -f "${ENV_DIR}/.env" ]]; then
  cat > "${ENV_DIR}/.env" <<'EOF'
# BingX VST (testnet) — для D3 demo. Получить в BingX → API Management.
BINGX_ENV=vst
BINGX_VST_API_KEY=
BINGX_VST_API_SECRET=

# BingX Live — для реальной торговли (заполнить после VST validation).
# BINGX_LIVE_API_KEY=
# BINGX_LIVE_API_SECRET=

# Telegram алерты — опционально, но рекомендуется на D3 и обязательно на live.
# Получить:
#   1. @BotFather → /newbot → TOKEN
#   2. Открыть чат с ботом, написать сообщение
#   3. https://api.telegram.org/bot<TOKEN>/getUpdates → chat.id
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
EOF
  chmod 600 "${ENV_DIR}/.env"
  chown root:"${USER_NAME}" "${ENV_DIR}/.env"
  echo "  Created ${ENV_DIR}/.env — заполни VST ключи + Telegram"
fi

echo "==> [6/9] data dir ${DATA_DIR}"
mkdir -p "${DATA_DIR}"
chown -R "${USER_NAME}":"${USER_NAME}" "${DATA_DIR}"
chmod 750 "${DATA_DIR}"

echo "==> [7/9] systemd unit + logrotate"
install -m 644 "${INSTALL_DIR}/scripts/deploy/crypto-runner@.service" \
  /etc/systemd/system/crypto-runner@.service
# Phase E LLM runner (новый) + post-mortem timer
install -m 644 "${INSTALL_DIR}/scripts/deploy/crypto-llm-runner@.service" \
  /etc/systemd/system/crypto-llm-runner@.service
install -m 644 "${INSTALL_DIR}/scripts/deploy/crypto-postmortem.service" \
  /etc/systemd/system/crypto-postmortem.service
install -m 644 "${INSTALL_DIR}/scripts/deploy/crypto-postmortem.timer" \
  /etc/systemd/system/crypto-postmortem.timer
install -m 644 "${INSTALL_DIR}/scripts/deploy/faber-vst.service" \
  /etc/systemd/system/faber-vst.service
install -m 644 "${INSTALL_DIR}/scripts/deploy/faber-vst.timer" \
  /etc/systemd/system/faber-vst.timer
install -m 644 "${INSTALL_DIR}/scripts/deploy/logrotate.conf" \
  /etc/logrotate.d/crypto
systemctl daemon-reload

echo "==> [8/9] ufw firewall (SSH + healthz only)"
if ufw status | grep -q "Status: inactive"; then
  ufw --force enable
fi
ufw allow 22/tcp
# 8080 пока не открываем — healthz запустим позже
echo "  SSH allowed. healthz port 8080 — открой когда будет UptimeRobot готов:"
echo "    sudo ufw allow from <UPTIMEROBOT_IP> to any port 8080"

echo "==> [9/9] fail2ban"
systemctl enable --now fail2ban

cat <<'EOF'

================================================================================
УСТАНОВКА ЗАВЕРШЕНА.

Следующие шаги:

  1. Заполни /etc/crypto/.env:
       sudo nano /etc/crypto/.env

     Минимум: BINGX_VST_API_KEY, BINGX_VST_API_SECRET.
     Рекомендую: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID.

  2. Запусти diagnose (проверка конфига):
       sudo -u crypto /opt/crypto/.venv/bin/python -m scripts.diagnose

  3. Включи Phase E LLM runner (с Layer 6 post-mortem):
       sudo systemctl enable --now crypto-llm-runner@BTC-USDT

     Или legacy без LLM (если нет ANTHROPIC_API_KEY):
       sudo systemctl enable --now crypto-runner@BTC-USDT

  4. Включи daily post-mortem обработку loss-сделок:
       sudo systemctl enable --now crypto-postmortem.timer

  5. Проверь что работают:
       sudo systemctl status crypto-llm-runner@BTC-USDT
       sudo journalctl -u 'crypto-llm-runner@*' -f

  6. Через 15 минут проверь, что прилетели close events:
       sudo journalctl -u crypto-llm-runner@BTC-USDT | grep "candle closed"

  7. Ежедневная сводка:
       sudo -u crypto /opt/crypto/.venv/bin/python -m scripts.daily_summary

================================================================================
EOF

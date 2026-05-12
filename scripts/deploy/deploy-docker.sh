#!/usr/bin/env bash
# deploy-docker.sh — деплой crypto-бота в Docker на VPS с другими сервисами.
#
# Запуск (НА VPS, под root):
#   sudo bash deploy-docker.sh
#
# Что делает:
# 1. Проверяет что Docker есть
# 2. Клонирует / обновляет репо в /opt/crypto-bot
# 3. Создаёт /etc/crypto/.env шаблон если нет
# 4. Build образа
# 5. docker compose up -d
#
# НЕ перезапускает работающий стек если .env пустой.

set -euo pipefail

REPO_URL="https://github.com/stupolus/Crypto.git"
INSTALL_DIR="/opt/crypto-bot"
ENV_DIR="/etc/crypto"

if [[ "${EUID}" -ne 0 ]]; then
  echo "ERROR: run with sudo" >&2
  exit 1
fi

echo "==> [1/5] Проверка Docker"
if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: Docker не установлен. На Hostinger обычно уже есть." >&2
  echo "       Установи: curl -fsSL https://get.docker.com | sh" >&2
  exit 1
fi
docker --version
echo "Текущие контейнеры (для справки):"
docker ps --format "  {{.Names}} - {{.Image}}" | head -10

echo "==> [2/5] Клон/обновление репо"
if [[ ! -d "${INSTALL_DIR}/.git" ]]; then
  git clone "${REPO_URL}" "${INSTALL_DIR}"
else
  git -C "${INSTALL_DIR}" pull origin main
fi

echo "==> [3/5] Конфиг .env в ${ENV_DIR}"
mkdir -p "${ENV_DIR}"
chmod 750 "${ENV_DIR}"
if [[ ! -f "${ENV_DIR}/.env" ]]; then
  cp "${INSTALL_DIR}/scripts/deploy/.env.example" "${ENV_DIR}/.env"
  chmod 600 "${ENV_DIR}/.env"
  echo ""
  echo "  ⚠️  ${ENV_DIR}/.env создан как шаблон. Заполни ключи:"
  echo "       sudo nano ${ENV_DIR}/.env"
  echo ""
  echo "  После заполнения — повтори этот скрипт."
  exit 0
fi

# Проверка что ключи заполнены
if ! grep -q "^BINGX_VST_API_KEY=.\+" "${ENV_DIR}/.env"; then
  echo "ERROR: BINGX_VST_API_KEY пустой в ${ENV_DIR}/.env" >&2
  echo "       sudo nano ${ENV_DIR}/.env" >&2
  exit 1
fi

echo "==> [4/5] Build Docker образа crypto-bot:latest"
cd "${INSTALL_DIR}"
docker compose -f scripts/deploy/docker-compose.yml build

echo "==> [5/5] Запуск контейнеров"
docker compose -f scripts/deploy/docker-compose.yml up -d

echo ""
echo "================================================================================"
echo "✅ ДЕПЛОЙ ЗАВЕРШЁН"
echo ""
echo "Контейнеры:"
docker compose -f scripts/deploy/docker-compose.yml ps
echo ""
echo "Логи (live):"
echo "  docker compose -f ${INSTALL_DIR}/scripts/deploy/docker-compose.yml logs -f"
echo ""
echo "Конкретный контейнер:"
echo "  docker logs -f crypto-btc"
echo ""
echo "Через 15 минут проверить close events:"
echo "  docker logs crypto-btc | grep 'candle closed'"
echo ""
echo "Стоп всё:"
echo "  docker compose -f ${INSTALL_DIR}/scripts/deploy/docker-compose.yml down"
echo "================================================================================"

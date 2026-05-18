# Crypto Bot Deploy

Два варианта деплоя:

## Вариант A: Docker compose (рекомендуется для VPS с другими сервисами)

Используется когда на VPS уже работает что-то ещё (например, Hostinger VPS с Odoo).
Контейнерная изоляция: отдельная сеть, resource limits (0.5 CPU + 512MB RAM на контейнер),
read-only root FS, non-root user, drop ALL capabilities.

```bash
ssh root@<your-vps-ip>
wget https://raw.githubusercontent.com/stupolus/Crypto/main/scripts/deploy/deploy-docker.sh
sudo bash deploy-docker.sh
# Заполнить /etc/crypto/.env (скрипт скажет)
sudo bash deploy-docker.sh  # повторно
```

Файлы:
- `Dockerfile` — multi-stage slim build, non-root user, healthcheck
- `docker-compose.yml` — 3 контейнера (BTC/ETH/XRP) с лимитами и изоляцией
- `.env.example` — шаблон конфига
- `deploy-docker.sh` — установщик

## Вариант B: systemd на чистом VPS (без Docker)

Используется когда на VPS только наш бот, без других сервисов.
См. `install.sh` и `crypto-runner@.service`.

```bash
ssh root@<your-vps-ip>
wget https://raw.githubusercontent.com/stupolus/Crypto/main/scripts/deploy/install.sh
sudo bash install.sh
```

См. полный план: `plans/16-деплой-24-7.md`.

## Backup перед деплоем

Если на VPS уже есть Odoo / другие сервисы:
```bash
# Бэкап Odoo volume
docker run --rm -v odoo_data:/data -v $(pwd):/backup alpine tar czf /backup/odoo-backup-$(date +%Y%m%d).tar.gz /data
```

## Стоп / откат

```bash
# Docker:
cd /opt/crypto-bot
docker compose -f scripts/deploy/docker-compose.yml down

# systemd:
sudo systemctl stop 'crypto-runner@*'
sudo systemctl disable 'crypto-runner@*'
```

## Безопасность

- `.env` `chmod 600`, владелец `root` (Docker монтирует read-only)
- Контейнеры non-root (`crypto` user, UID не 0)
- `cap_drop: ALL` — никаких Linux capabilities
- `read_only: true` — root FS только для чтения
- `no-new-privileges: true` — sudo внутри контейнера невозможен
- Отдельная Docker network — не видим Odoo и наоборот

## Faber-VST автономный таймер (план 42)

Демо-стратегия Faber (NASDAQ100-перп на BingX **VST**, НЕ live)
крутится сама на VPS через systemd-timer (как crypto-postmortem):

```bash
# на VPS, после git pull в /opt/crypto и install.sh:
sudo systemctl enable --now faber-vst.timer
systemctl list-timers | grep faber          # видно следующий запуск
journalctl -u faber-vst -n 20 --no-pager     # логи прогонов
# kill-switch (мгновенный стоп без остановки сервиса):
touch /opt/crypto/ops/faber_HALT
```

Ежедневно 21:00 UTC реконсилирует позицию по сигналу Faber,
идемпотентно (повтор безопасен), Persistent=true (нагонит
пропуск при простое VPS). `/etc/crypto/.env` — ТОЛЬКО
`BINGX_ENV=vst` + `BINGX_VST_*` (live-ключей нет; код
hard-guard). Артефакты: `ops/faber_vst.jsonl` (прогоны/ошибки),
`ops/faber_vst_state.json` (период-стейт брейкеров).

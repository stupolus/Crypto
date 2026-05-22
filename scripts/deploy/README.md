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

## GTAA-4 портфель (план 47, заменяет Faber-single)

После решения владельца 2026-05-19: **GTAA-4 заменяет Faber-single
на demo** (Faber-single = частный случай GTAA-4, оба на одном
VST-аккаунте конфликтуют за NDX-позицию).

GTAA = 5 VST-перпов равными долями 1/5 эквити (план 45.2 + серебро
2026-05-22): NCSISP500 (S&P 500), NCSINASDAQ100 (NASDAQ), NCCOGOLD
(золото), NCCO1OILWTI (нефть), NCCOXAG (серебро). Faber 200SMA-сигнал
per Yahoo-индекс, месячный ребаланс на EOM, B-tier 1% риск-сайз + ≤3x
плечо. Серебро — execution-only до отдельного бэктеста edge (план 47).

**Миграция на VPS** (после git pull main):
```bash
# на VPS — копировать-вставить целиком:
set -e
cd /opt/crypto && sudo -u crypto git pull origin main
sudo bash scripts/deploy/install.sh                  # ставит gtaa-vst.* + report
sudo systemctl disable --now faber-vst.timer         # стопаем Faber-single
sudo systemctl enable  --now gtaa-vst.timer          # GTAA-4 исполнитель
sudo systemctl enable  --now gtaa-vst-report.timer   # ежедневный отчёт
```

Проверка:
```bash
systemctl list-timers | grep -E 'faber|gtaa'     # gtaa в очереди, faber inactive
systemctl is-enabled gtaa-vst.timer              # должно быть: enabled
journalctl -u gtaa-vst -n 30 --no-pager
sudo -u crypto tail -n 8 /opt/crypto/ops/gtaa_vst.jsonl
# Прогнать отчёт вручную прямо сейчас (не дожидаясь таймера):
sudo systemctl start gtaa-vst-report.service && journalctl -u gtaa-vst-report -n 20 --no-pager
```

**Preflight (read-only, рекомендуется сразу после установки).** Печатает
по 5 активам EOM-дату, close, SMA200, сигнал + связь с BingX VST. Не
ставит ордера, не пишет стейт. Для ручной сверки SMA200 с Yahoo
(DEMO_CRITERIA 2/3):
```bash
sudo -u crypto /opt/crypto/.venv/bin/python -m scripts.gtaa_vst_executor --check
# ИТОГ: ГОТОВ К ЗАПУСКУ  → данные и связь в порядке
```

Daily-trigger 21:30 UTC (отчёт 21:45) + state-tracking
`last_rebalance_eom` → ровно один ребаланс/месяц (на следующем
триггере после новой EOM-даты по Yahoo). Идемпотентно: повтор в
том же месяце = `noop`.

**Переживание ребута VPS.** `enable` прописывает таймер в
`timers.target` (автозапуск при загрузке). `Persistent=true` →
если VPS был выключен в момент триггера, прогон выполнится сразу
после включения. Дополнительных действий не нужно — проверить:
`systemctl is-enabled gtaa-vst.timer` = `enabled`.

Kill-switch (отдельный от Faber):
```bash
touch /opt/crypto/ops/gtaa_HALT          # мгновенный стоп ордеров
rm    /opt/crypto/ops/gtaa_HALT          # снять предохранитель
```

### Telegram-уведомления (опционально, рекомендуется)

Без ключей бот пишет в journald (StdoutAlerter) и НЕ падает.
С ключами — шлёт ребаланс/ошибки + ежедневный отчёт в чат.
Настройка (см. `docs/telegram-setup.md`):
1. `@BotFather` → `/newbot` → токен.
2. Написать боту любое сообщение, затем
   `https://api.telegram.org/bot<TOKEN>/getUpdates` → `chat.id`.
3. В `/etc/crypto/.env` добавить:
   `TELEGRAM_BOT_TOKEN=...` и `TELEGRAM_CHAT_ID=...`.
4. `sudo systemctl start gtaa-vst-report.service` — придёт отчёт.

### Рунбук: типичные ошибки и фиксы

| Симптом | Причина | Фикс |
|---|---|---|
| `STOP: BINGX_ENV=...` в логе | в `.env` не `vst` | поправить `BINGX_ENV=vst`, рестарт не нужен (oneshot) |
| `skip: нет цены перпа` | BingX klines недоступны | транзиентно (ретраи 2/4/8s исчерпаны); сработает на след. триггере |
| `skip: yahoo ... недоступен` | Yahoo лаг/блок | то же; идемпотентно догонит |
| `noop` каждый день | уже ребалансировано в этом месяце | норма — ребаланс раз/мес |
| `status:"error"` + `position side` | hedge-режим не включён | проверить #164-фикс развёрнут (`git log`), позиции в hedge |
| `ABORT: ... read_error` + `100410` | BingX rate-limit на `/user/positions` (слишком частые вызовы) | ребаланс прерван чисто, **state не тронут** → автоматически повторится на след. триггере. Не дёргать `--check/--dry` подряд много раз; раз/день не воспроизводится |
| `ABORT: get_balance ...` | BingX недоступен на старте | то же — state не тронут, ретрай след. триггер |
| отчёт `НЕТ СРАБАТЫВАНИЙ` | таймер не сработал/выключен | `systemctl status gtaa-vst.timer`; `enable --now` |
| отчёт `позиции не получены` | BingX API недоступен при отчёте | проверить ключи/сеть; на исполнение не влияет |

Артефакты: `ops/gtaa_vst.jsonl` (heartbeat `fired` + решения +
ошибки), `ops/gtaa_vst_state.json` (`last_rebalance_eom` +
период-стейт брейкеров). Критерии приёмки и шаблон вердикта —
`plans/47-gtaa-vst-executor.md` → DEMO_CRITERIA.

**Вердикт по итогу периода (≥4 недели).** Считает факты исполнения
из логов (дни-срабатывания, ошибки, пойман ли ребаланс) — не из
головы:
```bash
sudo -u crypto /opt/crypto/.venv/bin/python -m scripts.gtaa_vst_verdict \
  | sudo -u crypto tee /opt/crypto/retro/$(date +%F)-gtaa-demo-вердикт.md
```
Вывод: `ИСПОЛНЕНИЕ: НАДЁЖНО` (все дни сработали, ноль ошибок, ≥1
ребаланс пойман) или `НЕ ПОДТВЕРЖДЕНО` с причинами. PnL намеренно
не оценивается (1 ребаланс статистически недоказателен).

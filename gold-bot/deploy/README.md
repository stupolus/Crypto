# Деплой paper-runner gold-bot

План: `plans/07-deploy-2026-05-22.md`. Этот документ — операционная
инструкция, не источник истины по решениям.

## Что разворачиваем

Paper-runner. **Никаких реальных ордеров.** Image не имеет инфраструктуры
для live (CLAUDE.md §6, plan 06 §«Ключевые инварианты»).

## Что нужно на VPS

- Linux (Debian/Ubuntu).
- `docker` + `docker compose` (или systemd, как резерв — см. ниже).
- `timedatectl set-ntp true` — обязательно, иначе свечи кажутся
  закрытыми раньше времени (plan 07 §«10 причин» пункт 2).
- Каталог `/var/lib/gold-bot/` с uid:gid 1000:1000.

## Деплой через Docker (предпочтительно)

```bash
# Один раз: подготовка хоста
sudo mkdir -p /var/lib/gold-bot && sudo chown 1000:1000 /var/lib/gold-bot

# Клон репо и переключение
git clone https://github.com/stupolus/Crypto /opt/gold-bot
cd /opt/gold-bot && git checkout gold

# Telegram (опционально): cp .env.example → .env, заполнить
cp gold-bot/deploy/.env.example gold-bot/deploy/.env

# Сборка и запуск
cd gold-bot
docker compose -f deploy/docker-compose.yaml up -d --build

# Наблюдение
docker compose -f deploy/docker-compose.yaml logs -f
```

Перезапуск контейнера не теряет историю: SQLite на хост-volume,
`runner_state.open_position` восстанавливается на старте (plan 06 §6).

## Ежедневный отчёт

Cron на хосте (предпочтительно):

```
5 0 * * * docker exec gold-bot-paper python -m scripts.daily_report
```

Или systemd timer (см. ниже).

## Резервный путь: systemd без Docker

Если по какой-то причине Docker недоступен:

```bash
# Подготовка пользователя
sudo useradd --create-home --uid 1000 --shell /usr/sbin/nologin goldbot
sudo mkdir -p /var/lib/gold-bot && sudo chown goldbot:goldbot /var/lib/gold-bot
sudo mkdir -p /etc/gold-bot && sudo touch /etc/gold-bot/paper.env && sudo chmod 600 /etc/gold-bot/paper.env

# Клон + venv (gold-bot/)
sudo -u goldbot git clone https://github.com/stupolus/Crypto /opt/gold-bot
sudo -u goldbot bash -c 'cd /opt/gold-bot && git checkout gold'
sudo -u goldbot python3.12 -m venv /opt/gold-bot/.venv
sudo -u goldbot /opt/gold-bot/.venv/bin/pip install \
    "pydantic>=2.10,<3" "pyarrow>=16" "pyyaml>=6.0,<7" "ccxt>=4.4,<5"

# Установить юниты
sudo cp /opt/gold-bot/gold-bot/deploy/systemd/gold-bot-paper.service /etc/systemd/system/
sudo cp /opt/gold-bot/gold-bot/deploy/systemd/gold-bot-daily-report.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now gold-bot-paper
sudo systemctl enable --now gold-bot-daily-report.timer
sudo journalctl -u gold-bot-paper -f
```

## Остановка

```
docker compose -f deploy/docker-compose.yaml down       # docker
sudo systemctl stop gold-bot-paper                       # systemd
```

Журнал в `/var/lib/gold-bot/paper.sqlite` остаётся, при повторном
запуске продолжается с того же состояния.

## Диагностика

- Heartbeat в SQLite: `SELECT value FROM runner_state WHERE key='heartbeat_ts'`
  — миллисекунды UNIX. Если разница с `now` > 5 минут — runner мёртв.
- Свежие сделки: `SELECT * FROM trades ORDER BY exit_ts DESC LIMIT 10`.
- Эквити: `SELECT value FROM runner_state WHERE key='equity'`.
- Открытая позиция: `SELECT value FROM runner_state WHERE key LIKE 'open_position:%'`.

## Что **нельзя** делать без отдельного «да»

- Включать live-режим — его в этом образе нет, и его не появится без
  отдельного плана 09 и письменного разрешения.
- Менять `risk.yaml` / `paper.yaml` на живом контейнере без коммита и
  ретроспективного бэктеста — CLAUDE.md §10.
- Импортировать в paper какой-либо код из корня репозитория — gold-bot
  изолирован (CLAUDE.md §1.1).

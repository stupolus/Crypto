# Деплой demo бота «трейдер» на VPS

> Запускать НЕ из облачной сессии Claude (там исходящий SSH заблокирован),
> а с машины с доступом к VPS. Только BingX **VST (demo)**.

## 0. Предусловия

- VPS с Python 3.12+, git, доступ по SSH.
- Ключи (значения — из твоих сессий, в git НЕ коммитятся):
  `COINGLASS_API_KEY`, `BINGX_VST_API_KEY`, `BINGX_VST_API_SECRET`,
  опц. `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.

## 1. Зайти на VPS и проверить состояние

```bash
ssh root@<VPS_IP>
date -u                      # ВАЖНО: время должно быть верным (TLS!)
timedatectl                  # если время уехало → синхронизировать (см. §1a)
python3.12 --version
ls ~/Crypto 2>/dev/null && echo "репо есть" || echo "репо нет"
# не конфликтует ли с основным ботом:
pgrep -af 'live_runner|llm_runner|trader' || echo "других раннеров нет"
```

### 1a. Если время уехало (была ошибка TLS «certificate is not yet valid»)

```bash
apt-get update && apt-get install -y systemd-timesyncd
timedatectl set-ntp true
timedatectl   # дождаться "System clock synchronized: yes"
```

## 2. Получить код (ветка демо)

```bash
cd ~
# первый раз:
git clone <repo-url> Crypto || true
cd ~/Crypto
git fetch origin claude/create-trader-folder-z30oG
git checkout claude/create-trader-folder-z30oG
git pull origin claude/create-trader-folder-z30oG
```

## 3. venv + зависимости + тесты

```bash
cd ~/Crypto
python3.12 -m venv .venv
. .venv/bin/activate
pip install -U pip
pip install -e ".[dev]"
pytest -q core/signals/ parsers/coinglass/ strategies/liquidation_reversal/ runners/tests/
```

## 4. .env (секреты — ввести значения вручную, файл в .gitignore)

```bash
cat > ~/Crypto/.env <<'ENV'
COINGLASS_API_KEY=<твой_coinglass_key>
BINGX_ENV=vst
BINGX_VST_API_KEY=<твой_vst_key>
BINGX_VST_API_SECRET=<твой_vst_secret>
TELEGRAM_BOT_TOKEN=<опц>
TELEGRAM_CHAT_ID=<опц>
ENV
chmod 600 ~/Crypto/.env
```

Проверка авторизации:

```bash
. .venv/bin/activate
python -c "
import asyncio
from adapters.bingx.settings import BingXSettings
from adapters.bingx.private import PrivateAPI
from adapters.bingx.client import BingXClient
async def m():
    async with BingXClient(settings=BingXSettings()) as c:
        print(await PrivateAPI(c).get_balance())
asyncio.run(m())
"
```

## 5. Запуск demo (сначала dry-run!)

`start_demo.sh` по умолчанию с `--dry-run` (ордера НЕ отправляются,
только лог и журнал). Запуск под `tmux` (живёт после выхода из SSH):

```bash
tmux new -s trader
cd ~/Crypto && bash трейдер/раннеры/start_demo.sh
# отсоединиться: Ctrl-b затем d ; вернуться: tmux attach -t trader
```

Либо systemd-юнит (надёжнее для 24/7) — см. §6.

## 6. systemd (24/7, авто-рестарт)

```bash
cat > /etc/systemd/system/trader-demo.service <<'UNIT'
[Unit]
Description=Trader demo (liquidation_reversal, BingX VST)
After=network-online.target

[Service]
WorkingDirectory=/root/Crypto
ExecStart=/usr/bin/env bash /root/Crypto/трейдер/раннеры/start_demo.sh
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now trader-demo
journalctl -u trader-demo -f      # смотреть логи
```

## 7. Проверка работы

```bash
# журнал/heartbeat появились:
ls -la ~/Crypto/трейдер/журнал/
# дневной отчёт (когда накопятся сделки):
. .venv/bin/activate
python -m scripts.daily_summary --journal трейдер/журнал/journal.sqlite
```

В логе должно быть: `Coinglass live providers wired (BTC-USDT @ 6h)`,
`BingX WS subscribed channel=BTC-USDT@kline_6h`.

## 8. Переход с dry-run на реальные demo-ордера

Только после нескольких суток dry-run и проверки журнала: убрать флаг
`--dry-run` в `трейдер/раннеры/start_demo.sh`, затем
`systemctl restart trader-demo`. Это всё ещё **VST (demo)**, не live.

Live (реальные деньги) — отдельно, только после ≥4 недель demo +
явного «да» (CLAUDE.md).

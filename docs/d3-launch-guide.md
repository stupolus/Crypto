# D3 Launch Guide — Demo на VST (BTC + ETH iter#1)

**Цель:** 4 недели на VST с iter#1 одновременно на BTC и ETH. **Не для прибыли, а для проверки гипотезы**: walk-forward показал PF 1.42 / 1.60 на out-of-sample, посмотрим что покажет live.

---

## Пред-проверки

```bash
# 1. .env содержит VST-ключи
cat .env | grep BINGX_
# BINGX_ENV=vst
# BINGX_VST_API_KEY=...
# BINGX_VST_API_SECRET=...

# 2. Запустить healthcheck для каждого символа
./venv/bin/python -m scripts.healthcheck --symbol BTC-USDT
./venv/bin/python -m scripts.healthcheck --symbol ETH-USDT

# Должно быть «✅ All checks passed» для обоих
# Если есть открытые позиции — закрыть руками:
./venv/bin/python -c "
import asyncio
from adapters.bingx.client import BingXClient
from adapters.bingx.settings import BingXSettings
from adapters.bingx.private import PrivateAPI

async def main():
    async with BingXClient(settings=BingXSettings()) as c:
        api = PrivateAPI(c)
        await api.close_position('BTC-USDT')
        await api.close_position('ETH-USDT')
        await api.cancel_all('BTC-USDT')
        await api.cancel_all('ETH-USDT')
        print('cleaned')

asyncio.run(main())
"

# 3. Убедиться что аккаунт настроен правильно
./venv/bin/python -c "
import asyncio
from adapters.bingx.client import BingXClient
from adapters.bingx.settings import BingXSettings
from adapters.bingx.private import PrivateAPI

async def main():
    async with BingXClient(settings=BingXSettings()) as c:
        api = PrivateAPI(c)
        await api.set_margin_mode('BTC-USDT', 'ISOLATED')
        await api.set_leverage('BTC-USDT', 3)
        await api.set_margin_mode('ETH-USDT', 'ISOLATED')
        await api.set_leverage('ETH-USDT', 3)
        await api.set_position_mode(one_way=True)
        print('configured')

asyncio.run(main())
"
```

---

## Запуск (две сессии параллельно)

**Терминал 1 — BTC:**
```bash
./venv/bin/python -m runners.live_runner \
    --strategy btc_breakout \
    --symbol BTC-USDT \
    --interval 15m \
    --warmup-candles 300 \
    --journal-db ops/d3-btc-orders.sqlite \
    --metrics-file ops/d3-btc-metrics.jsonl \
    2>&1 | tee ops/d3-btc.log
```

**Терминал 2 — ETH:**
```bash
./venv/bin/python -m runners.live_runner \
    --strategy btc_breakout \
    --symbol ETH-USDT \
    --interval 15m \
    --warmup-candles 300 \
    --journal-db ops/d3-eth-orders.sqlite \
    --metrics-file ops/d3-eth-metrics.jsonl \
    2>&1 | tee ops/d3-eth.log
```

**На VPS:** для запуска в фоне (24/7) — `tmux` или `systemd`. Если падает — runner автоматически реконнектит WS, но если процесс упал — `systemd` рестартанёт.

---

## Мониторинг

**Что смотреть каждый день:**

```bash
# Количество сделок за сутки
sqlite3 ops/d3-btc-orders.sqlite \
    "SELECT COUNT(*) FROM orders WHERE created_at_ms > strftime('%s', 'now', '-1 day') * 1000;"
sqlite3 ops/d3-eth-orders.sqlite \
    "SELECT COUNT(*) FROM orders WHERE created_at_ms > strftime('%s', 'now', '-1 day') * 1000;"

# Статусы ордеров
sqlite3 ops/d3-btc-orders.sqlite "SELECT status, COUNT(*) FROM orders GROUP BY status;"

# Latency / slippage
jq -s '[.[].latency_ms] | add/length' ops/d3-btc-metrics.jsonl
```

**Раз в неделю — записать в `журнал/`:** P&L неделя, отклонения, заметки.

---

## Критерии успеха (через 4 недели)

| Метрика | Цель | Что значит провал |
|---|---|---|
| Trades суммарно | ≥ 15 на BTC + 15 на ETH | Стратегия не открывает сделки (фильтры слишком жёсткие) |
| PF в обоих | ≥ 1.3 | Edge не подтверждается на live |
| Max DD | < 15% | Размер позиции слишком большой / SL слишком далеко |
| Adapter crashes | 0 | Инфра не готова к live |
| Slippage avg | < 50 bps | Live существенно хуже бэктеста |

**Если пройдены все** — обсудить переход на live с малым deposit ($100-500 для начала).
**Если хоть один провален** — retro в `retro/<дата>-d3.md` с разбором.

---

## Аварийный стоп

`Ctrl-C` в каждом терминале. Runner закроет listenKey + WS корректно через SIGINT.

**Если runner упал во время позиции** — см. `docs/runbook.md` §3 (восстановление через REST).

---

## Что мы НЕ ожидаем от D3

- ❌ **Прибыль.** На 4 недели и ~20 trades — слишком мало для статистически значимой прибыли. Это **гипотеза-тест**, не доход.
- ❌ **Подтверждения для деплоя $10K на live.** Минимум deposit для live — $100-500, после прохождения D3.
- ❌ **Идеального совпадения с бэктестом.** Live даёт +slippage / -latency / -fees. Допустимое отклонение ±20-30% от теории.

## Что мы ожидаем

- ✅ **Адаптер работает 4 недели без падений.** Это сам по себе результат.
- ✅ **Накопленные `live-metrics.jsonl`** — реальные latency / slippage цифры для будущих стратегий.
- ✅ **Решение go/no-go на live** на основе данных, не догадок.

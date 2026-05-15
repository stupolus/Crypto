# Runbook — практические рецепты

Документ «когда что делать»: типичные ситуации с готовыми командами.

---

## 1. Запуск стратегии на VST (demo)

```bash
# 1. Убедиться что .env содержит VST-ключи и BINGX_ENV=vst
cat .env | grep BINGX_

# 2. Опционально: скачать свежие свечи для warmup
./venv/bin/python -m scripts.download_klines --symbol BTC-USDT --interval 15m --months 1

# 3. Сначала dry-run (не отправляет ордера, только логирует сигналы)
./venv/bin/python -m runners.live_runner \
    --strategy btc_breakout --symbol BTC-USDT --interval 15m --dry-run

# 4. Если dry-run корректный — запустить с реальными ордерами на VST
./venv/bin/python -m runners.live_runner \
    --strategy btc_breakout --symbol BTC-USDT --interval 15m

# 5. Мониторить journal + metrics
sqlite3 ops/live-orders.sqlite "SELECT * FROM orders ORDER BY created_at_ms DESC LIMIT 10;"
tail -f ops/live-metrics.jsonl
```

**Где остановить:** Ctrl-C (SIGINT) — runner закроет listenKey + соединения корректно.

---

## 2. Запуск бэктеста

```bash
# Скачать данные
./venv/bin/python -m scripts.download_klines --symbol BTC-USDT --interval 15m --months 6

# Прогнать одну стратегию
./venv/bin/python -m scripts.run_backtest \
    --candles data/candles/btc-usdt-15m.jsonl \
    --strategy btc_breakout

# С out-of-sample split
./venv/bin/python -m scripts.run_backtest \
    --candles data/candles/btc-usdt-15m.jsonl \
    --strategy btc_breakout \
    --split-fraction 0.5

# Батч на нескольких символах
./venv/bin/python -m scripts.run_batch_backtest \
    --strategy btc_breakout \
    --symbols BTC-USDT,ETH-USDT,SOL-USDT \
    --interval 15m --split-fraction 0.5
```

---

## 3. Если runner упал во время открытой позиции

**Не перезапускать сразу!** Сначала проверить состояние:

```bash
# Проверить через REST: есть ли открытые позиции
./venv/bin/python -c "
import asyncio
from adapters.bingx.client import BingXClient
from adapters.bingx.settings import BingXSettings
from adapters.bingx.private import PrivateAPI

async def main():
    async with BingXClient(settings=BingXSettings()) as c:
        api = PrivateAPI(c)
        positions = await api.get_positions()
        for p in positions:
            if p.position_amount != 0:
                print(f'OPEN: {p.symbol} {p.position_amount} side={p.position_side}')
        if all(p.position_amount == 0 for p in positions):
            print('No open positions')

asyncio.run(main())
"

# Проверить journal: какие ордера остались pending
sqlite3 ops/live-orders.sqlite \
    "SELECT client_order_id, symbol, status, created_at_ms FROM orders WHERE status IN ('pending', 'acked') ORDER BY created_at_ms DESC;"
```

**Если есть открытая позиция и нет attached SL** (квирк §7 п.36 — SL хранится как атрибут entry-ордера, не отдельный) — закрыть руками:

```bash
./venv/bin/python -c "
import asyncio
from adapters.bingx.client import BingXClient
from adapters.bingx.settings import BingXSettings
from adapters.bingx.private import PrivateAPI

async def main():
    async with BingXClient(settings=BingXSettings()) as c:
        await PrivateAPI(c).close_position('BTC-USDT')
        print('closed')

asyncio.run(main())
"
```

После — можно перезапустить runner.

---

## 4. Если signed-запрос упал с `code=100001` (Signature mismatch)

Возможные причины (по убыванию вероятности):

1. **Ключи перепутаны (API_KEY ↔ API_SECRET).** Проверить в `.env`.
2. **Параметры не в alpha-sorted порядке.** Квирк §7 п.31. Уже зафикшено в `_do_signed`, но если новый код — проверить.
3. **`recvWindow` отправлен.** Квирк §7 п.30. Не отправлять.
4. **`stopPrice` строкой вместо числа.** Квирк §7 п.32. Использовать `float(decimal)`.
5. **`positionSide` ≠ `BOTH` в one-way mode.** Квирк §7 п.33.

Логи signed-запросов: `LOG_LEVEL=DEBUG` → `bingx GET ...` строки с masked URL.

---

## 5. Если стратегия не открывает позиции в backtest

Проверить:

1. **Warmup history достаточен?** Стратегии требуют `donchian_n`/`atr_window`/`lookback` свечей до первого сигнала. Если data < min_history — стратегия молчит.
2. **Composite filters блокируют?** Логи на уровне INFO покажут «signal rejected by RiskEngine».
3. **RiskEngine reject?** Возможные причины: `STOP_TOO_TIGHT`, `LEVERAGE_OVER_CAP`, `DAILY_LOSS_LIMIT`. Проверить `RiskInputs` (особенно `equity`).
4. **Параметры слишком жёсткие?** Например `atr_percentile_min=0.5` режет половину candidates. Расслабить можно — но **не подгонять под результат** (см. AGENTS.md).

---

## 6. Тесты

```bash
# Unit-only (быстро, ~5s)
./venv/bin/pytest -q

# Integration на live BingX VST (медленно, минуты)
./venv/bin/pytest -m integration

# Конкретный тест
./venv/bin/pytest adapters/bingx/tests/test_int_orders.py -v

# С coverage
./venv/bin/pytest --cov=adapters/bingx --cov-report=term-missing
```

---

## 7. Линт / mypy / formatting

```bash
# Проверка
./venv/bin/ruff check adapters core strategies scripts runners
./venv/bin/mypy adapters core strategies scripts runners

# Авто-фикс ruff (только безопасные)
./venv/bin/ruff check --fix adapters core strategies

# Форматирование
./venv/bin/ruff format adapters core strategies
```

**Перед коммитом** — оба должны быть зелёные (это требование CLAUDE.md правил авто-мержа).

---

## 8. Когда менять параметры в `бизнес/риск-профиль.md`

Только если:
- Появилось обоснование из реальной торговли (не из бэктеста).
- Согласовано пользователем.

**Запрещено:** менять числа потому что «бэктест показал лучше при X». Это overfit (см. AGENTS.md).

---

## 9. Когда мержить PR в `main`

См. `CLAUDE.md` §«Авто-мерж своих PR в `main`». Все условия (unit + integration + ruff + mypy + не трогает CLAUDE.md/.env/секреты) должны быть выполнены **одновременно**.

Если что-то красное — фиксить, не мержить.

---

## 10. Если BingX API изменился

1. Запустить integration-тесты: `pytest -m integration` — упадут с новым `code=...` или `text=...`.
2. Зафиксировать новый квирк в `plans/01-bingx-адаптер.md` §7.
3. Поправить адаптер. Юнит-тест на новое поведение.
4. PR с **acknowledgement** что это breaking change BingX-side, не наш bug.

---

## 11. Где смотреть метрики live-сессии

```bash
# Все ордера за сессию
sqlite3 ops/live-orders.sqlite "SELECT * FROM orders;"

# Latency / slippage статистика
jq -s '[.[].latency_ms] | add/length' ops/live-metrics.jsonl  # avg latency
jq -s '[.[].slippage_bps | tonumber] | add/length' ops/live-metrics.jsonl  # avg slippage

# Журнал по символу
sqlite3 ops/live-orders.sqlite \
    "SELECT status, COUNT(*) FROM orders WHERE symbol='BTC-USDT' GROUP BY status;"
```

---

## 12. Если есть сомнения

`AskUserQuestion` в Claude-сессии для уточнения. Особенно для:
- Изменения параметров риск-профиля.
- Перехода с VST на live.
- Мержа PR с большими архитектурными изменениями.

Не действовать без подтверждения.

# Crypto — алгоритмическая торговая платформа

[![CI](https://github.com/stupolus/Crypto/actions/workflows/ci.yml/badge.svg)](https://github.com/stupolus/Crypto/actions/workflows/ci.yml)

**Стартовые точки:**
- Для агентов / Claude: [`CLAUDE.md`](./CLAUDE.md), [`AGENTS.md`](./AGENTS.md)
- Архитектура и принципы: [`docs/architecture.md`](./docs/architecture.md)
- Мастер-план: [`plans/00-стратегия-проекта-2026-05-09.md`](./plans/00-стратегия-проекта-2026-05-09.md)
- Бизнес-знания / риск-профиль: [`бизнес/INDEX.md`](./бизнес/INDEX.md)

## Статус (2026-05-11)

✅ **Адаптер BingX готов.** Полная фаза 0 (A→E):
- HTTP + WS, signed requests с маскированием.
- `place_order` с attached SL/TP, kill switch, compensating-close.
- User Data Stream (push events) + reconcile + periodic soft-reconcile.
- SQLite `OrderJournal` + JSON-lines `MetricsWriter`.
- 173 unit-тестов, integration на live VST зелёные.

✅ **Backtest pipeline готов.** RiskEngine + BacktestEngine + 3 стратегии в коде.

✅ **Live runner готов.** `python -m runners.live_runner --dry-run` запускает любую стратегию на VST.

❌ **Простые rule-based стратегии edge не дают.** 4 итерации (Donchian 15m, Donchian 1h, US session, EMA trend 4h) на 3 символах × OOS — все опровергнуты. Подробности в [`plans/02-btc-breakout-backtest.md`](./plans/02-btc-breakout-backtest.md) и [`retro/2026-05-11-сессия-итог.md`](./retro/2026-05-11-сессия-итог.md).

⚠️ **Реабилитация iter#1 на BTC:** PF 1.72 (IS) / 1.74 (OOS) на 30 trades. Возможный candidate для D3 (demo на VST как проверка гипотезы).

## Quick start

```bash
# Setup
python3.13 -m venv venv
./venv/bin/pip install -e ".[dev]"
./venv/bin/pytest -q  # 173 unit зелёных

# Скачать свечи
./venv/bin/python -m scripts.download_klines --symbol BTC-USDT --interval 15m --months 6

# Бэктест одной стратегии
./venv/bin/python -m scripts.run_backtest \
    --candles data/candles/btc-usdt-15m.jsonl \
    --strategy btc_breakout

# Батч на нескольких символах с IS+OOS
./venv/bin/python -m scripts.run_batch_backtest \
    --strategy btc_breakout \
    --symbols BTC-USDT,ETH-USDT,SOL-USDT \
    --interval 15m --split-fraction 0.5

# Запустить стратегию на VST (dry-run = без отправки ордеров)
./venv/bin/python -m runners.live_runner \
    --strategy btc_breakout --symbol BTC-USDT --interval 15m --dry-run
```

## Принципы

1. **Никакого кода до плана.** Любая фича начинается с `plans/<номер>-<имя>.md`.
2. **Чужие сигналы — данные, не входы.** TG-скринеры, новости проверяются как фильтры с накопленной статистикой.
3. **Размер позиции от риска, не от плеча.** Через `core/risk/`.
4. **Каждое решение — в файлы.** Retro после каждой важной сессии.
5. **Никогда плечо > 5x.** Жёстко в `RiskEngine`.

## Структура

```
adapters/bingx/          # BingX HTTP+WS адаптер, journal, metrics
core/
├── risk/                # RiskEngine: размер + circuit breakers
├── signals/             # ATR, EMA, Donchian, composite (funding/news/blacklist), session
└── backtest/            # event-driven backtester + IS/OOS split
strategies/
├── btc_breakout/        # Donchian + ATR + volume
├── us_session_breakout/ # Asian range → US window pivot
└── trend_ema_4h/        # EMA(20)/EMA(50) + pullback
runners/
└── live_runner.py       # orchestrator адаптер + стратегия + journal
scripts/
├── download_klines.py
├── download_funding.py
├── run_backtest.py
└── run_batch_backtest.py
plans/                   # планы фич (08-15: стратегии и анализ)
retro/                   # ретроспективы сессий
docs/                    # архитектура, runbook
бизнес/                  # второй мозг: риск-профиль, цели, материалы
data/                    # собираемые данные (gitignored)
ops/                     # journal SQLite, metrics JSONL (gitignored)
```

## Документация

- [`docs/architecture.md`](./docs/architecture.md) — общая схема слоёв и принципы.
- [`docs/runbook.md`](./docs/runbook.md) — практические рецепты (как запустить, мониторить, отлаживать).
- [`plans/01-bingx-адаптер.md`](./plans/01-bingx-адаптер.md) §7 — 37 живых квирков BingX.
- [`бизнес/риск-профиль.md`](./бизнес/риск-профиль.md) — единственный источник чисел.

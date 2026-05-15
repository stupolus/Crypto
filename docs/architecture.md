# Архитектура проекта

**Версия:** 2026-05-11 (после 16 PR за день).
**Связано:** [[CLAUDE.md]], [[AGENTS.md]], [[plans/00-стратегия-проекта-2026-05-09]].

---

## 1. Общая картина

```
┌───────────────────────────────────────────────────────────────────┐
│                          BingX REST + WS                          │
└──────────────────────────────┬────────────────────────────────────┘
                               │ HTTP + websockets
                               ▼
┌───────────────────────────────────────────────────────────────────┐
│                     adapters/bingx/  (Layer 1)                    │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────────────┐  │
│  │ BingXClient │  │ PublicAPI    │  │ PrivateAPI              │  │
│  │ - sign      │  │ - klines     │  │ - get_balance/positions │  │
│  │ - retry     │  │ - contracts  │  │ - place_order           │  │
│  │ - rate-lim  │  │ - ticker     │  │ - cancel_*              │  │
│  │ - masking   │  │              │  │ - close_position        │  │
│  └─────────────┘  └──────────────┘  └─────────────────────────┘  │
│                                                                    │
│  ┌────────────────────────────┐  ┌────────────────────────────┐   │
│  │ BingXMarketWebSocket       │  │ BingXUserDataStream        │   │
│  │ (klines, ticker)           │  │ (ORDER/ACCOUNT events)     │   │
│  │ - gzip, Ping/Pong          │  │ + listenKey lifecycle      │   │
│  │ - reconnect                │  │ + reconcile (on connect)   │   │
│  │                            │  │ + soft-reconcile (periodic)│   │
│  └────────────────────────────┘  └────────────────────────────┘   │
│                                                                    │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐    │
│  │ OrderJournal    │  │ MetricsWriter   │  │ Settings        │    │
│  │ (SQLite)        │  │ (JSON-lines)    │  │ (pydantic .env) │    │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘    │
└───────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌───────────────────────────────────────────────────────────────────┐
│                        core/  (Layer 2)                           │
│  ┌──────────────┐  ┌─────────────────┐  ┌────────────────────┐    │
│  │ risk/        │  │ signals/        │  │ backtest/          │    │
│  │ - RiskEngine │  │ - indicators    │  │ - BacktestEngine   │    │
│  │ - size +     │  │   (ATR, EMA,    │  │ - Strategy proto   │    │
│  │   circuit    │  │    Donchian)    │  │ - fill simulation  │    │
│  │   breakers   │  │ - composite     │  │ - IS/OOS split     │    │
│  │              │  │   (funding etc) │  │ - metrics          │    │
│  │              │  │ - session       │  │                    │    │
│  └──────────────┘  └─────────────────┘  └────────────────────┘    │
└───────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌───────────────────────────────────────────────────────────────────┐
│                       strategies/  (Layer 3)                      │
│  ┌──────────────────────┐  ┌──────────────────────┐               │
│  │ btc_breakout         │  │ us_session_breakout  │               │
│  │ Donchian + ATR +     │  │ Asian range pivot    │               │
│  │ volume               │  │ in US window         │               │
│  └──────────────────────┘  └──────────────────────┘               │
│  ┌──────────────────────┐                                         │
│  │ trend_ema_4h         │                                         │
│  │ EMA(20)/EMA(50) +    │                                         │
│  │ pullback entry       │                                         │
│  └──────────────────────┘                                         │
│                                                                   │
│  Все реализуют ``core.backtest.Strategy`` protocol.               │
│  Используют RiskEngine для размера + signals для индикаторов.     │
└───────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌───────────────────────────────────────────────────────────────────┐
│                       scripts/  (Layer 4 — tools)                 │
│  ┌──────────────────┐  ┌──────────────────┐  ┌────────────────┐   │
│  │ download_klines  │  │ download_funding │  │ run_backtest   │   │
│  └──────────────────┘  └──────────────────┘  └────────────────┘   │
│  ┌────────────────────┐                                           │
│  │ run_batch_backtest │ — батч-прогон на нескольких символах      │
│  └────────────────────┘                                           │
└───────────────────────────────────────────────────────────────────┘
```

## 2. Принципы

### Decimal везде

Все денежные/количественные значения — `Decimal`, никогда `float`. Парсинг из BingX-ответов через `pydantic` с `extra="ignore"` (BingX добавляет поля без анонса).

### Stateless / DI

- `RiskEngine` — чистая функция: `evaluate(inputs) → Approval | Rejection`. Stateful-учёт (day P&L) на стороне стратегии или orchestrator.
- `BacktestEngine` — event-driven loop, без сетевых вызовов.
- Стратегия принимает provider'ы (`FundingProvider`, `NewsCalendar`, `Blacklist`) через конструктор — легко подменить в тестах.

### Numbers в `config.yaml`

Никаких magic-numbers в коде. Каждый порог / лимит — в YAML, валидируется pydantic, ссылка на источник (`бизнес/риск-профиль.md` или docs-v3).

### Безопасность

- API-ключи только в `.env` (gitignored).
- `BINGX_ENV=vst` default — никогда live без явного действия.
- `mask_signed_url` / `mask_headers` в логах.
- `OrderRequest` модель запрещает entry без `attached_stop_loss` на уровне валидатора → стратегия физически не может отправить голый entry.

### Event-driven backtest

Не vectorized — чтобы избежать lookahead bugs.
- Стратегия видит `history` включая `current_candle`. Не видит `c+1`.
- MARKET fill — по `open(c+1)`, не `close(c)`.
- Unit-тест `test_lookahead_independence_future_changes_do_not_affect_past` это проверяет.

## 3. Quick start (для новой Claude-сессии)

```bash
# Setup
.venv/bin/pip install -e .
.venv/bin/pytest -q  # 170 unit зелёных

# Бэктест существующей стратегии
.venv/bin/python -m scripts.download_klines --symbol BTC-USDT --interval 15m --months 6
.venv/bin/python -m scripts.run_backtest --candles data/candles/btc-usdt-15m.jsonl

# Батч на 3 символах с IS+OOS
.venv/bin/python -m scripts.run_batch_backtest \
    --strategy btc_breakout \
    --symbols BTC-USDT,ETH-USDT,SOL-USDT \
    --interval 15m --split-fraction 0.5

# Funding history (для D2)
.venv/bin/python -m scripts.download_funding --symbol BTC-USDT --limit 1000
```

## 4. История того что было пробовано

См. `plans/02-btc-breakout-backtest.md` — детальный разбор 4 итераций стратегий.
См. `retro/2026-05-11-сессия-итог.md` — общий разбор и стратегические варианты.

## 5. Где квирки BingX

`plans/01-bingx-адаптер.md` §7 — 37 живых квирков с обоснованиями (смесь docs+эмпирика на live VST).

## 6. Где правила трейдинга

`бизнес/риск-профиль.md` — единственный источник чисел (1% риск, 5x max leverage, 3 trades/day, и т.д.).
В коде ссылки на этот файл, числа не дублируются.

## 7. Roadmap (для будущего)

Технически готово к live. Что не сделано:

- Telegram-алерты (отложено — критерии: что алертить определяет live-стратегия).
- Standalone stop_market / stop_limit / tp_market ордера (нужны для flip-сценариев).
- Walk-forward backtest (rolling IS+OOS).
- Live runner / orchestrator (отдельный процесс, который соединяет адаптер + стратегию + journal).
- Расширение на других биржах (Bybit, Hyperliquid, ...).

## 8. Главное

**Инфраструктура работает.** Метод валидации (мульти-символ + OOS split + статистика) **поймал false-edge до live**. Это и есть успех проекта на этом этапе.

Любая будущая стратегия использует те же компоненты:
- RiskEngine для размера.
- BacktestEngine для проверки на истории.
- BingXClient + PrivateAPI + UserDataStream для live.
- OrderJournal + MetricsWriter для observability.

Стратегия — последний кусок пазла. Большая часть «риск management + bug-resistance + reproducibility» закрыта.

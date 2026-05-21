# 01 — ccxt-адаптер BingX + Bybit

Дата: 2026-05-20
Статус: адаптерный слой собран. Фазы 1A-1E + 1G готовы (модели, протокол, ошибки, нормализация, маскирование, market/account/trading адаптеры, smoke-скрипт, docs). 1F — scaffold (integration-тесты написаны, запуск вручную с ключами/сетью). Локально зелёно: ruff/format/mypy strict/pytest 63 (+3 integration deselected).

---

## Цель

Построить тонкий единый интерфейс к BingX и Bybit USDT-perp через ccxt, с поддержкой обязательного attached stop-loss на уровне `place_order`. Чтобы все вышестоящие модули (стратегии, paper-runner, live-runner) обращались к одному API независимо от биржи.

## Гипотеза edge'а

Edge'а нет — это инфраструктурный слой. Гипотеза проектная: ccxt достаточен для 80% функционала. Оставшиеся 20% (квирки BingX, attached SL/TP, normalize symbols) покрываем кастомным кодом.

## Что входит

### Market data
- `fetch_ohlcv(symbol, timeframe, since=None, limit=None)` — исторические свечи.
- `fetch_ticker(symbol)` — текущая цена + 24h объём + спред.
- `fetch_order_book(symbol, depth=20)` — стакан (для slippage эстимации).
- `fetch_funding_rate(symbol)` — текущий funding rate и время следующего расчёта.
- `fetch_markets()` — список доступных инструментов (важно для проверки «есть ли PAXG/XAUT/TSLA-USDT perp»).

WS-потоки (`watch_*`) в этот план НЕ входят — будут отдельным планом после бэктестера. Для бэктеста и paper-runner первых итераций polling REST — достаточно.

### Account
- `fetch_balance()` — USDT баланс на перп-аккаунте.
- `fetch_positions(symbols=None)` — открытые позиции, нормализованный формат (своя pydantic-модель).
- `set_leverage(symbol, leverage)` — установка биржевого плеча (биржевой ползунок, не эффективное).
- `set_margin_mode(symbol, mode='isolated')` — **всегда isolated**, cross запрещён валидатором.

### Trading
- `place_order(...)` с **обязательным attached stop-loss**. На уровне pydantic-модели `OrderRequest`: поле `stop_price` non-nullable. `place_order(stop_price=None)` — ошибка валидации до любого сетевого вызова.
- `cancel_order(order_id, symbol)`
- `cancel_all_orders(symbol)`
- `close_position(symbol)` — рыночное закрытие.
- `fetch_order(order_id, symbol)` — статус ордера.
- `fetch_open_orders(symbol=None)`

### Resilience
- Retry с exponential backoff (1s, 2s, 4s, 8s) на network/timeout/5xx ошибки. Не retry на 4xx (кроме 429).
- Rate-limit через ccxt `enableRateLimit=True` + собственный счётчик как backup.
- Маскирование секретов в логах: функция `mask_secrets(s)` заменяет ключи на `***` в любой строке.
- Структурные JSON-логи (stdlib logging; structlog не используем — см. историю 1B).

## Структура папки

```
gold-bot/exchanges/
├── __init__.py
├── base.py            # абстрактный протокол ExchangeAdapter
├── models.py          # pydantic: OrderRequest, Position, Balance, OHLCV, Ticker
├── errors.py          # нормализованные исключения
├── ccxt_base.py       # CcxtAdapter — общая реализация поверх ccxt
├── bingx.py           # подкласс через ccxt.bingx
├── bybit.py           # подкласс через ccxt.bybit
├── normalize.py       # нормализация символов → BTC/USDT:USDT
├── logging_utils.py   # mask_secrets, JsonFormatter, configure_logging
└── tests/
    ├── test_models.py
    ├── test_normalize.py
    ├── test_masking.py
    ├── test_ccxt_market.py
    ├── test_ccxt_account.py
    ├── test_ccxt_trading.py
    └── test_integration_bybit_testnet.py  # под флагом -m integration
```

## Данные / источники

- `ccxt` 4.x для обеих бирж (проверено на 4.5.54).
- Документация BingX (квирки фиксируем в `gold-bot/journal/bingx-quirks.md` по мере обнаружения).
- Документация Bybit v5 (unified).
- Testnet: Bybit — да (testnet.bybit.com), BingX — нет полноценного (есть VST, но ограниченный по инструментам).

## Метод проверки

- **Unit-тесты** с моками (без сети) для каждой публичной функции. Покрытие 100% публичных методов.
- **Инварианты**: `OrderRequest(stop_price=None)` → ValidationError до сетевого вызова. `set_margin_mode('cross')` → ошибка.
- **Маскирование**: тест проверяет что в логах после вызова с фейковыми ключами ключи заменены на `***`.
- **Нормализация**: тесты что `"BTC-USDT"`, `"BTCUSDT"`, `"BTC/USDT:USDT"` — все приводятся к одной канонической форме (выберем `BTC/USDT:USDT` по ccxt-конвенции).
- **Integration-тест** на Bybit testnet: полный цикл `fetch_balance` → `set_margin_mode(isolated)` → `place_order(BTC, market, qty, stop_price)` → `fetch_positions` → `close_position`. Запуск под флагом `pytest -m integration`, не в дефолтном ране.
- **Публичные markets**: integration-тесты fetch_markets для bybit/bingx без ключей (проверка связности и наличия инструментов).
- **Smoke-скрипт**: `python -m scripts.smoke_exchange --exchange bybit --symbol BTC/USDT:USDT` — печатает markets/ticker/balance. Ручная проверка перед следующим планом.

## 10 причин почему может не сработать

1. **ccxt не поддерживает attached SL/TP на BingX через универсальный интерфейс** — придётся отправлять стоп отдельным ордером, это нарушает атомарность. План б: «locking entry until stop подтверждён» — в код `place_order` встраиваем последовательность и роллбек (закрываем позицию рынком, если стоп не встал). [Статус: в 1E стоп уходит через stopLossPrice; verify+rollback — отдельно перед live, после testnet-проверки 1F.]
2. **Bybit testnet закрыт/сломан в момент интеграции.** План б: smoke в paper-mode внутренний, без сети.
3. **PAXG/XAUT перпов не существует ни на BingX, ни на Bybit** — выявится через `fetch_markets`. Реакция: фиксируем в journal, пересматриваем MVP-список (возможно XAU-perp вместо PAXG или спот).
4. **WS-потоки ccxt.pro требуют отдельной лицензии** — ок, в этот план WS не входит, пользуемся REST polling.
5. **Наименование символов разных бирж** отличается. ccxt поле `symbol` имеет разную форму. Решение: слой `normalize.py` с тестами.
6. **Rate-limit биржи ниже чем ожидали** на private endpoints (BingX особенно). Реакция: вложенный backoff + логирование лимита.
7. **BingX возвращает ошибки в HTTP 200** (`{"code": ..., "msg": ...}`) — ccxt часть ловит как Exception, часть нет. Решение: wrapper в `bingx.py` проверяет `code != 0` и сам бросает нормализованное исключение. [Отложено до первых live-вызовов — фиксируем в bingx-quirks.md.]
8. **isolated-режим нужно выставить один раз перед первым ордером**, иначе биржа возьмёт cross. Решение: set_margin_mode вызывает runner раз на символ при старте (не внутри place_order, чтобы не ловить «not modified»).
9. **Версия ccxt в PyPI отстаёт от свежего API** биржи на 2-4 недели. Решение: пиним версию в `pyproject.toml` (ccxt>=4.4,<5), фиксируем проверенную в `journal/bingx-quirks.md`.
10. **Нарушение правил на этапе кода**: кто-то (я в будущей сессии) попытается «взять из корневого крипто-проекта готовый BingX-адаптер и не писать заново». По CLAUDE.md §1.1 это запрещено. Страховка — явный пункт в этом плане.

## Критерии успеха

- 100% public-методы адаптера покрыты unit-тестами с моками. ✅
- `OrderRequest` физически отклоняет вход без стопа (тест проверяет). ✅
- Bybit testnet integration-тест зелёный при ручном запуске с ключами. — scaffold, ждёт ключей/сети (1F)
- `ruff` + `ruff format` + `mypy --strict` чисто. ✅
- Скрипт `scripts/smoke_exchange.py` работает и печатает markets/ticker/balance. — написан, ручной запуск с сетью
- `gold-bot/journal/bingx-quirks.md` создан. ✅

## Критерии неуспеха

- Bybit testnet integration не удаётся запустить ни в одном варианте → откат на paper-only, пересмотр роадмапа.
- attached SL/TP не реализуемые никак → запись в journal, план б «стоп сразу после входа + окно риска», повторное уточнение правил.

## Фазы реализации

| Фаза | Что | Статус |
|---|---|---|
| **1A** | `pyproject.toml` для gold-bot + base.py (Protocol) + models.py (pydantic) + errors.py + tests/test_models.py | ✅ готово (524bfbe) |
| **1B** | normalize.py + logging_utils.py + tests/test_normalize.py + tests/test_masking.py | ✅ готово (ee5956a) |
| **1C** | bingx.py и bybit.py: market data (fetch_ohlcv/ticker/order_book/funding/markets) + unit-тесты с моками | ✅ готово (348af9d) |
| **1D** | account endpoints (balance, positions, set_leverage, set_margin_mode) + unit-тесты | ✅ готово (31f816d) |
| **1E** | trading (place_order с обязательным стопом, cancel, close, fetch_order, fetch_open_orders) + unit-тесты | ✅ готово (31f816d) |
| **1F** | Bybit testnet integration-тест (под флагом) + публичные fetch_markets | 🟡 scaffold (37fe130) — запуск вручную с ключами/сетью |
| **1G** | `scripts/smoke_exchange.py` + README в `gold-bot/exchanges/` + `journal/bingx-quirks.md` | ✅ готово (37fe130) |

Каждая фаза = отдельный коммит на ветке `gold` или фиче-ветке от неё.

## Зависимости

- Plan 00 одобрен.
- Доступ к Bybit testnet (ключи на VPS в `.env`) — нужен только для фазы 1F. Фазы 1A-1E работают без ключей.

## Что отложено (явно)

- WebSocket-потоки (`watch_*`) — после плана 06 (paper-runner).
- User-data stream и обработка push-событий — после paper, перед live.
- verify+rollback стопа в place_order (риск #1) — перед live, после testnet-проверки что stopLossPrice реально принимается.
- Cross-exchange арбитраж-логика — отдельный план если и когда-то.

## История изменений

| Дата | Изменение |
|---|---|
| 2026-05-20 | Создан план. Нуждается в одобрении. |
| 2026-05-20 | Фаза 1A реализована: models.py, base.py, errors.py, __init__.py, tests/test_models.py, pyproject.toml. Локально зелёно (ruff, ruff format, mypy --strict, pytest 16/16). Коммит 524bfbe. |
| 2026-05-20 | Фаза 1B: normalize.py (to_canonical) + logging_utils.py (mask_secrets/JsonFormatter, stdlib вместо structlog) + тесты. pytest 37/37. Коммит ee5956a. |
| 2026-05-20 | Фаза 1C: ccxt_base.py (CcxtAdapter market-data) + bingx.py + bybit.py + async-тесты на моках. pytest 47/47. Коммит 348af9d. |
| 2026-05-20 | Фазы 1D+1E: account (balance/positions/leverage/margin-mode) + trading (place_order со стопом, cancel/close/fetch) + тесты. pytest 63/63. Коммит 31f816d. |
| 2026-05-20 | Фазы 1F+1G: integration-тесты (scaffold, -m integration), smoke_exchange.py, exchanges/README.md, journal/bingx-quirks.md. Коммит 37fe130. |

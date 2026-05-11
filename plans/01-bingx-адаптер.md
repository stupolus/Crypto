# План: BingX-адаптер (фаза 0)

**Дата:** 2026-05-09
**Статус:** актуальный — фазы 0.A/0.B/0.C закрыты, готов к фазе 0.D (trading + kill switch)
**Автор:** Claude + пользователь
**Связано:** [[plans/00-стратегия-проекта-2026-05-09]], [[бизнес/инструменты-bingx]], [[бизнес/риск-профиль]], [[бизнес/правила-торговли/мм-контр-стратегии]]
**Источник API-данных:** официальная документация BingX docs-v3, https://bingx-api.github.io/docs-v3/#/en/info (V2-портал `bingx-api.github.io/docs/` редиректит туда). Аудит проведён 2026-05-09; конкретные эндпоинты и квирки — в [[бизнес/инструменты-bingx]] с прямыми ссылками.

---

## 1. Контекст и цель

BingX — биржа №1 по [[plans/00-стратегия-проекта-2026-05-09]] §2: единственная площадка, где у пользователя уже есть опыт и где доступен весь целевой набор инструментов под одной крышей (крипта, металлы, индексы, токенизированные акции). Без работающего адаптера к BingX **ничего больше из фазы 0 не имеет смысла** — ни стратегия, ни бэктест, ни риск-движок не подключаются к рынку.

Цель плана: спроектировать **минимальный, надёжный, тестируемый** адаптер BingX для USDT-M perpetual futures, достаточный для:
- запуска фазы 1 (BTC breakout на одном инструменте);
- расширения в фазу 2 (золото) **без переписывания**, только конфигурацией символа;
- работы Risk Engine'а (`core/risk/`), Backtest Engine'а (`core/backtest/`) и стратегий (`strategies/`) поверх единого интерфейса.

**Что мы НЕ делаем в этом адаптере:**
- Не работаем со спотом и опционами (только perp).
- Не реализуем сложные ордер-типы (TWAP, iceberg, OCO в полной форме). Минимум: market, limit, stop-market, stop-limit, take-profit-market.
- Не торгуем — адаптер только предоставляет интерфейс. Решения принимает стратегия + риск-движок.
- Не делаем универсальный «multi-exchange abstraction». Сейчас один адаптер. Bybit (фаза 4+) подключим вторым реализатором того же интерфейса, если он окажется удобной формой; преждевременно не обобщаем.

---

## 2. Скоуп

### Что должен уметь адаптер (MUST)

**Market data (read-only, public API):**
- Получить список доступных торговых пар (perpetual) с их параметрами: tick size, lot size, min/max notional, max leverage, статус торгов.
- Получить исторические свечи (klines) по символу, таймфрейму (1m, 5m, 15m, 1h, 4h, 1d), диапазону. С пагинацией.
- Подписаться на стрим свечей (klines WS).
- Подписаться на стрим тикеров / последней цены (для проверки kill-switch и risk-breach в реальном времени).
- Получить funding rate (текущий + история) — нужен для фильтра в стратегии.
- Получить open interest (текущий + история) — нужен для composite signal.

**Account / positions (private API):**
- Получить баланс эквити (USDT) и доступную маржу.
- Получить открытые позиции (символ, сторона, размер, средняя цена, нереализованный PnL, стоп/TP если стоят на бирже).
- Получить открытые ордера (для синхронизации после рестарта бота).
- Получить историю исполнений (fills) — нужен для журнала и сверки PnL.
- Установить режим маржи: **isolated** (см. [[бизнес/риск-профиль]] — кросс-маржа запрещена).
- Установить плечевой множитель (биржевое плечо) — на старте фиксируем 5x, дальше из конфига.
- Установить режим позиций: **one-way** (не hedge mode — мы не держим обе стороны одновременно).

**Trading (private API):**
- Поставить рыночный ордер (entry).
- Поставить лимитный ордер (для входов и TP).
- Поставить стоп-маркет ордер (stop-loss).
- Поставить стоп-лимит и take-profit-market (для TP1/TP2 механики breakout-стратегии).
- Отменить конкретный ордер.
- Отменить все ордера по символу (используется в kill switch и при ошибках).
- Закрыть позицию **рыночным ордером** (kill switch / cooldown).
- Связать стоп и TP с позицией так, чтобы при закрытии позиции защитные ордера автоматически снимались (если BingX это поддерживает; иначе — мы делаем это сами в обработчике fill-события).

**Подписки реального времени (WebSocket):**
- User data stream: события позиций (open, modify, close, liquidation), события ордеров (created, partial fill, filled, cancelled, rejected), события баланса.
- Heartbeat / ping-pong.
- Авто-реконнект с восстановлением подписок.

### Что НЕ MUST на этой фазе (но дизайн не должен мешать в будущем добавить)

- Sub-account API.
- Conditional orders сверх стопа/TP.
- Расширенные ордер-типы (TWAP, iceberg).
- Margin/funding history pull (можно вытащить через REST разово, не в горячем пути).
- Spot trading (в обозримом будущем не нужен).

### Чего НЕ должно быть в адаптере

- ❌ Решений о размере позиции (это `core/risk/`).
- ❌ Решений о входе/выходе (это `strategies/`).
- ❌ Кэширования long-term исторических данных (это `data/` слой).
- ❌ Логики усреднения/доливов — нет API `add_to_position`. Только `open_new` и `close`. Архитектурный запрет, см. [[бизнес/правила-торговли/усреднение-запрет]] §«Технический контроль».

---

## 3. Архитектура

### Слои

```
┌──────────────────────────────────────────┐
│  strategies/* , core/risk/, core/backtest/  │  ← клиенты адаптера
├──────────────────────────────────────────┤
│  ExchangeAdapter (Protocol/ABC)           │  ← интерфейс, общий для всех бирж
├──────────────────────────────────────────┤
│  adapters/bingx/BingXAdapter              │  ← реализация для BingX
├─────────────┬────────────┬────────────────┤
│  RestClient │  WsClient  │  AuthSigner    │  ← внутренние компоненты
├─────────────┴────────────┴────────────────┤
│  HTTP (httpx) , WebSocket (websockets)    │  ← транспорт
└──────────────────────────────────────────┘
```

**Принцип:** клиенты адаптера видят `ExchangeAdapter` как абстракцию. Внутренности BingX скрыты. Замена биржи в будущем — только новый класс, реализующий тот же протокол.

### Файловая структура

```
adapters/
├── __init__.py
├── base.py                  ← ExchangeAdapter (Protocol), доменные модели
├── errors.py                ← общие исключения (AdapterError, RateLimited, OrderRejected, ...)
├── bingx/
│   ├── __init__.py
│   ├── adapter.py           ← BingXAdapter — публичная точка входа
│   ├── rest.py              ← REST-клиент: подпись, retry, rate limit
│   ├── ws.py                ← WebSocket-клиент: reconnect, subscriptions
│   ├── signer.py            ← HMAC подпись запросов
│   ├── mapping.py           ← маппинг ответов BingX → доменные модели
│   ├── endpoints.py         ← список endpoint-ов как константы
│   └── tests/
│       ├── test_signer.py
│       ├── test_mapping.py
│       ├── test_rest_mocked.py
│       └── test_ws_mocked.py
```

### Доменные модели (в `adapters/base.py`)

Минимальный набор dataclasses (`@dataclass(slots=True, frozen=True)` где имеет смысл):

- `Symbol` — нормализованное представление пары (`BTCUSDT`, `XAUUSDT`).
- `SymbolMeta` — tick_size, lot_size, min_notional, max_leverage, status.
- `Candle` — open_time, open, high, low, close, volume, trades_count, close_time.
- `Ticker` — bid, ask, last, mark_price, index_price, ts.
- `FundingRate` — symbol, rate, next_funding_time.
- `Position` — symbol, side (long/short/flat), size, entry_price, unrealized_pnl, leverage, liq_price, isolated_margin.
- `OpenOrder` — id, symbol, side, type, price, qty, filled_qty, status, reduce_only, ts.
- `Fill` — order_id, symbol, side, price, qty, fee, fee_asset, ts.
- `AccountBalance` — equity (USDT), available, used_margin.
- `OrderRequest` — параметры размещаемого ордера (наша сторона), без специфики BingX.

### Интерфейс `ExchangeAdapter` (черновик)

Контракты — асинхронные (`async def`). Все методы возвращают доменные модели или поднимают типизированные исключения.

```
class ExchangeAdapter(Protocol):

    # Market data
    async def list_symbols() -> list[SymbolMeta]
    async def get_klines(symbol, tf, *, since=None, until=None, limit=None) -> list[Candle]
    async def get_funding_rate(symbol) -> FundingRate
    async def get_funding_history(symbol, *, since, until) -> list[FundingRate]
    async def get_open_interest(symbol) -> Decimal
    async def get_ticker(symbol) -> Ticker

    # Account
    async def get_balance() -> AccountBalance
    async def get_positions() -> list[Position]
    async def get_open_orders(symbol=None) -> list[OpenOrder]
    async def get_fills(symbol, *, since, until) -> list[Fill]
    async def set_margin_mode(symbol, mode: Literal["isolated"]) -> None
    async def set_leverage(symbol, leverage: int) -> None
    async def set_position_mode(mode: Literal["one_way"]) -> None

    # Trading
    async def place_order(req: OrderRequest) -> OpenOrder
    async def cancel_order(symbol, order_id) -> None
    async def cancel_all(symbol) -> None
    async def close_position(symbol) -> None  # market close, для kill switch

    # Streams (async generators)
    def stream_klines(symbol, tf) -> AsyncIterator[Candle]
    def stream_ticker(symbol) -> AsyncIterator[Ticker]
    def stream_user_events() -> AsyncIterator[UserEvent]   # позиции, ордера, баланс

    # Lifecycle
    async def connect() -> None
    async def disconnect() -> None
    async def healthcheck() -> bool   # для kill switch и мониторинга
```

`UserEvent` — sealed-union (через `match`-friendly enum-discriminator) с типами: `OrderEvent`, `PositionEvent`, `BalanceEvent`, `LiquidationEvent`. Стратегии и risk engine реагируют на эти события, не дёргают REST в горячем пути.

### Что обеспечивает интерфейс на уровне дизайна

- **Никаких ручных доливов.** Нет метода `add_to_position` — см. [[бизнес/правила-торговли/усреднение-запрет]].
- **Никакой хедж-моды.** `set_position_mode("one_way")` — одна сторона на инструмент (см. [[бизнес/риск-профиль]]).
- **Стоп ставится одновременно со входом.** `place_order` принимает `OrderRequest` с опциональными `stop_loss_price` и `take_profit_price` — адаптер сам размещает связанные ордера атомарно (или эмулирует атомарность). Если БиржА API не атомарна — адаптер подтверждает позицию ТОЛЬКО после успешной постановки стопа; иначе откатывает рыночным закрытием. Соответствует жёсткому запрету «нет стопа на бирже — нет позиции» из [[бизнес/риск-профиль]].

---

## 4. Спецификации методов (детально)

### 4.1 `place_order(req: OrderRequest) -> OpenOrder`

**Параметры (наша модель):**
- `symbol: Symbol`
- `side: Literal["long_open", "short_open", "long_close", "short_close"]`
- `type: Literal["market", "limit", "stop_market", "stop_limit", "tp_market"]`
- `qty: Decimal` (в базовой валюте; адаптер сам конвертирует в notional/contracts если требуется)
- `price: Decimal | None` (для limit/stop_limit)
- `stop_price: Decimal | None` (для stop_*/tp_*)
- `reduce_only: bool` (для close-сторон)
- `post_only: bool` (для лимитов на TP)
- `time_in_force: Literal["GTC", "IOC", "FOK"]` (по умолчанию GTC)
- `attached_stop_loss: Decimal | None` (только при entry-ордере)
- `attached_take_profit: Decimal | None` (только при entry-ордере)
- `client_order_id: str` (наш UUID — для идемпотентности и журнала)

**Поведение:**
1. Локальная валидация (`pricePrecision` / `quantityPrecision` из `/openApi/swap/v2/quote/contracts`, `tradeMinUSDT`, нельзя `attached_*` при close-side).
2. **Округление price/qty до разрешённой точности.** Квирк BingX (docs-v3, страница «Place Order»): «If the precision exceeds the allowed range, the API order will still be accepted but the value will be truncated» — биржа молча усечёт значение, и журнал разъедется с фактом. Адаптер округляет на стороне клиента **до** подписи.
3. Подпись запроса (HMAC-SHA256 по сортированной по ASCII строке параметров; см. §5.2).
4. POST `/openApi/swap/v2/trade/order`. Атомарность entry + SL/TP в одном теле:
   - Поля `stopLoss` и `takeProfit` принимаются как **stringified JSON-объекты** (не как plain numbers). Пример из docs: `takeProfit='{"type":"TAKE_PROFIT_MARKET","stopPrice":31968.0,"price":31968.0,"workingType":"MARK_PRICE"}'`.
   - `workingType` фиксируем `MARK_PRICE` для всех защитных ордеров (снижает риск ловли спот-фитиля при stop hunt — см. [[бизнес/правила-торговли/мм-контр-стратегии]] п.1).
5. Если в ack пришёл `code != 0` или ордер размещён без подтверждённого SL — компенсирующее `close_position(symbol)` + ALERT (см. §3 «Атомарность entry+stop»). Это запасной путь: для штатных POST с `attached_stop_loss` BingX ставит SL атомарно, дополнительный шаг не нужен.
6. Возвращаем `OpenOrder` для entry; статусы связанных SL/TP стратегия получит через `stream_user_events` (`ORDER_TRADE_UPDATE`).

**Идемпотентность:** на стороне BingX поле — `clientOrderID` (так в payload-примере Place Order в docs-v3) либо `clientOrderId` (так в request-list Cancel Order в той же странице) — **в docs встречаются обе формы для одного и того же поля**. Адаптер использует одну (`clientOrderID` как в payload Place Order) и валидирует integration-тестом на VST в фазе 0.D. Длина 1–40 символов, сервер приводит к lowercase, уникальность в рамках аккаунта. Адаптер дополнительно держит in-memory ack-кэш + SQLite persistence на случай повторов после рестарта.

### 4.2 `close_position(symbol)` — kill switch

- Reduce_only market по полному размеру позиции в противоположную сторону.
- Используется циркуит-брейкерами и при WS-разрыве > 30 сек ([[бизнес/риск-профиль]]).
- Перед закрытием — `cancel_all(symbol)` для снятия защитных ордеров (иначе после закрытия они могут остаться висящими).

### 4.3 `stream_user_events`

- Один стрим на адаптер. Стратегии и risk engine подписываются как async iterator.
- Гарантирует **at-least-once** доставку: при reconnect делает `get_open_orders` + `get_positions` + `get_balance` и эмитит синтетические события «sync» (отметка, что это reconcile, а не свежее событие).
- При расхождении (например, ордер исполнился во время разрыва, но событие потеряно) — адаптер логирует WARNING и эмитит правильное событие. Стратегия должна быть толерантна к дубликатам (по `client_order_id`).

### 4.4 `get_klines` — пагинация, форматы интервалов, rate limit

- **Эндпоинт:** `GET /openApi/swap/v3/quote/klines` (без подписи). Параметры: `symbol` (формат `BTC-USDT` с дефисом), `interval`, `startTime`/`endTime` (ms), `timeZone` (только 0 или 8), `limit` (default 500, **max 1440**).
- **Формат свечи в REST V3:** только `open/high/low/close/volume/time` (open_time). **Нет `n` (число трейдов) и `q` (turnover/quote volume)** — если они нужны для фич, тянем через WS-канал `<symbol>@kline_<interval>` (там полный набор: T/c/h/i/l/n/o/q/s/t/v).
- **Разные форматы `interval` в REST и WS:** REST принимает `1m`, `15m`, `1h`. WS — `1min`, `15min`, `1h`. Адаптер маппит обе формы внутри в общую доменную модель.
- **Бэктест 6 мес 15m:** ~17 500 свечей → **13 чанков по 1440** с пагинацией по `endTime`. Под глобальный лимит market data 500/10s (см. §6) — спокойно укладывается даже с consecutive bulk fetch.
- Адаптер сам разбивает запрос на чанки, склеивает, дедуплицирует по `time` (open).
- Чтит rate limit: использует HTTP-заголовки `X-RateLimit-Requests-Remain` / `X-RateLimit-Requests-Expire` для адаптивного backoff; при перегрузке BingX блокирует ключ на ~5 минут (docs-v3, Frequency Limit).
- Для бэктестов отдельный режим `bulk=True` с настраиваемой паузой между запросами и progress-логом.

---

## 5. Аутентификация и безопасность

### 5.1 Ключи

- **Только торговые права. Без вывода средств.** Это требование жёсткое — [[CLAUDE.md]] §«Правила безопасности».
- **IP whitelist** обязателен. До деплоя на VPS — наш домашний/офисный IP. После — только IP VPS.
- Ключи в `.env` (читается через pydantic-settings или python-dotenv). Никогда в коде. `.env*` уже в `.gitignore`.
- **Ротация:** раз в 3 месяца (см. [[plans/00-стратегия-проекта-2026-05-09]] §5 п.5).

### 5.2 Подпись (`adapters/bingx/signer.py`)

- HMAC-SHA256 (стандарт BingX, уточнить алгоритм при аудите docs).
- Все приватные запросы: timestamp + recvWindow + параметры → канонический query → подпись → header/param.
- Sync времени с биржей: при старте делаем GET `/time`, фиксируем offset; пересчёт каждые N минут.

### 5.3 Что мы **не** даём адаптеру

- Доступ к коду фразы из `.env` напрямую — только через интерфейс `Settings` (pydantic-settings), чтобы тесты не имели доступа к live-ключам.
- Авто-апгрейд прав ключа. Если BingX ввёл новое право — обновляем вручную.

### 5.4 Логирование

- Запросы логируются на уровне DEBUG **без подписей и без ключей**. Параметры — да; secrets — нет.
- Ответы с PII (email, account id) — на INFO маскируются.
- Ошибки с rate limit / network → WARNING; ошибки с ордером (rejected, insufficient margin) → ERROR.

---

## 6. Обработка ошибок и retry-стратегия

### Иерархия исключений (`adapters/errors.py`)

- `AdapterError` (база)
  - `NetworkError` (timeout, DNS, conn reset) — retry с backoff.
  - `RateLimited` (HTTP 429, custom code) — backoff по `Retry-After` или экспоненциальный.
  - `AuthError` (401, 403) — не retry, fatal: логируем, поднимаем kill switch.
  - `OrderRejected` (биржа отказала) — содержит код причины (insufficient_margin, invalid_size, market_closed). Не retry.
  - `OrderNotFound` (для cancel/query)
  - `ServerError` (500-е) — retry с лимитом попыток.

### Retry-политика

- Идемпотентные операции (GET, ack-кэшированные POST через `client_order_id`): до N попыток (3 по умолчанию), backoff 0.5s → 1s → 2s → 4s.
- **Неидемпотентные операции, для которых нет client_order_id или сервер их не поддерживает: НЕ ретраим**. Лучше упасть и поднять алерт, чем разместить ордер дважды.

### Kill switch триггеры со стороны адаптера

| Условие | Действие |
|---|---|
| `AuthError` | поднимаем `KillSwitch`, отключаем адаптер, шлём Telegram-алерт |
| WS-стрим не отдаёт сообщения > 30 с | re-connect; если не поднялся за 30 с — `close_position` для всех символов |
| `cancel_all` после `close_position` упал | повтор раз в 5 с до успеха, ERROR-лог |
| Разные позиции в локальном состоянии и в `get_positions` (при reconcile) | принимаем биржу как источник истины, эмитим WARNING + событие |

---

## 7. Известные квирки BingX (после аудита docs-v3, 2026-05-09)

Полные ссылки и raw-цитаты — в [[бизнес/инструменты-bingx]] §«Особенности API». Здесь — сжатый список с пометкой состояния («подтверждено в docs» / «требует проверки на VST в фазе 0.B»). Источники-эндпоинты приведены прямыми путями `/openApi/...` — каждый такой путь есть как отдельная страница в docs-v3 (https://bingx-api.github.io/docs-v3/#/en/info → раздел USDT-M Perp Futures).

| # | Квирк / факт | Состояние | Что меняется в адаптере |
|---|---|---|---|
| 1 | **Symbol с дефисом:** `BTC-USDT`, не `BTCUSDT`. Все trade/quote эндпоинты помечают `symbol` как «There must be a hyphen». | подтверждено в docs | Доменная `Symbol` нормализует дефис на входе. |
| 2 | **VST (testnet) — отдельный домен.** REST `https://open-api-vst.bingx.com`, WS `wss://vst-open-api-ws.bingx.com/swap-market`. Подтверждение — описание `POST /openApi/swap/v2/trade/getVst`. Ключи VST отдельные от live. | подтверждено в docs | Адаптер берёт base URL из конфига; в `connect()` чекает `serverTime`. |
| 3 | **USDT-M (`/openApi/swap/v2/...`) ≠ Coin-M (`/openApi/cswap/v1/...`).** Разные пути и разные WS-домены. Нам нужен только USDT-M. | подтверждено в docs | В `endpoints.py` фиксируем USDT-M пути; Coin-M не реализуем в фазе 0. |
| 4 | **Position mode:** `POST /openApi/swap/v1/positionSide/dual` с `dualSidePosition: "true"` (hedge) / `"false"` (one-way). Глобально для всех контрактов; нельзя менять при наличии позиций/ордеров. | подтверждено в docs | `connect()` форсит one-way; ошибка при наличии активов — описана в `errors.py`. |
| 5 | **Margin type — три значения:** `ISOLATED` / `CROSSED` / `SEPARATE_ISOLATED` (`POST /openApi/swap/v2/trade/marginType`), не два. | подтверждено в docs | Фиксируем `ISOLATED` (см. [[бизнес/риск-профиль]] — кросс запрещён). |
| 6 | **`set_leverage`:** в hedge mode `side` ∈ {LONG, SHORT}; в one-way mode `side = "BOTH"` (LONG/SHORT не принимаются). | подтверждено в docs | В нашем one-way режиме адаптер шлёт `side="BOTH"`. |
| 7 | **Атомарность entry+SL/TP в одном POST.** `POST /openApi/swap/v2/trade/order` принимает `stopLoss` и `takeProfit` как **stringified JSON-объекты** в body (пример из docs: `takeProfit='{"type":"TAKE_PROFIT_MARKET","stopPrice":31968.0,"price":31968.0,"workingType":"MARK_PRICE"}'`). | подтверждено в docs | Адаптер сериализует attached_stop_loss/attached_take_profit в JSON-строку; `workingType` фиксирован `MARK_PRICE`. Compensating-close остаётся как fallback на error в ack. |
| 8 | **`reduceOnly` — только в one-way mode.** В hedge mode параметр игнорируется; направление задаётся `positionSide`. По умолчанию `false`. | подтверждено в docs | В наших закрывающих ордерах ставим `reduceOnly: true` (one-way всегда). |
| 9 | **`closePosition: true`** доступно для `STOP_MARKET` / `TAKE_PROFIT_MARKET` — закрывающий ордер на всю позицию без явного qty. Удобно для kill switch и position-stop. | подтверждено в docs | Используем в `close_position(symbol)` и для трейлинг-стопа. |
| 10 | **Точность молча усекается.** Если price/qty превосходят `pricePrecision`/`quantityPrecision` — биржа **не отвергает**, а **truncates** значение. | подтверждено в docs | Адаптер обязан округлять локально перед отправкой. Юнит-тест на округление обязателен. |
| 11 | **Klines V3 (`/openApi/swap/v3/quote/klines`)** не отдаёт `n` (трейды) и `q` (turnover). Поля только `o/h/l/c/v/time`. WS-канал `<symbol>@kline_<interval>` даёт полный набор. | подтверждено в docs | Если фичам нужен `n`/`q` — стримим, не запрашиваем REST. `Candle` доменная модель имеет эти поля Optional. |
| 12 | **Разный формат `interval` REST vs WS.** REST: `1m`, `15m`, `1h`. WS: `1min`, `15min`, `1h`. | подтверждено в docs | `mapping.py` маппит общую модель в обе формы. |
| 13 | **`limit` свечей max 1440.** Для 6 мес 15m — ~13 чанков. | подтверждено в docs | Пагинация в `bulk` режиме. |
| 14 | **WS лимиты подключений:** EN-доку: 200 топиков на 1 ws, 60 ws на 1 IP (error 80403 при превышении топиков). ZH-страница того же раздела указывает 240 ws на IP — **расхождение между EN и ZH версиями**. | подтверждено в docs (с расхождением) | Используем консервативные EN-цифры (60), на VST в фазе 0.B измерим фактический cap. |
| 15 | **WS gzip + текстовый Ping/Pong.** Все ответы сервера сжаты gzip. Сервер шлёт текстовое `Ping` каждые 5 сек, клиент отвечает текстовым `Pong`. **Это не JSON-payload.** | подтверждено в docs | `ws.py` декомпрессит входящие фреймы; heartbeat-handler сравнивает строку, не парсит JSON. |
| 16 | **listenKey TTL = 1 час.** Истёк — выпускаем новый и переподключаемся. | подтверждено в docs | Задача в `ws.py`: продлевать listenKey каждые 30 мин (буфер) через `POST /openApi/user/auth/userDataStream`. |
| 17 | **User Data Stream без явного subscribe.** При подключении к `swap-market?listenKey=...` сервер пушит все типы пользовательских событий: `ORDER_TRADE_UPDATE`, `ACCOUNT_UPDATE`. Тип `LIQUIDATION` приходит как тип ордера в `ORDER_TRADE_UPDATE`. | подтверждено в docs | Один `stream_user_events` стрим, без управления подписками. |
| 18 | **Подпись:** HMAC-SHA256 (64-char lowercase hex), header `X-BX-APIKEY`. Подписная строка = ASCII-сортированная конкатенация `key=value&...&timestamp=ms` **без URL-encoding**. URL-encoding только при сборке итогового URL и только для значений с `[`/`{`. `recvWindow` default 5000 мс. | подтверждено в docs | Алгоритм в `signer.py` 1:1, юнит-тест на тест-векторе из docs (Query String Example). |
| 19 | **Server time sync обязателен.** `GET /openApi/swap/v2/server/time` → `serverTime`. Если `|timestamp - serverTime| > recvWindow` — реджект «expired». Default допуск 5 сек. | подтверждено в docs | `connect()` синхронизирует offset; пересчёт каждые N минут. |
| 20 | **Rate limits per UID + per endpoint, независимы.** Заголовки `X-RateLimit-Requests-Remain` / `X-RateLimit-Requests-Expire`. При перегрузке блокировка на ~5 мин. Глобально market data — 500 req / 10 sec на ключ (changelog 2026-01-05). Backup-домен `open-api.bingx.io` — общий лимит 60 req/min, режим деградации. | подтверждено в docs | Bucket-token per-endpoint; при `429`/перегрузе exponential backoff с уважением `Retry-After`. |
| 21 | **Funding interval per symbol = 1/2/4/8 часов.** Поле `fundingIntervalHours` в `/openApi/swap/v2/quote/premiumIndex`. BTC-USDT в примере docs — 8 ч. min/max funding rate per symbol — там же (для BTC-USDT ±0.3%). | подтверждено в docs | Стратегия читает `fundingIntervalHours` per symbol, не хардкодит 8 ч. |
| 22 | **Минимальный notional BTC-USDT = $2 USDT** (`tradeMinUSDT=2` в `/openApi/swap/v2/quote/contracts`, raw-пример docs). **Это снимает блокер фазы 1** — на $1000 капитала с риском 1% и стопом 1% notional ≈ $1000, что значительно выше минимума. | подтверждено в docs (пример из эндпоинта) | Решение для фазы 1: BTC-USDT остаётся (см. §10 п.7). |
| 23 | **Идемпотентность ордеров:** поле `clientOrderID` (так в payload Place Order) либо `clientOrderId` (так в request-list Cancel Order в той же странице). Разногласие в наименовании в самих docs. Длина 1–40 символов, сервер приводит к lowercase. | подтверждено в docs (с расхождением) | Адаптер шлёт `clientOrderID` (как в Place Order), сверяет integration-тестом. |
| 24 | **`Cancel All After`** (`POST /openApi/swap/v2/trade/cancelAllAfter`) — биржевой dead-man timer: если адаптер не «погладит» биржу за N мс, она сама отменит все ордера. | подтверждено в docs | Дополняет клиентский kill switch на сетевые дисконнекты. Включаем на старте сессии, пингуем периодически. |
| 25 | **Слиппедж и спред на BTC-USDT.** Не уточнено в docs (это рыночные данные). Замер на VST (фаза 0.B–0.E) и зафиксировать в [[бизнес/инструменты-bingx]]. | требует измерения на VST | Бенчмарк latency и slippage (см. §9.1 «Bench/measurement»). |
| 26 | **Поведение API в моменты ликвидаций / крупных движений.** Не уточнено в docs (нет SLA на ack). | требует наблюдения | Адаптер логирует ack-latency на каждый ордер; смотрим эмпирику до фазы 1 deploy. |
| 27 | **WS-формат интервала в канале klines = REST-формат (`1m`), а не `1min`.** Реальное поведение live BingX (integration-тест 2026-05-10): подписка на `BTC-USDT@kline_1min` отвергается `code=80015 "dataType not support"`. Принимается только `BTC-USDT@kline_1m`. Противоречит docs-v3 §«USDT-M Perp Futures → WebSocket → Subscriptions», где явно указано `1min`. | подтверждено на live (расходится с docs) | `adapters/bingx/config.yaml`: `intervals_ws = intervals_rest`. Маппинг REST↔WS оставлен в адаптере как failsafe — на случай, если BingX вернёт документированное поведение. Зафиксировано integration-тестом. |
| 28 | **`/openApi/swap/v2/quote/contracts` не отдаёт `maxLongLeverage`/`maxShortLeverage` в live-ответе** — поля есть только в примере docs. Реальный ответ содержит `size`, `tradeMinLimit`, `apiStateOpen`, `apiStateClose`, `ensureTrigger`, `triggerFeeRate`, `launchTime`, `maintainTime`, `offTime`, `displayName`. Подтверждено integration-тестом 2026-05-10. | подтверждено на live (расходится с docs) | `Contract.max_long_leverage`/`.max_short_leverage` — `Optional[int]`. Реальное плечо берётся через `POST /openApi/swap/v2/trade/leverage` в фазе 0.C. |
| 29 | **Klines возвращаются DESC** (newest first), а не ASC. Не указано явно в docs-v3, но подтверждено integration-тестом 2026-05-10. | подтверждено на live | `PublicAPI.get_klines` локально сортирует по `open_time_ms` ASC — стратегии/бэктест получают удобный time-series порядок без сюрпризов. |
| 30 | **`/user/balance` ушёл на V3** (`/openApi/swap/v3/user/balance`), V2-путь больше не появляется в актуальном бандле docs-v3 (сверка 2026-05-11). V3 возвращает **массив** (по элементу на каждый margin-актив: USDT, BTC, ETH, …), а не одиночный объект. Поле `realisedProfit` присутствует только для USDT-строки, у крипто-активов его нет. | подтверждено в docs (JS-бандл, не SPA) | `AssetBalance.realised_profit` и `user_id` Optional; `get_usdt_balance` фильтрует USDT по `asset.upper()`. |
| 31 | **`/trade/openOrders` и `/trade/allFillOrders` обёрнуты разными ключами.** `openOrders.data = {orders: [...]}` (camelCase), `allFillOrders.data = {fill_orders: [...]}` (snake_case). Остальные list-эндпоинты (`/user/balance`, `/user/positions`) отдают массив прямо в `data`. | подтверждено в docs (JS-бандл) | `PrivateAPI.get_open_orders` / `get_fills` распаковывают вложенный ключ; рассинхрон документации/реальности уже учтён в маппинге. |
| 32 | **`stopPrice` / `avgPrice` в ордерах — могут быть пустыми строками**, а не `null` или `0`. Pydantic-валидатор `Decimal` падает на `""`. | подтверждено по примеру из docs | `OpenOrder.stop_price: str | None` + property `stop_price_decimal` → `Decimal | None`. Парсим вручную, чтобы не терять остальную модель из-за пустого поля. |

---

## 8. MM-устойчивость

См. реестр [[бизнес/правила-торговли/мм-контр-стратегии]]. От адаптера зависит реализация **технических защит**, без которых стратегия беззащитна:

| Counter-pattern | Что делает адаптер для защиты |
|---|---|
| Post-news range expansion | Только лимитные входы по флагу стратегии; market-fallback запрещён в окнах news pause. Метрика slippage на каждый fill — в журнал, для пост-анализа. |
| Liquidity grab / sweep | Атомарность entry+stop: позиция «не существует» без подтверждённого стопа на бирже. После свипа стопа адаптер немедленно эмитит `PositionEvent(closed)` — стратегия не «отыгрывает» это входом. |
| Spoofing | Адаптер **не отдаёт глубину стакана** наружу как сигнал на текущей фазе (нет `get_orderbook` в публичном интерфейсе). Если стратегия захочет — добавим осознанно с защитой по реализованному объёму. |
| Funding game | `get_funding_rate` и `get_funding_history` — first-class метод. Стратегия использует как фильтр входа. |
| Stop hunt у круглых чисел | Адаптер отдаёт mark price отдельно от last price (stream_ticker), стратегия может ставить стопы относительно mark, что снижает вероятность попадания в фитильный wick на спот-цене. |

### Атомарность entry+stop — критическая инвариантность

```
1. place_order(entry) → ok
2. place_order(stop_market reduce_only) → ?
     a. ok → позиция «оформлена», эмитим PositionEvent(opened)
     b. timeout/reject → close_position(market) → эмитим PositionEvent(rejected_protection)
                          → стратегия НЕ считает позицию открытой
                          → risk engine НЕ списывает риск-бюджет
                          → ALERT в Telegram
```

Это требование берётся из [[бизнес/риск-профиль]] §«Жёсткие запреты»: «Нет стопа на бирже — нет позиции».

---

## 9. Тестирование

### 9.1 Уровни

**Unit:**
- `signer.py`: подпись на тестовых векторах из официальной документации BingX (когда соберём).
- `mapping.py`: BingX-ответы (фиксированные JSON-фикстуры) → доменные модели. Эталоны взяты с реального VST.
- `rest.py`: с замоканным httpx (respx). Покрываем happy path + 429/500/network/auth.
- `ws.py`: с замоканным WebSocket-сервером (локальный fixture). Покрываем reconnect, потерю heartbeat, sync после ресвязи.
- Иерархия исключений: каждый тип воспроизводится в моке.

**Integration (VST):**
- Полный цикл: `connect → set_margin_mode(isolated) → set_leverage(5) → set_position_mode(one_way) → place_order(entry+SL) → wait_fill → close_position → disconnect`.
- Атомарность entry+stop: имитируем отказ постановки стопа (через сетевую задержку или принудительно отменяя стоп после ack) → проверяем, что позиция закрылась автоматически.
- Реконнект WS во время открытой позиции → проверяем, что после reconnect стрим выдаёт корректное состояние.
- Behavior при rate limit: специально превышаем — фиксируем поведение.

**Bench/measurement (VST):**
- Latency: время от `place_order` вызова до получения `OrderEvent(filled)` через WS. Цель < 500 мс на 95-перцентиле в обычные часы.
- Slippage на market entry: реальная цена fill vs ticker.last в момент отправки. Цель — медиана < 0.05% на BTCUSDT.
- WS heartbeat: средняя задержка эхо-сообщения. Цель < 300 мс.

### 9.2 Чек-лист завершения фазы 0 для адаптера

(подмножество чек-листа фазы 0 из мастер-плана)

- [ ] Все unit-тесты зелёные, покрытие критичных модулей (signer, mapping, errors) ≥ 90%.
- [ ] Integration-сценарий entry+SL+close на VST проходит стабильно (10 запусков подряд без ошибок).
- [ ] Атомарность entry+stop проверена принудительным отказом стопа.
- [ ] Реконнект WS проверен: позиция, ордера, баланс — синхронизируются автоматически.
- [ ] Файл [[бизнес/инструменты-bingx]] заполнен реальными значениями для BTC-USDT (плечо, тики, минимумы, fees, funding interval, часы, известные квирки).
- [ ] Latency и slippage замерены и зафиксированы в `ops/baseline-metrics.md`.
- [ ] Telegram-алерт на `KillSwitch` и `AuthError` подключён и протестирован (вручную триггерим).
- [ ] Security review адаптера: нет логирования secrets, нет вывода средств в правах ключа, IP whitelist на VST подтверждён.

---

## 10. 10 причин провала (критика этого плана)

1. **Документация BingX неполная или меняется без анонса.**
   - Митигация: в фазе 0.A официальный аудит документации, версионируем endpoints в `endpoints.py`, integration-тесты на VST еженедельно, breaking changes ловим раньше деплоя.

2. **VST не поведенчески идентичен живой бирже.**
   - Митигация: для критических маршрутов (latency, slippage, поведение в стрессе) — повторный замер на минимальном live-капитале до фазы 1 deploy. Не доверяем VST как 1:1.

3. **Атомарность entry+stop невозможно гарантировать средствами BingX.**
   - Митигация: у нас compensating-action (close на отказ стопа), не транзакция. Принимаем 1–2 секунды окна риска, в течение которого «голая» позиция → рыночное закрытие. Альтернатива — ничего не делать без стопа — хуже, чем 1.5 сек экспозиции.

4. **WebSocket нестабилен / часто рвётся.**
   - Митигация: reconnect с exponential backoff, синхронизация по REST после reconnect, kill switch при разрыве > 30 сек. Если эмпирически WS BingX рвётся чаще 1 раза в час — это проблема, эскалируем (Bybit-адаптер раньше в плане).

5. **Rate limit бьёт во время критичных моментов (волатильность, news).**
   - Митигация: token bucket с conservative budget (используем 70% официального лимита), приоритезация запросов (kill switch > trading > market data), отдельная квота для WS-only периодов.

6. **`client_order_id` не поддерживается / не идемпотентен.**
   - Митигация: in-memory ack-кэш + SQLite persistence на адаптере. На рестарте restore + reconcile через `get_open_orders`.

7. **Минимальный notional на BTC-USDT слишком высокий для $1k капитала.** — **Снято после аудита docs 2026-05-09.**
   - Факт: `tradeMinUSDT = 2 USDT` для BTC-USDT в примере ответа `GET /openApi/swap/v2/quote/contracts` (docs-v3, страница «USDT-M Perp Futures symbols»). Полная запись минимумов — [[бизнес/инструменты-bingx]] §«Крипта (USDT-M perpetual)».
   - Расчёт фазы 1: эквити $1 000, риск 1% = $10 на сделку, стоп 1% от цены → notional ≈ $1 000, что **в 500 раз выше** минимума $2 USDT.
   - Резерв: даже при стопе 5% (худший случай для маленьких сетапов) notional = $200 — всё равно >> $2.
   - Подтверждение на VST: integration-тест в фазе 0.B вытащит реальный `tradeMinUSDT` для BTC-USDT и сверит с примером в docs (защита от тихого изменения).
   - Решение: BTC-USDT остаётся основным инструментом фазы 1 без правок мастер-плана.

8. **Подпись HMAC реализована неверно — все приватные запросы 401.**
   - Митигация: тест-вектора из docs, ранний прогон `get_balance` на VST как smoke. Если падает — фокусированный фикс до любых ордеров.

9. **Адаптер задумывается «слишком общий» (multi-exchange abstraction раньше времени).**
   - Митигация: в этом плане один интерфейс с одной реализацией. Bybit (фаза 4+) — повод **рефакторить** интерфейс под фактические различия двух бирж, не до того.

10. **Лог пишет ключи / подписи / PII.**
    - Митигация: явный `RedactingFormatter` поверх логгера с тестом на «нет в логе слов из `.env`». В CI lint этот тест обязателен.

---

## 11. Фазы имплементации (внутри плана)

Адаптер строится поэтапно. Каждая фаза заканчивается **рабочим коммитом**.

### Фаза 0.A — Исследование (1–2 сессии) — ЗАКРЫТА 2026-05-09
- ✅ Аудит официальной документации BingX docs-v3 (REST + WS, USDT-M perp).
- ✅ §7 переписана: 26 квирков с пометкой «подтверждено в docs» / «требует проверки на VST».
- ✅ [[бизнес/инструменты-bingx]] заполнен числами для BTC-USDT и ETH-USDT, ссылки на эндпоинты-источники.
- ✅ Блокер «min notional» снят: `tradeMinUSDT=2` >> $1 000 фаза-1 notional (см. §10 п.7).
- Артефакт: коммит на ветке `claude/infallible-proskuriakova-6e981c`.
- **НЕТ кода.**

### Фаза 0.B — Каркас + публичные методы (1–2 сессии) — ЗАКРЫТА 2026-05-10
- ✅ Структура `adapters/bingx/` (10 модулей), `pyproject.toml` (httpx, websockets, pydantic, pydantic-settings, pyyaml, ruff, mypy, pytest, respx).
- ✅ `BingXClient` — async HTTP-клиент: подпись HMAC-SHA256 (как заготовка для фазы 0.C), token-bucket rate limit (350/10s — 70% от официальных), retry-policy на 429/5xx с экспоненциальным backoff, разбор envelope `{code, msg, data}` с `code!=0` → `APIError`.
- ✅ Pydantic-модели `Contract`, `Ticker`, `Kline`, `ServerTime` — все денежные поля `Decimal`, валидация дефиса в `symbol`, `extra="ignore"` для устойчивости к новым полям BingX.
- ✅ `PublicAPI`: `get_server_time`, `get_contracts`/`get_contract`, `get_ticker`, `get_klines` — с локальной валидацией `limit ≤ 1440` и сортировкой свечей ASC.
- ✅ `BingXMarketWebSocket`: gzip-декомпрессия, текстовый Ping/Pong (литералы, не JSON), session-loop с прозрачным авто-реконнектом и переподпиской, async-iterator API, watchdog на тишину 30 с.
- ✅ Тесты: **39 unit** (respx-моки) + **4 integration** (live public API). Покрытие **83.02%** (target ≥70%). Линтеры: ruff + mypy strict — чистые.
- ✅ Найдено и зафиксировано **3 новых квирка live BingX** (§7 п.27–29) расходящихся с docs-v3: WS-формат интервала = REST-форма; `maxLongLeverage` отсутствует в live `/contracts`; klines возвращаются DESC.
- **Артефакт:** `await PublicAPI(client, cfg).get_klines("BTC-USDT", "15m", limit=...)` отдаёт типизированный `list[Kline]` ASC по времени, `BingXMarketWebSocket.subscribe("BTC-USDT@kline_1m")` отдаёт async-iterator data-фреймов с авто-реконнектом.

### Фаза 0.C — Аутентификация и приватный read (1 сессия) — ЗАКРЫТА 2026-05-11
- ✅ `adapters/bingx/settings.py` — `BingXSettings` (pydantic-settings) с парами live/vst, `SecretStr`-маскированием, `credentials_for(env)` с `ConfigError` на половинные пары. `.env.example` в корне репозитория, `.env` уже whitelist'нут в `.gitignore`.
- ✅ Server-time sync в `BingXClient`: `sync_server_time()` + `now_ms()` + автосинк при первом `request_signed` и далее не чаще `signing.server_time_resync_interval_s` (300 с). Поправка на RTT — серверное время берётся в середине окна `local_before/local_after`.
- ✅ `request_signed`: timestamp от `now_ms()`, recvWindow + signature, `X-BX-APIKEY` в headers, прохождение через тот же token-bucket + retry, что и `request_public`.
- ✅ Pydantic-модели: `AssetBalance`, `Position`, `OpenOrder` (с `stop_price_decimal` для пустых строк), `Fill` (с `filled_at`), `PositionMode`, `LeverageInfo`. Все денежные поля Decimal, опциональные — где BingX отдаёт значение не во всех окружениях.
- ✅ `adapters/bingx/private.py` — `PrivateAPI`: `get_balance`, `get_usdt_balance`, `get_positions`, `get_open_orders`, `get_fills`, `get_position_mode`, `set_position_mode`, `set_margin_type`, `set_leverage`, плюс `ensure_invariants(symbol, leverage)` — bootstrap one-way + ISOLATED + leverage за 3 идемпотентных POST'а.
- ✅ Эндпоинты сверены 2026-05-11 по docs-v3 JS-бандлу (`bingx-api.github.io/docs/static/js/app.*.js`): `balance` ушёл на V3 (массив per-asset, `realisedProfit` Optional), `openOrders` обёрнут в `{orders: [...]}`, `allFillOrders` — в `{fill_orders: [...]}` (snake_case в отличие от camelCase в остальных эндпоинтах). Запись в §7 п.30 ниже.
- ✅ Тесты: **64 unit** (17 на PrivateAPI + 8 на Settings + старые) с respx; 8 integration-тестов (4 публичных live + 4 приватных VST, последние skip без `BINGX_VST_API_KEY/SECRET`). Покрытие **86.51%** (target ≥70%). Линтеры ruff + mypy strict — чистые.
- **Артефакт:** `await PrivateAPI(client, cfg).get_balance()` отдаёт `list[AssetBalance]`; `ensure_invariants("BTC-USDT", 5)` приводит VST-аккаунт к жёстким инвариантам риск-профиля. Smoke на VST остался за пользователем: создать demo-ключи в BingX Demo Trading, положить в `.env`, прогнать `pytest -m integration` — приватная подгруппа выполнится автоматически.

### Фаза 0.D — Trading и kill switch (2 сессии)
- `place_order` (market, limit, stop_market, stop_limit, tp_market).
- Атомарность entry+stop с compensating close.
- `cancel_order`, `cancel_all`, `close_position`.
- `stream_user_events` с reconcile после reconnect.
- Полный integration-сценарий на VST.

### Фаза 0.E — Hardening и метрики (1 сессия)
- Retry-стратегия, ack-кэш, persistence.
- Replay/reconcile после рестарта.
- Latency и slippage benchmark, baseline в `ops/baseline-metrics.md`.
- Telegram-алерты на критичные события.
- Security review (см. чек-лист §9.2).
- Итог фазы 0 для адаптера: PR/коммит и галочки.

---

## 12. Бэклог идей (для адаптера, не сейчас)

- Multi-account support (sub-accounts) — фаза 4+ при распределении капитала.
- Coin-M perp поддержка — если появится инструмент только в Coin-M.
- Order book streaming — только осознанно после фазы 2, с защитой от спуфинга.
- Bybit-адаптер как второй реализатор того же интерфейса (фаза 4+ по мастер-плану).
- Унифицированный `MarketDataCache` слой между биржами — после второй биржи.

---

## 13. Что СЕЙЧАС, в ближайшую сессию

Фазы 0.A/0.B/0.C закрыты. **Следующая сессия — фаза 0.D (trading + kill switch).**

Прежде чем кодить — **обязательный пользовательский шаг** (выполняется один раз):
- Создать demo-ключи в [BingX → Demo Trading](https://bingx.com/en/accounts/api). Положить в `.env` как `BINGX_VST_API_KEY` / `BINGX_VST_API_SECRET`. IP whitelist — VPS-IP (`187.124.41.13`) и/или текущий рабочий IP. Без прав на вывод средств.
- Прогнать `pytest -m integration` — 4 публичных теста (по live BingX) и 4 приватных теста на VST. Все должны быть зелёными до старта фазы 0.D.

Конкретные задачи фазы 0.D (из §11):
1. `OrderRequest` (модель domain-уровня) с маппингом в BingX-payload (`stopLoss`/`takeProfit` как stringified JSON, см. §4.1 и квирк §7 п.7).
2. `place_order(req)`: market / limit / stop_market / stop_limit / tp_market.
3. Атомарность entry+stop с compensating close. Лог ack-latency на каждый ордер.
4. `cancel_order(symbol, order_id)`, `cancel_all(symbol)`, `close_position(symbol)`.
5. `stream_user_events` (WS-listenKey) с reconcile после reconnect: эмитим синтетические `sync`-события сверкой `get_open_orders`/`get_positions`/`get_balance`.
6. Cancel-All-After dead-man timer (§7 п.24) включается на старте сессии, периодически продлевается.
7. Integration-сценарий entry+SL+close на VST: 10 запусков подряд, latency и slippage в `ops/baseline-metrics.md`.

**Параллельно** (другая сессия / другой контекст) можно начать `plans/04-риск-движок.md` — он не зависит от BingX-API детально, только от интерфейса адаптера, который зафиксирован в §3 этого документа.

---

## 14. Артефакты этой сессии

Сессия предыдущая (создание плана):
- `plans/01-bingx-адаптер.md` (этот файл).
- `бизнес/правила-торговли/усреднение-запрет.md`.
- `бизнес/правила-торговли/мм-контр-стратегии.md`.
- Обновлён `бизнес/INDEX.md` (добавлены ссылки на два новых правила).

Сессия 2026-05-09 (фаза 0.A — исследование docs):
- Заполнен [[бизнес/инструменты-bingx]] реальными числами для BTC-USDT и ETH-USDT, базовыми URL (live + VST, REST + WS), деталями подписи / rate limits / WS-каналов / klines / atomic SL/TP.
- Переписан §7 этого плана: 26 пунктов с пометкой «подтверждено в docs» / «требует проверки на VST».
- Уточнён §4.1 (place_order: stringified JSON для attached SL/TP, локальное округление, разногласие в имени `clientOrderID`/`clientOrderId`).
- Уточнён §4.4 (klines: V3-формат, 1440 limit, разные интервалы REST vs WS).
- Снят блокер фазы 1 (§10 п.7): `tradeMinUSDT=2` для BTC-USDT, $1 000 капитала проходит без правок мастер-плана.
- Фаза 0.A помечена закрытой; §13 переключён на фазу 0.B.

Сессия 2026-05-10 (фаза 0.B — каркас + публичные методы, первый код в проекте):
- `pyproject.toml` (Python 3.12+, ruff + mypy strict + pytest + coverage + httpx + websockets + pydantic + pydantic-settings).
- `adapters/bingx/` целиком: `config.yaml` (все числа со ссылками на источники), `config.py` (pydantic-валидация YAML), `exceptions.py`, `models.py` (Contract/Ticker/Kline/ServerTime на Decimal), `client.py` (async HTTP + sign_query + token-bucket + retry), `public.py` (4 публичных метода), `websocket.py` (gzip + Ping/Pong + auto-reconnect).
- `adapters/bingx/tests/`: 39 unit-тестов с respx + 4 integration-теста против live BingX. Покрытие 83.02%.
- §7 пополнен 3 новыми квирками (п.27–29) на основе живых данных, расходящихся с docs.
- §13 переключён на фазу 0.C (приватные read на VST). §11 фаза 0.B помечена закрытой.

Сессия 2026-05-11 (фаза 0.C — аутентификация + приватные read + setters):
- Сверка приватных эндпоинтов BingX через JS-бандл docs-v3 (`bingx-api.github.io/docs/static/js/app.*.js`) — извлечено 60+ путей с примерами payload'ов для balance/positions/openOrders/allFillOrders/marginType/leverage/positionSide-dual.
- `adapters/bingx/settings.py` — `BingXSettings(BaseSettings)` с парами live/vst, `SecretStr` для маскирования в repr, `credentials_for(env)` бросает `ConfigError` на половинные ключи; `.env.example` в корне.
- `adapters/bingx/client.py` — server-time sync: `sync_server_time()` считает offset с поправкой на RTT, `now_ms()` возвращает скорректированное время, `_ensure_server_time_synced()` синхронизирует перед первым `request_signed` и далее не чаще `signing.server_time_resync_interval_s`.
- `adapters/bingx/models.py` — `AssetBalance`, `Position`, `OpenOrder` (с `stop_price_decimal` property для пустых строк BingX), `Fill` (с `filled_at` property ISO-8601), `PositionMode` (`is_hedge_mode` bool из строки), `LeverageInfo`.
- `adapters/bingx/private.py` — `PrivateAPI` (10 методов + `ensure_invariants` bootstrap one-way+ISOLATED+leverage за три идемпотентных POST'а).
- `adapters/bingx/config.yaml` пополнен секцией `private_endpoints`, `config.py` — моделью `PrivateEndpoints` (strict, frozen).
- `adapters/bingx/tests/test_settings.py` (8 тестов) + `test_private.py` (17 тестов) с respx-моками и фикстурами; 4 новых integration-теста на VST с авто-skip при отсутствии ключей. Покрытие **86.51%**, mypy strict + ruff чистые.
- §7 пополнен 3 новыми квирками (п.30 — V3 balance is array; п.31 — разные обёртки `orders`/`fill_orders`; п.32 — пустые строки в `stopPrice`/`avgPrice`).
- §13 переключён на фазу 0.D (trading + kill switch). §11 фаза 0.C помечена закрытой. Smoke на VST остался за пользователем — после создания demo-ключей и `pytest -m integration`.

---

## 15. Резюме

**Что было:** в мастер-плане BingX-адаптер указан как первая техническая задача фазы 0 в одну строку — без интерфейса, без скоупа, без контракта на «нет позиции без стопа», без плана исследования API.

**Что стало:** конкретный интерфейс `ExchangeAdapter` (16 методов + 3 стрима + lifecycle), доменные модели, спецификация `place_order` с атомарным `entry+stop`, явные защитные инварианты (one-way, isolated, нет API-усреднения), 5 этапов имплементации с чёткими артефактами, чек-лист завершения, 10 причин провала, секция MM-устойчивости со ссылкой на реестр.

**Какую проблему решал:** превратил «реализовать BingX-адаптер» в проверяемый план с понятными границами и понятными первыми шагами (фаза 0.A — исследование, не код). Зафиксировал на уровне архитектуры все запреты из риск-профиля и правил торговли, чтобы они работали как инвариантность системы, а не как «дисциплина пользователя».

**Было ли это самым эффективным решением:** да. Альтернатива «начать кодить» приведёт к: (а) угадыванию квирков BingX и переделкам, (б) пропуску атомарности entry+stop как ключевой инвариантности, (в) отсутствию метрик baseline для оценки фазы 1. План делает следующую сессию (фаза 0.A) дешёвой и обратимой.

# План 06 — Фаза 0.D part 2: user-data stream + dead-man timer + compensating-close

**Дата:** 2026-05-11
**Статус:** актуальный — план + реализация в той же сессии
**Связано:** [[plans/01-bingx-адаптер]] §7 п.15–17/§7 п.24/§11 фаза 0.D, [[plans/05-фаза-0D]], [[бизнес/инструменты-bingx]], [[бизнес/риск-профиль]]

---

## 1. Контекст

0.D part 1 закрыта: place_order/cancel_order/cancel_all/close_position работают на VST. Не хватает:

- **Никакой обратной связи в реальном времени:** статусы ордеров (FILLED/CANCELED) узнаём только через `get_open_orders`/`get_fills` polling. Это убийственно для kill switch на сетевом разрыве и для атомарности «entry+SL подтверждён».
- **Нет dead-man timer на стороне биржи:** если адаптер упадёт с открытой позицией, бирже это не помешает «висеть» — стопы на SL сработают только если рынок дойдёт.
- **Compensating-close не реализован:** в маловероятном случае «ack без подтверждённого SL» нет автоматики, позиция останется голой.

## 2. Цель плана

Закрыть остаток фазы 0.D:

1. `PrivateAPI.create_listen_key` / `keep_alive_listen_key` / `close_listen_key`.
2. `BingXUserDataStream` — WS-клиент на `swap-market?listenKey=...`, парсит `ACCOUNT_UPDATE` и `ORDER_TRADE_UPDATE`, авто-реконнект с обновлением listenKey каждые 30 мин (буфер от TTL 1 час).
3. `PrivateAPI.cancel_all_after(timeout_ms)` — биржевой dead-man (POST `/openApi/swap/v2/trade/cancelAllAfter`). Стратегия пингует каждые N сек.
4. **Compensating-close в `place_order`**: после ack `place_order` адаптер проверяет, что для entry-ордера есть **связанный SL-ордер** на бирже (через `get_open_orders`). Если нет в течение `compensating_check_timeout_ms` — рыночное `close_position` + `OrderRejected` исключение.
5. Integration на VST: открыть позицию через `place_order` → получить `ORDER_TRADE_UPDATE` в стриме → закрыть через `cancel_all_after` с коротким timeout (имитация разрыва).

**Что НЕ делаем в этой фазе:**
- ❌ Reconcile после reconnect (синтетические sync-события) — отдельный план в фазе 0.E (вместе с persistence ack-кэша).
- ❌ Standalone stop_market / stop_limit / tp_market — атрибуты под отдельный план в 1+ (когда понадобится для не-attached сценариев).
- ❌ Telegram-алерты, метрики latency — фаза 0.E.

## 3. Спецификация

### 3.1 listenKey methods в `PrivateAPI`

- `await create_listen_key() -> str` — POST signed; возвращает строку listenKey.
- `await keep_alive_listen_key(listen_key) -> None` — PUT signed с `listenKey=...`. Idempotent.
- `await close_listen_key(listen_key) -> None` — DELETE signed. На теплом завершении адаптера.

Эндпоинты в `config.yaml`:
- `user_data_stream: /openApi/user/auth/userDataStream` (POST/PUT/DELETE — один путь).

### 3.2 `BingXUserDataStream` (новый файл `adapters/bingx/user_stream.py`)

Структура близка к `BingXMarketWebSocket` (websocket.py) — переиспользуем gzip, Ping/Pong, watchdog, async-iterator API.

```
class BingXUserDataStream:
    def __init__(self, private_api: PrivateAPI, config: BingXConfig, ...): ...

    async def __aenter__(self): ...   # create_listen_key + start loop
    async def __aexit__(...): ...     # close_listen_key + cancel tasks

    @property
    def listen_key(self) -> str: ...  # текущий ключ

    async def events(self) -> AsyncIterator[UserStreamEvent]: ...
```

URL: `f"{ws_base}?listenKey={listen_key}"`. WS base из `endpoints.<env>.ws_market`.

Внутренности:
- **Один фоновый task на keep-alive:** каждые `keep_alive_interval_s` (по умолчанию 1800 = 30 мин) зовёт `keep_alive_listen_key`. При ошибке — пере-создаёт listenKey и переподключается.
- **Session-loop как в market WS:** reconnect + переподписка не нужна (User Data Stream без subscribe).
- **Watchdog 60 сек** (выше market-WS, потому что user-data events идут редко в спокойном рынке).

### 3.3 События

`adapters/bingx/private_models.py`:

```
class OrderUpdateEvent(_StrictModel):
    event_type: Literal["ORDER_TRADE_UPDATE"]
    event_time_ms: int = Field(alias="E")
    symbol: str
    side: OrderSide
    type: OrderType
    status: OrderStatus
    order_id: str
    client_order_id: str | None
    price: Decimal
    quantity: Decimal
    executed_quantity: Decimal
    avg_price: Decimal | None
    reduce_only: bool
    execution_type: Literal["NEW", "CANCELED", "CALCULATED", "EXPIRED", "TRADE"]

class AccountUpdateEvent(_StrictModel):
    event_type: Literal["ACCOUNT_UPDATE"]
    event_time_ms: int = Field(alias="E")
    balances: list[BalanceDelta]
    positions: list[PositionDelta]

UserStreamEvent = OrderUpdateEvent | AccountUpdateEvent
```

Чёткие модели нужны: каждое событие должно идти в risk-engine с типизацией.

### 3.4 `cancel_all_after(timeout_ms)` в `PrivateAPI`

POST `/openApi/swap/v2/trade/cancelAllAfter` с параметром `timeOut` (in ms). `timeOut=0` отменяет таймер. Идемпотентность: каждый вызов сбрасывает предыдущий таймер.

`config.yaml` (новые числа):
- `cancel_all_after.default_window_ms: 60000` — 60 сек. Стратегия пингует каждые 20 сек (1/3 от окна).

### 3.5 Compensating-close в `place_order`

Логика после получения ack от BingX:
1. Если `req.attached_stop_loss is None` (close-side / reduce_only) → возвращаем ack как есть, выход.
2. Иначе ждём `compensating_check_delay_ms` (по умолчанию 500 ms — BingX публикует attached SL в openOrders с небольшой задержкой).
3. `await get_open_orders(symbol)` → ищем ордер с `type in {"STOP_MARKET", "STOP"}` и `reduce_only=true`.
4. Если найден — успех, возвращаем ack.
5. Если **не** найден — `await close_position(symbol)` + `raise OrderRejected("entry placed without confirmed SL — compensating close triggered")`.

`config.yaml` (новые числа):
- `place_order.compensating_check_delay_ms: 500`
- `place_order.compensating_check_attempts: 3` (retry с экспоненциальным backoff 500ms → 1s → 2s).

### 3.6 Exceptions

Расширяем `exceptions.py`:
- `OrderRejected(BingXError)` — ордер размещён, но post-условие не выполнено (например, SL не подтвердился). Используется для compensating-close.

## 4. Защита

- VST-only: `cancel_all_after` стартует на старте `BingXUserDataStream.__aenter__` с дефолтным timeOut, опционально (флаг `enable_dead_man=False` по умолчанию, чтобы integration-тесты не блокировали аккаунт).
- На `__aexit__` — `cancel_all_after(0)` (отмена таймера) перед `close_listen_key`. Чтобы рестарт адаптера не оставлял dead-man в подвешенном состоянии.

## 5. Чек-лист закрытия

- [ ] `PrivateAPI.create_listen_key/keep_alive_listen_key/close_listen_key/cancel_all_after`.
- [ ] `BingXUserDataStream` (новый модуль) + интеграция в `__init__.py`.
- [ ] `OrderUpdateEvent`, `AccountUpdateEvent` в `private_models.py` + типизация union'а.
- [ ] `OrderRejected` в `exceptions.py`.
- [ ] Compensating-close в `place_order`.
- [ ] Эндпоинты + числа в `config.yaml` (`user_data_stream`, `cancel_all_after.*`, `place_order.compensating_*`).
- [ ] Unit-тесты: listenKey lifecycle, event-parsing, compensating-close (с моком openOrders), cancel_all_after.
- [ ] Integration на VST: open позицию → дождаться `ORDER_TRADE_UPDATE(FILLED)` в стриме → close → дождаться `ACCOUNT_UPDATE` с нулевой позицией.
- [ ] retro + plans/01 (§11 фаза 0.D part 2 → закрыта, §13 → 0.E) + plans/00 чек-лист.
- [ ] Коммит + push + draft PR.

## 6. Резюме

**Было:** ордера отправляются, но «выстрелил и забыл» — статусы тянем через polling. Сетевой разрыв = голая позиция без kill switch на стороне биржи.

**Будет:** user-data stream даёт push-уведомления (latency < 500 мс по плану metrics). Биржевой dead-man (`cancelAllAfter`) гарантирует автоотмену всех ордеров при разрыве > N секунд. Compensating-close не даёт entry «провисеть» без SL.

**Альтернатива «остановиться на 0.D part 1 и начать стратегию»:** нет — risk-engine не может работать без push-событий. Polling каждые 1-2 сек = превышение rate-limit и значительная задержка реакции на FILLED/STOP сработавшие.

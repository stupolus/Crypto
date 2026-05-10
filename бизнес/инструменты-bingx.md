# Инструменты BingX

Все цифры — со ссылкой на источник. Источник по умолчанию — официальная документация BingX-API: https://bingx-api.github.io/docs-v3/#/en/info (на 2026-05-09 V2-портал `bingx-api.github.io/docs/` редиректит на этот). Где число пришло из примера ответа эндпоинта `/openApi/swap/v2/quote/contracts` — оно зафиксировано «как в docs»; реальные текущие значения пуллим из этого же эндпоинта в фазе 0.B `БитX-адаптера`.

Дата последнего аудита docs: **2026-05-09**.

## Базовые URL

### REST
- **Live:** `https://open-api.bingx.com` ([docs-v3 → Quick Start → Signature Authentication](https://bingx-api.github.io/docs-v3/#/en/Quick%20Start/Signature%20Authentication)).
- **Backup:** `https://open-api.bingx.io` — открыт «только когда основной недоступен», общий лимит **60 req/min** (там же).
- **VST (demo):** `https://open-api-vst.bingx.com` — отдельный домен для Virtual Simulated Trading. Подтверждение — описание эндпоинта `Apply VST` в docs-v3: «Only available for demo trading, demo domain: https://open-api-vst.bingx.com».

### WebSocket (USDT-M perpetual swap)
- **Public market data live:** `wss://open-api-swap.bingx.com/swap-market` ([docs-v3 → USDT-M Perp Futures → WebSocket → Connection Limitations](https://bingx-api.github.io/docs-v3/#/en/USDT-M%20Perp%20Futures)).
- **Private (user data) live:** `wss://open-api-swap.bingx.com/swap-market?listenKey=<KEY>` (тот же документ, секция Account Data Stream).
- **VST market+user:** `wss://vst-open-api-ws.bingx.com/swap-market` (тот же документ, Access).

### WebSocket (Spot и Coin-M — для справки, в фазе 0–1 не используем)
- Spot: `wss://open-api-ws.bingx.com/market`
- Coin-M perp (cswap): `wss://open-api-cswap-ws.bingx.com/market`

## Крипта (USDT-M perpetual)

| Тикер     | Макс. плечо | Tick size (price)       | Lot step (qty)           | Min qty       | Min notional      | Maker / Taker    | Funding interval | Часы | Заметки |
|-----------|-------------|-------------------------|--------------------------|---------------|-------------------|------------------|------------------|------|---------|
| BTC-USDT  | 125x        | 0.1 USDT (`pricePrecision=1`) | 0.0001 BTC (`quantityPrecision=4`) | 0.0001 BTC    | **2 USDT**        | 0.020% / 0.050%  | 8 ч              | 24/7 | основной для фазы 1 |
| ETH-USDT  | 125x        | 0.01 USDT (`pricePrecision=2`) | 0.01 ETH (`quantityPrecision=2`) | 0.01 ETH      | 2 USDT            | 0.020% / 0.050%  | 8 ч              | 24/7 | бэкап / диверсификация |
| SOL-USDT  | tbd         | tbd                     | tbd                      | tbd           | 2 USDT (typical)  | 0.020% / 0.050%* | 1/2/4/8 ч**      | 24/7 | подтянем `/quote/contracts` в фазе 0.B |

*Maker/Taker для BTC-USDT и ETH-USDT — точные значения из примера в docs (`makerFeeRate=0.0002`, `takerFeeRate=0.0005`). Для других тикеров значения те же по умолчанию, но валидируем через тот же эндпоинт.

**Funding interval per symbol = 1, 2, 4 или 8 часов — поле `fundingIntervalHours` в `/openApi/swap/v2/quote/premiumIndex` (см. ниже §Funding). Пример из docs для BTC-USDT — 8 часов.

«24/7» для крипто-перпов — рыночная конвенция; явно в docs не выписано, но эндпоинт `apiStateOpen=true / apiStateClose=true / status=1` подтверждает «постоянно открыто на API». Время плановых обслуживаний (`maintainTime`, `offTime`) — фиксированы per symbol в `/quote/contracts` и пустые для BTC-USDT/ETH-USDT в примере.

**Источник всех чисел в таблице:** [GET /openApi/swap/v2/quote/contracts](https://bingx-api.github.io/docs-v3/#/en/USDT-M%20Perp%20Futures), пример ответа в docs:

```json
{"contractId":"100","symbol":"BTC-USDT","quantityPrecision":4,"pricePrecision":1,
 "feeRate":5e-4,"makerFeeRate":2e-4,"takerFeeRate":5e-4,
 "tradeMinQuantity":1e-4,"tradeMinUSDT":2,
 "maxLongLeverage":125,"maxShortLeverage":125,
 "currency":"USDT","asset":"BTC","status":1, ...}
```

## Металлы и индексы (RWA-перпы)

Не уточнено в `/openApi/swap/v2/quote/contracts` — пример в docs только для крипты. Подтянем через тот же эндпоинт + UI BingX в фазе 2 («Аудит ликвидности RWA» из мастер-плана). Заполняется при первой технической сессии под золото/индексы.

| Тикер | Тип | Макс. плечо | Tick | Lot | Min notional | Funding interval | Часы | Заметки |
|---|---|---|---|---|---|---|---|---|
| GOLD/XAU | tokenized perp | TODO | TODO | TODO | TODO | TODO | TODO (вне CME часов?) | проверим в фазе 2 |
| SILVER/XAG | tokenized perp | TODO | TODO | TODO | TODO | TODO | TODO | вторая фаза металлов |

| Тикер | Что отражает | Макс. плечо | Часы | Заметки |
|---|---|---|---|---|
| NASDAQ100 | Nasdaq-100 perp | TODO | TODO | для фазы 3 |
| SPX/S&P500 | S&P 500 perp | TODO | TODO | для фазы 3 |

## Акции (TradFi-style)

То же самое — TODO до фазы 3.

## Комиссии (USDT-M perp, общие)

- **Maker fee:** 0.020% (default из примера `/quote/contracts` для BTC-USDT, ETH-USDT). Возможны индивидуальные ставки по статусу аккаунта/VIP.
- **Taker fee:** 0.050% (там же).
- **Funding:** интервал per symbol — 1/2/4/8 часов (`fundingIntervalHours`); ставка кэпирована `minFundingRate`/`maxFundingRate` в `/openApi/swap/v2/quote/premiumIndex` (для BTC-USDT диапазон ±0.3%).
- **Withdrawal fee:** не относится к торговому пути; не фиксируем в этом файле (ключи **без вывода**, см. CLAUDE.md и `риск-профиль.md`).

## Особенности API

### Подпись и авторизация

Источник: [docs-v3 → Quick Start → Signature Authentication](https://bingx-api.github.io/docs-v3/#/en/Quick%20Start/Signature%20Authentication).

- **Header:** `X-BX-APIKEY: <api_key>`.
- **Алгоритм:** HMAC-SHA256, выход — 64-символьная hex-строка lowercase.
- **Канонизация:** все параметры (бизнес + `timestamp`) сортируем по ASCII по имени → склеиваем `key1=v1&key2=v2&...&timestamp=ms` → подписываем. **В подписной строке — без URL-encoding.**
- **`recvWindow`:** окно валидности запроса в миллисекундах. По умолчанию 5000 мс. Если `|timestamp - serverTime| > recvWindow` — запрос отклонён как «expired».
- **Server time:** `GET /openApi/swap/v2/server/time` → `{"data":{"serverTime":<ms>}}`. Адаптер синхронизирует offset при `connect()` и периодически пересчитывает.
- **JSON body** — для редких эндпоинтов (sub-account, transfer asset). Подпись и `timestamp` в этих случаях кладутся **в body**, не в query. Все trade/quote эндпоинты USDT-M perp идут через query string.
- **Ключи** создаются в [User Center → API Management](https://bingx.com/en/accounts/api). По умолчанию — read-only; для торговли надо явно дать «Professional Futures Trading». IP whitelist рекомендуется в самом портале.

### Rate limits

- **Per UID, per endpoint, независимы.** При перегрузке система блокирует запросы и **восстанавливается через 5 минут** (docs-v3 → Quick Start → Frequency Limit).
- **Заголовки:** `X-RateLimit-Requests-Remain` (оставшиеся) и `X-RateLimit-Requests-Expire` (когда окно сбрасывается). Адаптер использует их для адаптивного backoff.
- **Per-endpoint лимиты** указаны в каждом эндпоинте как `rate-limitation` и `ip-rate-limitation`. Примеры: `Place Order POST` — 10/sec UID + ip-bucket=3; `Cancel Order DELETE` — 10/sec; `Set Leverage POST` — 5/sec; `Change Margin Type POST` — 2/sec; `Set Position Mode POST` — 4/sec; `Apply VST POST` — 5/sec. (Точные числа — в каждой странице эндпоинта в docs-v3.)
- **Глобальный лимит market data:** с 2026-01-05 (changelog docs-v3) — все market endpoints ограничены **500 запросов / 10 секунд** на ключ.
- **Backup-домен** `open-api.bingx.io` имеет общий лимит **60 req/min** — это режим деградации, не повседневный.

### Точность (price / quantity)

- **`pricePrecision`** — число знаков после запятой для цены (для BTC-USDT = 1 → шаг 0.1 USDT). **`quantityPrecision`** — то же для qty (для BTC-USDT = 4 → шаг 0.0001 BTC).
- **Квирк:** если в ордере точность превышает разрешённую — API **не отвергнет, а молча усечёт** значение. Пример из docs: «If the precision exceeds the allowed range, the API order will still be accepted but the value will be truncated. For example, if precision is 0.0001 and you submit 0.123456, it will be submitted as 0.1234.» → Адаптер обязан округлять локально **перед** отправкой, иначе журнальная цена/объём не будут соответствовать ожидаемым.

### Symbol format

- **С дефисом:** `BTC-USDT`, не `BTCUSDT`. Параметр `symbol` помечен «There must be a hyphen/`-` in the trading pair symbol» в docs-v3 для всех trade/quote эндпоинтов.

### Position mode и Margin

- **POST `/openApi/swap/v1/positionSide/dual`** — `dualSidePosition: "true"` = hedge (двусторонний), `"false"` = one-way (односторонний). Применяется глобально; нельзя менять при наличии позиций или ордеров.
- **POST `/openApi/swap/v2/trade/marginType`** — `marginType` ∈ {`ISOLATED`, `CROSSED`, `SEPARATE_ISOLATED`}. Три значения, не два! Адаптер использует `ISOLATED` (см. `риск-профиль.md` — кросс запрещён).
- **POST `/openApi/swap/v2/trade/leverage`** — поле `side` ∈ {`LONG`, `SHORT`} в hedge mode или **`BOTH`** в one-way mode. В one-way `LONG`/`SHORT` не принимаются.

### Атомарность entry + SL/TP

- **POST `/openApi/swap/v2/trade/order`** принимает `takeProfit` и `stopLoss` как **stringified JSON-объекты** в одном теле запроса. Пример из docs:
  ```
  takeProfit='{"type":"TAKE_PROFIT_MARKET","stopPrice":31968.0,"price":31968.0,"workingType":"MARK_PRICE"}'
  ```
- Это и есть **атомарный entry+SL/TP в одном POST** — соответствует жёсткому требованию «нет стопа на бирже — нет позиции» из `риск-профиль.md`. Адаптеру не нужен compensating-close в горячем пути для штатной постановки.
- Для уже открытой позиции SL/TP ставится отдельным условным ордером (`STOP_MARKET` + `closePosition: true` или `reduce_only: true`).

### `reduceOnly` и `closePosition`

- **`reduceOnly`** работает **только в one-way mode**, по умолчанию `false`; в hedge mode параметр игнорируется (направление задаётся `positionSide`). Для нашей архитектуры (one-way) `reduceOnly: true` ставится на закрывающие/защитные ордера.
- **`closePosition: true`** доступно для `STOP_MARKET` / `TAKE_PROFIT_MARKET` — закрывающий ордер привязан к **всей** позиции, без указания `quantity`. Удобно для kill switch / position-stop.

### Ордер-типы (POST `/openApi/swap/v2/trade/order`)

Из docs-v3 примеры payload: `LIMIT`, `MARKET`, `STOP_MARKET`, `TAKE_PROFIT_MARKET`, `STOP`, `TAKE_PROFIT`, `TRIGGER_LIMIT`, `TRIGGER_MARKET`, `TRAILING_STOP_MARKET`, `TRAILING_TP_SL`, `POSITION_STOP_MARKET` (= `STOP_MARKET` + `closePosition: true`), `POSITION_TAKE_PROFIT_MARKET`. `workingType` ∈ {`MARK_PRICE`, `CONTRACT_PRICE`} — на что смотрит триггер.

### `Cancel All After` (dead-man switch)

- **POST `/openApi/swap/v2/trade/cancelAllAfter`** — таймер: если адаптер не «погладит» биржу за N миллисекунд, биржа сама отменит все открытые ордера. Полезный safety net для kill switch при сетевом дисконнекте, не подменяет (но дополняет) клиентский kill switch.

### Klines (свечи)

- **REST V3:** `GET /openApi/swap/v3/quote/klines` — поля только `open/high/low/close/volume/time`. Параметры: `symbol`, `interval`, `startTime`, `endTime`, `timeZone` (0 или 8), `limit` (default 500, **max 1440**).
- **Квирк precision полей:** REST V3 не отдаёт `n` (число трейдов) и `q` (turnover/quote volume). Если они нужны для фич — берём через WS-канал `<symbol>@kline_<interval>`, который даёт полные поля (T/c/h/i/l/n/o/q/s/t/v).
- **Квирк формата интервала:** REST принимает `1m`, `15m`, `1h`, `1d`. WS-канал использует другую запись: `1min`, `5min`, `15min`, `1h`. Адаптер маппит обе формы внутри.
- **Бэктест-расчёт:** для 6 мес 15m свечей нужно ~17 500 баров → **13 чанков по 1440** (с пагинацией по `endTime`). При 500/10s глобальном лимите — спокойно укладываемся.

### Open Interest, Mark Price, Funding

- **OI:** `GET /openApi/swap/v2/quote/openInterest` (без подписи). Возвращает `openInterest` как строку.
- **Mark + Funding:** `GET /openApi/swap/v2/quote/premiumIndex` → `markPrice`, `indexPrice`, `lastFundingRate`, `nextFundingTime`, `fundingIntervalHours`, `minFundingRate`, `maxFundingRate`. Без подписи.
- **Funding history:** `GET /openApi/swap/v2/quote/fundingRate`, default 100, **max 1000**.

### WebSocket — общее

Источник: docs-v3 → USDT-M Perp Futures → секция «Connection Limitations / Access / Data Compression / Heartbeats / Subscriptions».

- **Сжатие:** все ответы сервера **gzip-сжаты**, клиент обязательно декомпрессит.
- **Heartbeat:** сервер шлёт **текстовое** `Ping` каждые 5 секунд (частота может меняться). Клиент обязан ответить текстовым `Pong`. **Это не JSON-payload** — это литерал.
- **Subscribe/Unsubscribe:**
  ```
  {"id":"<uuid>","reqType":"sub","dataType":"BTC-USDT@kline_1min"}
  {"id":"<uuid>","reqType":"unsub","dataType":"BTC-USDT@kline_1min"}
  ```
- **Подтверждение:** `{"id":"<uuid>","code":0,"msg":"SUCCESS","timestamp":<ms>}`.
- **Лимиты подключений (USDT-M perp swap):** до **200 топиков на одно соединение** (иначе error 80403); до **60 одновременных WS-соединений на IP** (по EN-доке). На ZH-странице в том же месте указано «240 websocket per IP» — **расхождение между EN и ZH версиями документации**, отмечаем явно. Использовать консервативную EN-цифру (60), пока не проверим integration-тестом.
- **Каналы public swap:**
  - `<symbol>@kline_<interval>` — свечи (`<interval>` = `1min`, `5min`, `15min`, `1h`, ...)
  - `<symbol>@trade` — публичные сделки
  - `<symbol>@ticker` — 24h ticker
  - `<symbol>@markPrice` — mark price
  - `<symbol>@depth<lvl>@<intervalMs>` — стакан (например `BTC-USDT@depth5@500ms`)

### User Data Stream (USDT-M perp)

Источник: docs-v3 → USDT-M Perp Futures → User Data Stream.

- **Получение listenKey:** `POST https://open-api.bingx.com/openApi/user/auth/userDataStream` (приватный, подписан).
- **TTL listenKey:** **1 час**, нужно периодически продлевать (renew). Если истёк — придётся выпустить новый и переподключиться.
- **Подключение:** `wss://open-api-swap.bingx.com/swap-market?listenKey=<KEY>`.
- **Поток событий:** **без явного subscribe** — сервер сам шлёт все типы пользовательских событий. Включает `ORDER_TRADE_UPDATE` (статусы ордера: NEW/PARTIALLY_FILLED/FILLED/CANCELED/EXPIRED, причины: NEW/CANCELED/CALCULATED/EXPIRED/TRADE), `ACCOUNT_UPDATE` (баланс + позиции). Тип `LIQUIDATION` (强平單) приходит как тип ордера в потоке `ORDER_TRADE_UPDATE`.

### VST (Virtual Simulated Trading) — testnet-эквивалент

- Отдельный домен: REST `https://open-api-vst.bingx.com`, WS `wss://vst-open-api-ws.bingx.com/swap-market`.
- Те же эндпоинты USDT-M perp, что и live.
- **Ключи отдельные** (заводятся в UI BingX «Demo Trading»), не пересекаются с live.
- **Пополнение баланса:** `POST /openApi/swap/v2/trade/getVst` (только VST). Лимит: 1 000 000 VST за запрос, 10 000 000 кумулятивно.
- **Подтверждено для USDT-M perp.** Coin-M / spot — не уточнено в docs, проверим integration-тестом в фазе 0.B (нам там не нужно, но полезно знать пределы).

## Чек-лист перед фазой 1 (live)

- [ ] Создан suborder API key с правами «Professional Futures Trading», **без вывода средств**.
- [ ] IP whitelist настроен на VPS.
- [ ] Telegram-алерты на критичные события подключены.
- [ ] Тестовый ордер на минимальном размере прошёл успешно (entry + attached SL + close).
- [ ] Position mode = one-way (`dualSidePosition=false`).
- [ ] Margin type = `ISOLATED`.
- [ ] Плечо на ползунке выставлено разумно (≤5x), но размер всё равно от риск-формулы.
- [ ] Sync серверного времени (offset < 1 сек) при старте подтверждён.
- [ ] Адаптер локально округляет price/qty по `pricePrecision`/`quantityPrecision` (защита от тихого усечения).

## История инцидентов BingX

(Заполняем, если что-то случается — отвалы API, проблемы с выводом, странные баги)

| Дата | Что произошло | Как обработали |
|---|---|---|
|  |  |  |

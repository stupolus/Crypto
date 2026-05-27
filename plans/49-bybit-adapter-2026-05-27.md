# План 49 — Bybit V5 адаптер (первичный)

**Стадия:** ПЕРВИЧНАЯ. Кода нет, до явного «да» владельца на фазу 49.0
ничего в `adapters/bybit/` не появляется.

**Дата:** 2026-05-27. **Источник:** решение владельца — «торговать
параллельно с BingX в зависимости от удобства и данных».

## Контекст и решение

CLAUDE.md: «Биржа №1 BingX, №2 Bybit (позже)». «Позже» наступило.
Уточнение владельца (2026-05-27): **Bybit — это и вторая точка
исполнения (demo + live, как BingX), И источник исторических
данных** для анализа/бэктеста, потому что BingX моложе и его
исторический массив (klines, депт-данные) короче. Сценарий «**данные
на Bybit, исполнение на BingX**» — отдельный класс использования:
сигнал считается на длинной истории Bybit, ордер ставится на
BingX-перпе.

Архитектура: адаптер Bybit V5 по образцу `adapters/bingx/`, стратегии
exchange-agnostic (`Strategy` protocol + `OrderRequest`). Цена
паритета: трейдер выбирает execution-биржу в конфиге, не в коде
стратегии.

**Что НЕ делаем в плане 49:**
- Не переписываем стратегии под Bybit (они exchange-agnostic уже —
  работают с `Strategy` protocol и `OrderRequest`).
- Не делаем «арбитраж BingX↔Bybit».
- Не торгуем live ни на одной бирже до прохождения testnet/demo
  цикла + явного «да» (то же правило, что для BingX-VST).

## Кросс-venue паттерн «данные Bybit → исполнение BingX»

Отдельная подзадача, **не** относящаяся к чисто-адаптерному коду:

1. **Symbol-маппинг между биржами.** На BingX `BTC-USDT`, на Bybit
   `BTCUSDT`. Для TradFi-перпов (NCSI..., NCCO...) — отдельная
   таблица соответствий (если такие же активы есть на Bybit). Решение:
   `core/data/cross_venue.py` (фаза 49.6).
2. **Price reference consistency.** При расчёте стопа/RiskEngine на
   данных Bybit нельзя использовать Bybit-цену напрямую — стоп
   ставится на BingX-перпе, цены могут расходиться. Подход — как уже
   работает в GTAA-executor: ratio-мэппинг (стоп Yahoo→BingX через
   close-ratio). Применить тот же приём для Bybit-данных.
3. **Backtest data-loader.** `core/backtest` сейчас читает Bybit-klines
   через CSV/parquet файлы. Добавить `BybitDataSource` — прямой
   pull из адаптера, без выгрузки в файлы. Это фаза 49.7.
4. **Live-режим (live signal + live execution на разных биржах) —
   запрещён** до явного «да» владельца + отдельного плана с
   обоснованием cost-model (cross-venue latency, slippage).

## Безопасность (ДО кода)

1. **Ключи владельца, присланные в чате 2026-05-27, скомпрометированы**
   (логи сессии). Владелец обязан их повернуть/удалить на bybit.com и
   не присылать в чат повторно.
2. Новый ключ:
   - **Permissions:** только Contract Trade. **БЕЗ Withdraw.**
   - **IP whitelist:** только VPS + (опц.) домашний IP.
   - В `/etc/crypto/.env` (chmod 600, owner root, не коммитить).
3. Адаптер читает ключи **только из env** через `BybitSettings`
   (по образцу `BingXSettings`). Hard-guard `env in {"testnet","live"}`,
   ничего иного.
4. **Live-режим запрещён до прохождения тестов 49.3 + явного «да»
   владельца.** Это hard-assert в коде, не комментарий.

## Цели адаптера

Полный паритет с тем, что используется на BingX:

| Возможность | BingX (есть) | Bybit (надо) | Phase |
|---|---|---|---|
| Public klines | `models.Kline` | то же | 49.1 |
| Public ticker / orderbook | есть | то же | 49.1 |
| Private balance | `get_balance()` | то же | 49.2 |
| Private positions | `get_positions(symbol)` | то же | 49.2 |
| place_order (MARKET/LIMIT) | + attached SL/TP | то же | 49.2 |
| close_position | hedge-aware | hedge-aware | 49.2 |
| cancel_order / cancel_all | есть | то же | 49.2 |
| WS user stream | есть | то же | 49.4 |
| Order journal | есть | переиспользовать | 49.2 |
| Hedge / one-way mode | поддержано | поддержать | 49.2 |

Не реализуем сразу (отдельные фазы или после явного решения):
- WS публичных стримов (наши стратегии работают на REST-klines).
- Funding/OI стримы (можно добавить позже, если стратегия требует).
- Margin transfer / sub-accounts.

## Bybit V5 квирки (что отличается от BingX)

Документация: <https://bybit-exchange.github.io/docs/v5/intro>.

| Аспект | BingX | Bybit V5 |
|---|---|---|
| Базовый URL live | `open-api.bingx.com` | `api.bybit.com` |
| Testnet URL | `open-api-vst.bingx.com` (VST=demo) | `api-testnet.bybit.com` |
| Подпись | HMAC-SHA256(`querystring`) | HMAC-SHA256(`timestamp+api_key+recv_window+queryStringOrBody`) |
| Timestamp header | `X-BX-APIKEY` + `signature` query | `X-BAPI-API-KEY`, `X-BAPI-SIGN`, `X-BAPI-TIMESTAMP`, `X-BAPI-RECV-WINDOW` |
| Symbol format | `BTC-USDT` (с дефисом) | `BTCUSDT` (без дефиса) |
| Category | один тип | `linear` / `inverse` / `spot` / `option` — нужно указывать в каждом запросе |
| Hedge/one-way | глобальный режим аккаунта | per-symbol через `positionIdx` (0=one-way, 1=long hedge, 2=short hedge) |
| Attached SL/TP | в place_order | в place_order (`stopLoss`/`takeProfit` поля) |
| ReduceOnly | флаг | флаг |
| Order ID | строка | строка (но Bybit отдаёт и `orderLinkId` — наш COID) |
| Rate limits | window + endpoint | per-UID + per-endpoint (отдельный лимит на place/cancel) |
| Demo trading | VST («virtual» аккаунт) | UTA Testnet (отдельный домен) |

**Главные ловушки** (будут разруливаться в фазах):
1. **Symbol mapping.** Наш проектный формат `BTC-USDT`, Bybit ждёт `BTCUSDT`. Делаем translator (как у BingX уже сделан для NCS*-перпов).
2. **`positionIdx`.** В hedge-режиме каждый ордер должен явно указывать `positionIdx` (1 или 2). Mirror фикса #164 #177 — но на уровне Bybit-адаптера. position_side из OrderRequest → positionIdx.
3. **`category`.** Каждый эндпоинт требует `category=linear` для USDT-перпов. Один параметр везде.
4. **Time-sync.** Bybit жёстко ругается на расхождение timestamp > recv_window. Аналог `time-sync` есть, надо повторить.
5. **Geoblock CloudFront.** Bybit (`api.bybit.com` и `api-testnet.bybit.com`)
   возвращает HTTP 403 с CloudFront-страницы из dev-окружения
   (проверено 2026-05-27). Это значит: **integration/smoke-тесты
   запускаются только на VPS** (Hostinger Asia) через Мануса, по
   образцу GTAA-smoke. Unit-тесты с `respx`-моками работают везде.

## 10 априорных причин провала

1. **API-документация Bybit меняется чаще, чем BingX** — нужны
   pin-версии endpoint-схем и тесты по факту, не по докам.
2. **`positionIdx` ≠ position_side BingX.** Если ошибиться в маппинге,
   повторим класс бага #164/#177 на новой бирже.
3. **Testnet поведение ≠ live** (как и с BingX VST): order fills, latency,
   liquidity отличаются — нельзя экстраполировать testnet-результаты
   как боевые. Demo проверяет ИСПОЛНЕНИЕ, не PnL (як з GTAA).
4. **Привычка к BingX-формату:** в стратегиях может остаться неявная
   зависимость от `BTC-USDT` формата. Symbol-translator должен быть на
   уровне адаптера, не стратегии.
5. **Rate-limit пере-вызовы:** Bybit лимиты строже на place/cancel —
   bursty стратегии могут упереться.
6. **WS-аутентификация Bybit:** auth-пакет другой, чем у BingX. WS-юнит
   надо тестировать отдельно (фаза 49.4).
7. **Hedge mode default ≠ ожиданию:** Bybit может быть в one-way по
   умолчанию, наша логика «всё в hedge» сломается. Адаптер должен
   уметь оба + ассертить совпадение при старте.
8. **Stop-orders attached vs separate:** Bybit поддерживает оба пути,
   надо выбрать ОДИН и придерживаться (как у BingX — attached в place_order).
9. **Order ID type:** Bybit отдаёт `orderId` строкой. Не int. Mirror
   BingX-фикса по str-кастингу.
10. **«Демо» аккаунт может быть инициализирован пустым** — testnet
    USDT не выдаются автоматически, нужен faucet-вызов или ручное
    пополнение. Решить до фазы 49.3.

## Фазы (НЕ выполнять до явного «да» владельца на фазу)

### 49.0 — Сборка контекста + критерии приёмки (DOC-ONLY)
- Дочитать V5-доки: place_order, position, balance, WS auth.
- Записать в этот файл: критерии приёмки = «smoke на testnet ставит
  ордер с SL, видит его в positions, закрывает» — паритет с тем, что
  доказывает наш `gtaa_vst_executor --check`.
- Сохранить ссылки на эндпоинты + версии докум.

### 49.1 — Public + settings + signing (PR #1)
- `adapters/bybit/__init__.py`, `client.py`, `models.py`, `settings.py`,
  `signing.py`.
- `BybitSettings(env: Literal["testnet","live"], api_key, api_secret, recv_window_ms)`.
- HTTP client с time-sync, retry, exp-backoff.
- Public klines + ticker (нужны для backtest-ового data-loader'а).
- Symbol translator: `BTC-USDT` ↔ `BTCUSDT`.
- Unit-тесты: signing-вектор из доков, parse моделей.
- Гейт: mypy strict + pytest.

### 49.2 — Private API (PR #2)
- `private.py`, `private_models.py`, `journal.py` (reuse — он общий уже).
- `OrderRequest` mapping: `position_side` LONG/SHORT/BOTH → `positionIdx` 1/2/0; `side` BUY/SELL → Bybit `Buy/Sell`.
- `get_balance`, `get_positions`, `place_order` (с attached SL/TP),
  `close_position` (hedge-aware), `cancel_order`, `cancel_all`.
- Compensating-close при отсутствующем SL в ack (как у BingX).
- Unit-тесты с respx-моками.
- Гейт: mypy strict + pytest.

### 49.3 — Testnet smoke (PR #3)
- Integration-тесты в `adapters/bybit/tests/test_int_*.py`,
  skip без `BYBIT_ENV=testnet` и ключей.
- Smoke-сценарий: place LONG market с SL → check positions → close →
  идемпотентный повтор → noop.
- Документировать в README: как получить testnet-USDT.

### 49.4 — WS user stream (PR #4) — опционально
- Подключение WS, авторизация, обработка `order`/`position` событий.
- Юнит на парсинг сообщений + integration на testnet.

### 49.5 — Production hardening (PR #5) — после ≥4 недель testnet
- Live-guard снимается отдельным коммитом.
- Phase 0.D из BingX-плана (dead-man timer, kill-switch файл) — переносим.

### 49.6 — Cross-venue (PR #6) — приоритет владельца 2026-05-27
- `core/data/cross_venue.py`: маппинг `BTC-USDT` ↔ `BTCUSDT` +
  таблица соответствий для TradFi-перпов (где совпадают).
- Утилита `cross_venue_price_ratio(bybit_close, bingx_close)` для
  переноса стоп-уровней между биржами (по образцу того, как
  GTAA-executor переносит SMA200 с Yahoo-индекса на BingX-перп).
- Unit-тесты: символы есть/нет, ratio sanity.

### 49.7 — Bybit как data-source для бэктеста (PR #7) — приоритет
- `core/backtest/datasource/bybit.py`: `BybitDataSource` —
  использует public klines из адаптера (фаза 49.1) для длинной
  истории, дольше чем BingX.
- Подключение в `scripts/run_backtest.py` опцией `--data-source bybit`.
- Бэктест-прогон любой существующей стратегии на Bybit-данных
  vs BingX-данных → diff (для сверки, что edge консистентен на длинной
  истории).

## Жёсткие стопы

- Каждая фаза = отдельный PR. Не сливать несколько фаз в один.
- Live-торговля: hard-assert `settings.env == "testnet"` до явного снятия.
- Bybit-ключи **только из env**, никаких хардкодов / тест-фикстур.
- Если на любой фазе Bybit API ведёт себя не как в доках — **остановиться,
  зафиксировать квирк в этом плане, спросить владельца**, не выдумывать
  обходных путей (правило заведено по факту работы с BingX VST).
- Параметры risk-engine FIXED — не подстраивать под Bybit (одинаковая
  политика на обеих биржах).

## Что нужно от владельца, чтобы начать 49.0

1. **Повернуть ключ** из чата (старый удалить на bybit.com).
2. **Новый ключ — без withdraw, с IP whitelist.** Владелец хочет и demo,
   и live (см. контекст). Решение: **два отдельных ключа**:
   - `BYBIT_TESTNET_API_KEY` — на api-testnet.bybit.com (для фаз 49.1–49.3).
   - `BYBIT_LIVE_API_KEY` — на api.bybit.com, **read-only пока** (для
     фаз 49.6–49.7 — data-source для анализа без риска ордера; в коде
     `live` режим до фазы 49.5 hard-блокирован для торговли). На trade
     перевести только когда фаза 49.5 будет завершена + явное «да».
3. **Положить ключи в `/etc/crypto/.env` через Мануса** на VPS (или в
   локальный `.env`), переменные:
   ```
   BYBIT_ENV=testnet          # переключатель текущего режима
   BYBIT_TESTNET_API_KEY=...
   BYBIT_TESTNET_API_SECRET=...
   BYBIT_LIVE_API_KEY=...     # read-only до фазы 49.5
   BYBIT_LIVE_API_SECRET=...
   BYBIT_RECV_WINDOW_MS=5000
   ```
4. **Явное «начинай фазу 49.0»** в чате — после этого я двигаюсь
   по фазам, каждая = PR.

До этих 4 пунктов — кода в `adapters/bybit/` нет.

# 06 — Paper-runner (живые котировки, виртуальное исполнение)

Дата: 2026-05-22
Статус: первичный, готов к реализации

## Цель

Запустить стратегию `mean_reversion_vwap` на **живых закрытых свечах**
с BingX/Bybit (без выставления реальных ордеров), вести журнал сделок в
SQLite, считать эквити, рапортовать в лог и (опционально) в Telegram.

Это фаза 1 из `risk-profile.md` («Paper / testnet», активный банк $0).
Без paper-runner'а нет фазы 1 → нет фазы 2 → нет live. Это обязательный
этап в master-плане (Шаг 06).

## Гипотеза edge'а

Та же, что в плане 05 (mean-reversion у VWAP±ATR). Paper-runner не
ищет новый edge — он проверяет, что бэктест-метрики **повторяются на
живом потоке свечей и cost-модели**: реальные комиссии, реальные
открытия следующих 15m, реальные high/low.

## Метод проверки

- Запуск ≥ 4 календарные недели по PAXG/USDT:USDT и XAUT/USDT:USDT (BingX,
  продакшн-данные; режим VST не нужен — котировки публичны).
- Каждую сделку — в SQLite (entry/exit/qty/PnL/exit_reason/equity).
- Ежедневный отчёт в лог: trades, winrate, PF, day_pnl, equity. Если
  Telegram-токен есть — туда же.
- По итогам — отдельный файл в `journal/backtests/` или `journal/paper-<symbol>-<dates>.md`
  с сравнением «бэктест vs paper»: разница в PF, expectancy, max DD.

## Архитектура (изолированный пакет `gold-bot/paper/`)

```
paper/
├── __init__.py
├── feed.py        # PaperFeed: опрос fetch_ohlcv, выдача только закрытых свечей
├── journal.py     # SQLite журнал: trades, equity-snapshots
├── engine.py      # PaperEngine: применяет стратегию + RiskEngine, симулирует fills
├── reporter.py    # Telegram-нотификатор (env-gated, no-op если токена нет)
├── runner.py      # PaperRunner: оркестратор — подписывает feed → engine → journal/reporter
└── tests/         # unit-тесты на feed/engine/journal
```

CLI: `scripts/run_paper.py --exchange bingx --symbols PAXG/USDT:USDT,XAUT/USDT:USDT --timeframe 15m`.

Конфиг: `config/paper.yaml` (символы по умолчанию, период опроса, путь к SQLite,
параметры cost-модели для paper). Числа риска — из `config/risk.yaml` (источник
единственный).

## Ключевые инварианты

1. **Никаких реальных ордеров.** Адаптер используется только для `fetch_markets`
   и `fetch_ohlcv`. Методы `place_order` / `cancel_order` / `fetch_positions`
   в paper-runner'е не вызываются (на уровне кода).
2. **Решения принимаются только по закрытым свечам.** Текущая (незакрытая)
   свеча игнорируется. PaperFeed сравнивает `candle.timestamp + tf_ms` с now()
   и выдаёт свечу только когда она гарантированно закрыта.
3. **Lookahead-bias невозможен.** Вход — по open следующей свечи (как в
   бэктестере). Стоп/тейк — по high/low следующей свечи. Это тот же контракт,
   что в `backtest.engine`.
4. **RiskEngine — единственный источник правды по сайзингу.** Никакого
   «paper-сайзинга» в обход (CLAUDE.md §13).
5. **Стоп = часть входа.** Если RiskEngine не одобрил вход (нет стопа /
   слишком близкий стоп / плечо / cost-edge / spread / circuit breaker) —
   сделки нет.
6. **Состояние переживает рестарт.** Open position, equity, last-seen
   candle ts по символу — всё в SQLite. При старте PaperRunner подтягивает
   состояние, и сделки не дублируются.
7. **Никаких секретов в коде/конфиге.** Telegram-токен/chat-id — из env,
   опциональные (если нет — Telegram-нотификатор не активируется, лог
   остаётся).

## Cost-модель paper

Та же `backtest.costs.CostModel`. Значения по умолчанию — из
`config/paper.yaml` (taker_fee, slippage_pct), не из памяти. После первой
недели paper-наблюдения — калибровка `slippage_pct` по факт. разнице
(open_next vs ожидаемая цена).

## Состояние и журнал в SQLite

Таблицы:
- `trades` — entry_ts, exit_ts, symbol, side, entry_price, exit_price, qty,
  gross_pnl, costs, net_pnl, exit_reason, equity_after.
- `equity_points` — ts, equity (после каждой закрытой сделки).
- `runner_state` — key/value: `last_candle_ts:<symbol>`, `open_position:<symbol>` (JSON).
- `daily_summary` — date (UTC), trades, gross_pnl, costs, net_pnl, max_dd_today.

SQLite — один файл, путь из `paper.yaml`. На VPS лежит вне `gold-bot/`
(в `/var/lib/gold-bot/paper.sqlite`), чтобы переживать обновления кода.

## Telegram-нотификатор

Опционален. Env: `GOLDBOT_TG_TOKEN`, `GOLDBOT_TG_CHAT_ID`. Если оба заданы —
по умолчанию шлёт:
- сообщение при старте/остановке runner'а;
- ежедневное summary (00:00 UTC): сделки, winrate, PF за день, day_pnl,
  equity, статус circuit breakers;
- алерт при срабатывании kill-switch / dailystop / consecutive_losses.

Если хотя бы одной переменной нет — модуль no-op, runner идёт в лог.

## Фазы реализации

1. **06A — feed + journal + engine.** PaperFeed, SQLite журнал, PaperEngine.
   Тесты на синтетике без сети: feed эмитит «закрытую» свечу когда
   currentTime ≥ candleClose + tf; engine открывает/закрывает по стопу.
2. **06B — runner + reporter + CLI.** Оркестратор + Telegram (тестируется на
   моке HTTP — без сетевых вызовов). Скрипт `scripts/run_paper.py`.
3. **06C — конфиг paper.yaml + journal/.md.** Конфиг с дефолтами,
   шаблон ежедневного отчёта.

После каждой фазы — `pytest`, `ruff`, `mypy --strict` зелёные, коммит.

## 10 причин почему может не получиться

1. **BingX не отдаёт «честно закрытые» 15m в реальном времени.** Свеча
   c.timestamp+tf_ms < now не гарантирует, что биржа считает её закрытой.
   Решение: буфер `close_grace_ms` (например 5 сек) в конфиге.
2. **Поток свечей с разрывами.** Если poll пропустил окно — придётся
   догонять с last_candle_ts. PaperFeed обязан дозапросить пропущенные.
3. **Time-drift VPS vs биржа.** Если часы VPS «убежали», свеча кажется
   закрытой раньше времени → ложные сигналы. Решение: NTP на VPS (вне
   gold-bot), плюс сверка `ticker.timestamp` с локальным `time()`.
4. **Бэктест-fill vs paper-fill отличаются больше, чем покрывает slippage.**
   Это и есть смысл paper-наблюдения. Запишем разницу, не «подкрутим» её.
5. **Краш runner'а между «открытие позиции» и «коммит в SQLite».**
   Решение: открываем транзакцию `BEGIN…COMMIT` вокруг каждого решения,
   восстанавливаем `open_position` на старте.
6. **Концерн «runner работает, но не торгует»** — может быть нормой
   (стратегия по логике, ничего не открыла). Reporter обязан отличать
   «нет сделок» от «runner упал»: heartbeat в `runner_state` каждые N минут.
7. **Telegram rate-limit.** Один алерт может улететь дублями при retry.
   Решение: debounce по ключу события + max 30 сообщений/час.
8. **Утечка секретов в логи.** Telegram-токен может попасть в трассу
   ошибки HTTP-библиотеки. Маскируем токен в любых строках, прежде
   чем писать в лог (есть `exchanges.logging_utils`).
9. **Сеть VPS — провал >30 сек.** В risk-profile.md по этому случаю —
   закрытие позиций рыночным. В paper «закрытие рыночным» = виртуальное
   закрытие по последней известной цене + флаг `network_outage`.
10. **Дрейф конфига между бэктестом и paper.** Решение: paper-runner
    при старте логирует git rev + хэши `risk.yaml` + `mean_reversion_vwap/config.yaml`.

## Критерии приёмки

- Юнит-тесты paper-пакета зелёные (≥ 10 тестов).
- `ruff` + `ruff format` + `mypy --strict` чисто.
- `scripts/run_paper.py --dry-run` (одна итерация на синтетических свечах) проходит локально.
- Документация в `journal/2026-05-23-paper-runner-start.md` — что запущено,
  где SQLite, как остановить, как читать журнал.

## Что не делаем в этом плане (отложено)

- Реальные ордера. Перенесено в план 07 (live-runner), который пишется
  только после успешных 4 недель paper.
- Multi-strategy оркестрация / challenger-кандидаты. Перенесено в план 08
  (champion-challenger), пишется после первого месяца paper.
- WebSocket-фид. На 15m таймфрейме polling fetch_ohlcv каждые 30–60 сек
  более чем достаточен; WS добавит сложности и багов без выигрыша.

## Зависимости

- План 01 (адаптер ccxt) — есть.
- План 02 (data layer) — есть.
- План 03 (RiskEngine) — есть.
- План 04 (backtest engine) — есть (CostModel, контракт fill переиспользуем).
- План 05 (стратегия) — есть.

## История

| Дата | Изменение |
|---|---|
| 2026-05-22 | Создан план. |

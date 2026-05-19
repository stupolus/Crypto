# План 34 — composite: live Coinglass-обвязка (фаза перед демо)

## Дата: 2026-05-18 · База: планы 31-33, core/signals/live_providers.py

## Контекст / честный статус

composite в `live_runner` = безопасный **no-op**: Static-провайдеры
пусты → сигналов нет → не торгует. Live Coinglass-обвязка
(liq/funding/CVD) **не построена нигде** (`live_providers.py`:
«Coinglass-обёртка для ликвидаций — отдельная задача, ждёт API-ключ»;
`llm_runner` её тоже не подключает). Есть только
`RollingOpenInterestProvider` (поллит BingX OI вживую).

⇒ Деплой composite на ВПС СЕЙЧАС бессмыслен — он ничего не делает.
Эта фаза нужна, но строго ПОСЛЕ прохождения backfill-критерия
(план 33): нет смысла строить live-обвязку для стратегии без
доказанного edge.

## Жёсткая последовательность (не нарушать)

1. **Гейт:** `composite_backtest` ETH+BTC (env с COINGLASS_API_KEY) →
   критерий iter#4 (PF>1.5 И PnL>+2% И OOS+≥2/3). НЕ прошёл → стоп,
   эта фаза не делается.
2. Прошёл → реализовать live-обвязку (ниже).
3. Forward-test на демо (pre-registered, план 31).

## Объём фазы (когда гейт пройден)

### 34.1 — live Coinglass-провайдеры
`core/signals/live_providers.py`:
- `CoinglassLiveLiquidationProvider` — обёртка `CoinglassClient
  .get_liquidation_history` на скользящем окне (последние N интервалов),
  `get_bucket`/`get_baseline` по протоколу `LiquidationProvider`.
- `CoinglassLiveFundingProvider` — `get_funding_history` rolling →
  `get_funding_rate(symbol, ts)` (anti-look-ahead, как
  `TsFundingProvider` из `scripts/composite_backtest`).
- OI — переиспользовать `RollingOpenInterestProvider` (BingX) ИЛИ
  Coinglass OI (решить по доступности интервала).
- Unit-тесты на fake `CoinglassClient` (DI, без сети/ключа) — как у
  `backfill`/`composite_backtest`.

### 34.2 — wiring в live_runner
`_build_strategy("composite_signal")`: если `COINGLASS_API_KEY` есть —
собрать live-провайдеры и передать в `CompositeSignalStrategy`; иначе
оставить no-op (без падения). Лог-строка о режиме.

### 34.3 — деплой
`docker-compose.composite.yml` (готов, план 33) + `/etc/crypto/.env`
с `COINGLASS_API_KEY`. `up -d`, наблюдать по pre-registered дизайну,
kill-критерий жёсткий.

## Статус (2026-05-18) — ВЫПОЛНЕНО (код), демо за воротами

34.1 `parsers/coinglass/live_providers.py` (4 провайдера + time-кэш от
429 + `build_live_providers`) + 4 теста на fake-клиенте. 34.2
`live_runner._build_strategy`: ключ+symbol+маппинг → live-провайдеры,
иначе безопасный no-op (D3 не задет). `config-4h-demo.yaml` (тариф
даёт ≥4h). Гейты: 665 тестов зелёные, ruff/mypy strict чисто.
Деплой (34.3) — на VPS, ПОСЛЕ backfill-критерия (план 33), не отсюда.

## Definition of Done
- Гейт пройден ДО начала 34.1 (иначе фаза не делается).
- live-провайдеры + тесты на fake-клиенте; ruff/mypy strict; pytest -q.
- live_runner: key → live, нет ключа → no-op (без регрессий D3).
- Прод `core/risk/config.yaml` не тронут. Демо — только после 34.2.

## Блокер
Всё за `COINGLASS_API_KEY`, которого нет в cloud-сессии. Гейт (шаг 1) и
эта фаза исполняются в окружении с ключом (ВПС/локально).

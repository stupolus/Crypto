# План 19 — Asset-specific стратегии (Gold / Oil / Stock)

## Дата: 2026-05-15

## Цель

Расширить strategy-портфолио тремя asset-specific вариантами Donchian breakout
для покрытия портфельной диверсификации:

1. **GoldSafetyHaven** (XAU-USDT) — safe-haven trend, LONG-only, slower Donchian.
2. **OilEiaAvoid** (CL-USDT) — WTI crude, both-sided, news-pause вокруг EIA.
3. **StockEarningsAvoid** (TSLA / NVDA -USDT) — equity perp, both-sided,
   blackout вокруг earnings + строго US session.

## Принцип реализации

Архитектура `BtcBreakoutStrategy` уже generic (Donchian + ATR + volume +
composite). Не переписываем, **обобщаем через config**:

1. Расширяем `StrategyConfig` опцией `direction_bias: Literal["both",
   "long_only", "short_only"]` (default "both" → backward-compatible).
2. Расширяем `BtcBreakoutStrategy` для уважения bias (early-return до
   ATR/volume фильтра).
3. Каждая новая стратегия — отдельный package с собственным YAML и thin
   wrapper class (или прямо `BtcBreakoutStrategy` с разным config).

### Почему не один монолит

`gold_safety_haven` / `oil_eia_avoid` / `stock_earnings_avoid` отдельные
**packages** (с собственным `__init__.py` + config.py + config.yaml + tests).
Имена дают понятную семантику. Live-runner подключает каждую отдельно,
если ассет активен.

## Параметры (обоснование)

### Gold (XAU-USDT, 1h timeframe)

| Параметр | Значение | Обоснование |
|---------|----------|-------------|
| timeframe | 1h | Gold — slower asset, 15m шум доминирует |
| donchian_n | 50 | ~2 суток на 1h, фильтрует micro-noise |
| atr_window | 14 | Стандарт Wilder |
| atr_percentile_min | 0.6 | Чуть выше чем BTC — gold ралли требуют impulse |
| volume_multiplier | 1.3 | Ниже чем BTC (1.5) — gold-volume less spiky |
| direction_bias | long_only | Safe-haven asymmetry: shorts gold = шорт страха |
| stop_min_pct | 0.4 | Gold менее волатилен — узкий стоп OK |
| tp1_r_multiple | 2.0 | Длиннее target — gold trends длиннее |
| risk_tier | B | 1% базовый |

### Oil (CL-USDT, 15m, **EIA blackout**)

| Параметр | Значение | Обоснование |
|---------|----------|-------------|
| timeframe | 15m | Crude волатилен, intraday breakouts работают |
| donchian_n | 20 | Как BTC |
| direction_bias | both | Oil симметричен (нет haven bias) |
| stop_min_pct | 0.5 | Стандарт |
| tp1_r_multiple | 1.5 | Стандарт |
| news_pause_eia | true | News calendar блокирует ±15 мин до EIA (Ср 14:30 UTC) |
| risk_tier | B | 1% |

EIA blackout реализуется через расширение `NewsCalendar` provider
(уже DI'нут в strategy) — добавляем weekly EIA recurring event.

### Stock (TSLA / NVDA -USDT, 15m, **earnings blackout + US session**)

| Параметр | Значение | Обоснование |
|---------|----------|-------------|
| timeframe | 15m | Stock perp = intraday |
| donchian_n | 16 | 4 часа на 15m — узкая US-session-relevant |
| direction_bias | both | Stocks обоюдны |
| stop_min_pct | 0.6 | Stocks gap-risk → шире стоп |
| tp1_r_multiple | 1.5 | Стандарт |
| earnings_blackout_days | 2 | ±2 дня вокруг earnings — критично! |
| session | us_market_hours | Строго 13:30-20:00 UTC Mon-Fri |
| risk_tier | B | 1% |

Earnings blackout — отдельный provider `EarningsCalendar`, dependency-injected.

## Фазы

### Phase 1 — Gold (этот PR)
- [x] Plan (этот файл)
- [ ] StrategyConfig.direction_bias
- [ ] BtcBreakoutStrategy уважает direction_bias
- [ ] `strategies/gold_safety_haven/` package (config + YAML + thin re-export)
- [ ] Unit tests
- [ ] CI green
- [ ] PR

### Phase 2 — Oil (следующий PR)
- [ ] EIA news calendar (recurring weekly event)
- [ ] `strategies/oil_eia_avoid/`
- [ ] Tests (включая EIA pause)
- [ ] PR

### Phase 3 — Stock (третий PR)
- [ ] EarningsCalendar provider (stub или real via API)
- [ ] `strategies/stock_earnings_avoid/`
- [ ] Tests (earnings + session)
- [ ] PR

### Phase 4 — Live wiring (после успешного backtest всех 3)
- [ ] Расширить llm_runner / live_runner для запуска N strategies параллельно
- [ ] Корреляционная проверка (макс 1 позиция на коррелированную группу)

## 10 причин провала

1. Gold-long-only пропустит downtrends → меньше сделок, но меньше DD.
2. Donchian 50 на 1h = ~10-15 сетапов в год — мало для статистики. Решение:
   проверять на 5+ лет истории до live.
3. EIA timing != фиксированный — иногда releases переносят. Решение:
   полагаться на actual API, не на hardcoded cron.
4. Earnings calendar: stub'ы будут falsy. Решение: на live используем реальный
   provider (Finnhub / Polygon), на backtest — manual list.
5. XAU-USDT может не быть liquid'ным на BingX VST. Решение: проверить
   через `/api/symbols` до запуска.
6. Stock perp: после-hours pricing wonky. Решение: строгая session check.
7. ATR percentile lookback 200 на 1h = ~8 дней — слишком короткий. Решение:
   увеличить до 500 для gold.
8. Risk corr: gold long + stock long могут быть anti-correlated (risk-on/off).
   Решение: на этапе portfolio добавим corr matrix.
9. Funding rate на gold/stock perp может работать иначе. Решение: проверим
   формат BingX-ответа, при необходимости — skip funding-check для не-крипты.
10. Slippage на low-liquidity perps выше → R-multiple на TP1 надо тестировать.
    Решение: в backtest добавим slippage = 5 bps для не-крипты (vs 1 bps крипта).

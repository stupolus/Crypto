# План 14 — Volatility breakout на US session open

**Дата:** 2026-05-11
**Статус:** актуальный — план + реализация в той же сессии
**Связано:** [[plans/13-стратегия-выбор-3]] (вариант B), [[plans/02-btc-breakout-backtest]]

---

## 1. Контекст

Donchian breakout 15m+1h опровергнут. Текущая идея — стратегия с **time-of-day фильтром**: торгуем только на открытии US session (13:00-15:00 UTC), когда крипта часто получает impulse moves из-за подключения американских участников.

## 2. Идея

**Asian range breakout:**
- Считаем диапазон Asian session: высокий и низкий за 00:00-13:00 UTC.
- В US window (13:00-15:00 UTC) ждём пробоя Asian range.
- Вход: LONG если `close > asian_high`. SHORT если `close < asian_low`.
- SL: на противоположный конец Asian range.
- TP: 1.5R.

**Time windows (UTC):**
- 00:00-13:00 UTC — Asian range collection (13 часов).
- 13:00-15:00 UTC — US window для пробоя (2 часа).
- 15:00-00:00 UTC — off (если позиция открыта — продолжаем до SL/TP/end-of-day).

**End-of-day:** в 23:55 UTC закрываем все открытые позиции рыночным (защита от ночных news / разрывов до следующей Asian session).

## 3. Гипотеза

На крипте US session start даёт самый сильный statistical move дня. Стратегия с time фильтром = меньше false signals, больше hit rate на качественных пробоях.

## 4. Спецификация

### 4.1 Конфиг (`config.yaml`)

| Параметр | Значение | Обоснование |
|---|---|---|
| symbol | BTC-USDT | фаза 1 mainstream |
| timeframe | 15m | компромисс reaction vs noise |
| asian_start_hour_utc | 0 | midnight UTC |
| asian_end_hour_utc | 13 | до пика US open |
| us_start_hour_utc | 13 | NYSE open ≈ 13:30-14:00 |
| us_end_hour_utc | 15 | окно пробоя |
| eod_close_hour_utc | 23 | EOD close |
| min_range_pct | 0.5 | Asian range >= 0.5% от midpoint (иначе пропускаем — flat day) |
| max_range_pct | 5.0 | Asian range <= 5% (иначе уже большая волатильность — breakout less reliable) |
| stop_min_pct | 0.5 | как в риск-профиле |
| tp1_r_multiple | 1.5 | как в риск-профиле |
| risk_tier | B | 1% риск |

### 4.2 State machine

```
WAITING_ASIAN_DAY_START → ACCUMULATING_RANGE → US_WINDOW → 
  ↓                          ↓                    ↓
  noop                       обновляем H/L       проверяем пробой
                                                  ↓
                                                  если signal → PENDING → OPEN
                                                                          ↓
                                                                          SL/TP или EOD close
```

Каждый день в `00:00 UTC` state machine сбрасывается.

### 4.3 Алгоритм `on_candle_close`

```python
1. Если open_position → проверяем EOD close (>= eod_close_hour).
   Иначе noop (SL/TP управляет backtester / адаптер).
2. Получаем utc_hour, utc_day из candle.open_time_ms.
3. Если utc_day != current_day → reset Asian range, state.
4. Если utc_hour < asian_end_hour:
   - Обновляем asian_high = max(asian_high, candle.high).
   - Обновляем asian_low = min(asian_low, candle.low).
   - noop (нет сигнала).
5. Если asian_end_hour <= utc_hour < us_end_hour AND asian_range_complete:
   - asian_range_pct = (asian_high - asian_low) / midpoint * 100.
   - Если asian_range_pct < min_range_pct → skip day (flat day).
   - Если asian_range_pct > max_range_pct → skip day (already volatile).
   - LONG: candle.close > asian_high → signal.
     - entry = candle.close, stop = asian_low, tp = entry + 1.5 * (entry - stop).
   - SHORT: candle.close < asian_low → signal.
     - entry = candle.close, stop = asian_high, tp = entry - 1.5 * (stop - entry).
   - Если уже сгенерировали signal сегодня → skip.
6. Иначе noop.
```

### 4.4 RiskEngine integration

Та же логика что в `BtcBreakoutStrategy`: формируем `RiskInputs`, проверяем `RiskApproval`, если ok — собираем `OrderRequest` с attached SL/TP.

### 4.5 Composite filters

На MVP — только blacklist + news pause (как в BTC breakout). Funding не критично для time-of-day стратегии.

### 4.6 Реализация

- `core/signals/session.py` — функции:
  - `utc_hour_of_day(timestamp_ms) -> int`.
  - `utc_day_of_epoch(timestamp_ms) -> int`.
  - `is_in_session(timestamp_ms, start_hour, end_hour) -> bool`.
- `strategies/us_session_breakout/strategy.py` — `UsSessionBreakoutStrategy`.
- Тот же `Strategy` protocol → совместима с BacktestEngine.

## 5. Гейты решения

| Критерий | Цель | Логика |
|---|---|---|
| IS PF | ≥ 1.3 на всех 3 символах | Минимальный edge |
| OOS PF | ≥ 1.0 на всех 3 символах | Не убыток в OOS |
| Trade count IS+OOS | ≥ 30 на каждом символе | Ожидаем 1 trade в 1-3 дня = ~60-180 trades за 6 мес |
| Max drawdown | < 15% в обоих окнах | Risk control |

Если все пройдены → **go на demo (VST)**. Если IS красивые цифры, OOS нет — **overfit, бросаем**.

## 6. Чек-лист

- [ ] `core/signals/session.py` + tests.
- [ ] `strategies/us_session_breakout/strategy.py` + `config.py` + `config.yaml` + tests.
- [ ] Прогон на BTC/ETH/SOL 15m с IS+OOS split (0.5).
- [ ] Обновить `plans/02-btc-breakout-backtest.md` (или новый файл) с итерацией 3.
- [ ] Решение go/no-go.
- [ ] PR + авто-мерж.

## 7. Резюме

**Что было:** Donchian опровергнут. Нужна новая идея с другим edge mechanism.

**Что будет:** time-of-day breakout с фильтром Asian range. Микроструктурный edge известен на форексе, проверим на крипте.

**Какую проблему решает:** даёт **новый угол** на проблему — не trigger filtering (которое не работало), а **selective entry времени**. Это другая категория стратегий.

**Запреты:** подгонка `asian_end_hour` или `min_range_pct` под результат. Параметры выбираются ДО прогона из микроструктуры рынка (NYSE open 14:30 UTC = смешение с 13:30 cash в зимнее время).

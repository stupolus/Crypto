# План 15 — Trend following EMA cross 4h

**Дата:** 2026-05-11
**Статус:** актуальный — план + реализация в той же сессии
**Связано:** [[plans/13-стратегия-выбор-3]] (вариант C), [[plans/02-btc-breakout-backtest]]

---

## 1. Контекст

3 итерации breakout-стратегий опровергнуты (Donchian 15m, Donchian 1h, US session). Все опираются на «прорыв уровня» как triggers. Может быть **прорывы на crypto-perp = stop-hunt**, а реальный edge в другой логике.

**Trend following** — другая категория: ждём подтверждённый тренд (EMA cross + ATR), входим по pullback, идём за движением до разворота. Тестируем на 4h — реже шумов.

## 2. Идея

**EMA(20) cross EMA(50) на 4h:**
- `EMA(20) > EMA(50)` → long bias (восходящий тренд).
- `EMA(20) < EMA(50)` → short bias.
- Вход не по cross'у, а по **pullback** к EMA(20):
  - LONG в long bias: после касания EMA(20) и закрытия выше неё → BUY.
  - SHORT в short bias: после касания EMA(20) и закрытия ниже → SELL.
- SL: ATR × 1.5 от entry в обратную сторону.
- TP1: 1.5R (стандарт).

## 3. Параметры (зафиксированы ДО прогона)

| Параметр | Значение | Обоснование |
|---|---|---|
| TF | 4h | Стандарт trend following на крипте |
| EMA fast | 20 | Классика (20 SMA → 20 EMA) |
| EMA slow | 50 | Классика (50 SMA — long-term trend) |
| ATR window | 14 | Wilder |
| SL ATR multiplier | 1.5 | Стандарт ATR-based stop |
| Pullback EMA touch | EMA(20) | Та же, что fast |
| TP1 R multiple | 1.5 | Стандарт |
| Min EMA spread % | 0.2 | EMA20-EMA50 minimum spread, иначе тренд слабый |
| Stop min % | 0.5 | Из риск-профиля |
| Risk tier | B | 1% риск |

**Сознательно не используем:** percentile-фильтры, volume-фильтры (что давало false-edge раньше). Только тренд + ATR.

## 4. Гейты решения

Те же что в плане 12 §3:
- IS PF ≥ 1.3 на всех 3 символах.
- OOS PF ≥ 1.0 на всех 3 символах.
- Trade count ≥ 10 за 3 мес (на 4h частота низкая).
- Max drawdown < 15%.

**Это последняя итерация.** Если провал — идём на D3/D4.

## 5. Чек-лист

- [ ] `strategies/trend_ema_4h/` (config + strategy).
- [ ] Скачать BTC/ETH/SOL 4h × 6 мес.
- [ ] IS+OOS прогон на 3 символах.
- [ ] Обновить `plans/02-btc-breakout-backtest.md` итерацией 4.
- [ ] Решение go/no-go.
- [ ] PR + авто-мерж.

## 6. Резюме

**Что было:** 3 итерации breakout опровергнуты — простой «прорыв» edge не работает на крипте.

**Что будет:** другая категория (trend following) на крупном TF (4h). Это последняя попытка простого rule-based подхода.

**Запреты:** подгонять EMA periods под результат.

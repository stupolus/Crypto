# План 27 — daily-equity стратегия: trend_ema на акциях/индексах

## Дата: 2026-05-18 · База: план 26 + retro 2026-05-18, retro iter#3 (2026-05-12)

## Зачем

План 26: btc_breakout структурно не для daily equities. Нужна
purpose-built daily-стратегия. **Решение — не писать новую с нуля, а
переиспользовать `trend_ema_4h`:**

- `timeframe` Literal уже включает `1d` — код не трогаем.
- Warmup `max(ema_slow, atr_window+1)+2 ≈ 52` бара ≪ годового OOS-окна
  (в плане 26 btc_breakout валился именно на warmup 201 > OOS 90).
- Логика — настоящее трендследование (EMA20/50 + spread + pullback).
  Retro iter#3 сам зафиксировал: trend-following архитектурно НЕ для
  чопной крипты, но **дневные equity-индексы — каноничный дом
  трендследования**. Это честная проверка гипотезы, а не ретрофит.
- Уже зашит в `walk_forward.py`/`run_backtest.py`, есть тесты,
  реализует Strategy protocol.

**Нового кода в денежном пути — ноль.** Только config + дата-тулинг.

## Статус (2026-05-18) — ВЫПОЛНЕНО

WF по 6 символам (~19 окон). Критерий iter#4 не пройден ни одним.
AAPL PF 2.23 / NVDA 1.78 (трендследование механически работает на
трендовых именах), индексы — нет. Ключевой caveat: выбор AAPL/NVDA =
selection bias, edge не развёртываемый. Нужна point-in-time
momentum-вселенная (отдельный план). Отчёт:
`retro/2026-05-18-equity-trend-wf.md`.

## Pre-registered решения (до взгляда на доходность)

1. **Домен данных — современная эпоха (2005→2026).** Сплит-сведённые
   цены 1980-х (~$0.1 AAPL) — артефакт, не репрезентативны, и ломают
   TP-валидатор на шортах (план 26 finding #2). 2005+ даёт ~5000
   дневных баров / ~20 годовых OOS-окон — кратно выше порога iter#3.
   Это a-priori доменное решение, не подгонка под результат.
2. **Параметры trend_ema — дефолтные** (ema 20/50, atr 14,
   sl_atr 1.5, spread 0.2%, tp1_r 1.5, tier B). НЕ трогаем — иначе
   оверфит (урок XRP-скальп). Только `timeframe: 1d` + symbol-заглушка.
3. **WF-параметры:** IS=730d (2y), OOS=365d (1y), step=365d.
   Warmup 52 ≪ 365 → OOS-сделки будут. ~20 окон на символ.

## Что делаем

### 27.1 — `download_equity --start-year`
Минимальный опц. аргумент: `period1` от начала года N (default —
текущее поведение, без регрессии). Чистая функция + unit-тест. Нужно,
чтобы воспроизводимо взять 2005+ домен.

### 27.2 — config
`strategies/trend_ema_4h/config-equity-1d.yaml`: timeframe 1d, symbol
`EQUITY-USD` (косметика; филлы из файла свечей), остальные параметры =
дефолт trend_ema (pre-registered).

### 27.3 — данные
Перекачать GSPC, NDX, AAPL, NVDA, TSLA, MSTR с `--start-year 2005`.

### 27.4 — полный walk-forward
По каждому символу: `walk_forward.py --strategy trend_ema_4h
--strategy-config config-equity-1d.yaml --candles … --is-days 730
--oos-days 365 --step-days 365`. Собрать OOS PF/PnL/WR/maxDD/Sharpe/
OOS+ доля + total trades.

### 27.5 — отчёт
`retro/2026-05-18-equity-trend-wf.md`: таблица по 6 символам, вердикт
по критерию iter#4 (OOS PF mean >1.5 И PnL >+2% И OOS+ ≥2/3),
индексы vs акции, честная рекомендация.

## Definition of Done
- `--start-year` + тест зелёные; ruff/format/mypy strict; pytest -q.
- 6 символов, полный WF (~20 окон), отчёт с числами в `retro/`.
- Чёткий вердикт по каждому: edge подтверждён / не подтверждён.
- Без подгонки параметров. Прод `core/risk/config.yaml` не тронут;
  `trend_ema_4h/strategy.py` не менялся.
- Live-решение — только при прохождении критерия + отдельная проверка
  tracking-расхождения с синтетикой BingX.

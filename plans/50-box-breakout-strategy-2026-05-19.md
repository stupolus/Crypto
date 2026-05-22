# План 50 — box_breakout (#008): volatility-box breakout + volume-bias

## Дата: 2026-05-19 · Источник: skalping-выжимка #008 · Планка: план 49

## Зачем

Единственный ценный + не реализованный + без блокеров данных кандидат
из видео. Структурно ДРУГОЙ триггер — **пробой консолидации**, не
reversion/momentum (всё прочее в репо — reversion/momentum). Только
klines → полная WF-валидация на бесплатных BingX-данных.

## Логика (Strategy protocol, klines-only)

- **Бокс:** за `box_n` закрытых баров hi=max(high), lo=min(low),
  mid=(hi+lo)/2, width_pct=(hi-lo)/mid·100.
- **Фильтр консолидации:** `width_pct ≤ box_max_width_pct` (узкий
  диапазон = накопление). Иначе не бокс — пропуск.
- **Volume-bias внутри бокса:** `bias = Σ sign(close-open)·volume`
  по box-барам. >0 → бычий, <0 → медвежий (прокси нетто-объёма; L2
  нет).
- **Триггер (на ЗАКРЫТИИ текущей свечи, не фитиль):**
  - LONG: `close > hi` И bias>0 И `volume ≥ breakout_vol_mult ×
    avg(box volume)`.
  - SHORT: `close < lo` И bias<0 И тот же volume-фильтр.
  - `direction_bias` может ограничить сторону.
- **Стоп:** `entry ∓ atr_sl_mult·ATR`, структурный пол — не дальше
  противоположного края бокса; min `stop_min_pct`.
- **TP:** `tp_r × dist(entry,stop)` (RR 1.5–2).
- **Sizing:** RiskEngine (tier B), take_profit прокинут.

## Параметры (pre-registered, дефолты из теории/видео, НЕ под бэктест)

box_n=20, box_max_width_pct=5.0, vol_sma_window=20,
breakout_vol_mult=1.5, atr_window=14, atr_sl_mult=1.0, stop_min_pct=0.3,
tp_r=1.8, risk_tier=B, direction_bias=both. Таймфрейм 15m (как
btc_breakout/us_session для сопоставимости WF).

## Валидация (планка плана 49, заморожена)

`walk_forward --strategy box_breakout` на BTC И ETH 15m, IS=60 OOS=30
step=30 (как iter#1/#4). PASS ⟺ 7 условий плана 49 на ОБОИХ символах.

## Дерево решений (сам, без вопросов)

- PASS на BTC И ETH → промоушен в forward-демо (бумага/VST), прод не
  трогать; план демо-обвязки как у composite.
- НЕ PASS → честно закрыть в retro + PR, без подгонки параметров.

## DoD

- strategy.py + config.py + config.yaml + __init__ + тесты (логика,
  не edge); wired в run_backtest/walk_forward; testpaths.
- Полный WF BTC+ETH, метрики vs план 49, вердикт.
- ruff/format/mypy strict, pytest -q. Прод/демо не тронуты.

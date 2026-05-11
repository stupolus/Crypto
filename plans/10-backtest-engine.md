# План 10 — BacktestEngine: event-driven прогон стратегий на исторических свечах

**Дата:** 2026-05-11
**Статус:** актуальный — план + реализация в той же сессии
**Связано:** [[plans/08-стратегия-btc-breakout]] §6.1, [[plans/09-risk-engine]], [[plans/01-bingx-адаптер]] §4 (модели Order/Kline)

---

## 1. Контекст

Стратегия (план 08) описана. RiskEngine (план 09) готов. Прежде чем запускать стратегию на demo (VST), нужно подтвердить **наличие edge** на истории: 6+ месяцев BTC-USDT 15m → Sharpe > 1.0, max DD < 20%, profit factor > 1.5.

Без BacktestEngine — мы бы прыгнули на demo с непроверенной стратегией → потратили 4 недели на «возможно edge есть».

## 2. Цель плана

`core/backtest/` — event-driven backtester:

1. Принимает `Strategy` (protocol с `on_candle_close` + `on_fill`), `CandleStream` (iterator над `Kline`), `BacktestConfig` (fees, slippage, начальный equity).
2. На каждой закрытой свече: вызывает стратегию → получает `Signal | None`. Эмулирует fill следующей свечой (open + slippage).
3. Учитывает attached SL/TP — при касании цены в свече закрывает позицию.
4. Возвращает `BacktestResult`: trades, equity_curve, summary-метрики.

**Что НЕ делаем:**
- ❌ Vectorized backtest (pandas/numpy magic). У нас single-position single-instrument, event-driven прозрачнее и без скрытых багов.
- ❌ Параллелизация / GPU. На 17280 свечей (6 мес × 15m) event-loop отрабатывает за секунды.
- ❌ Multi-asset / portfolio backtest. На MVP — один символ.
- ❌ Загрузка свечей с BingX (скрипт `download.py` — отдельная задача).
- ❌ Walk-forward / out-of-sample split. На MVP — один прогон, ретро покажет нужны ли дальше.

## 3. Спецификация

### 3.1 `Strategy` protocol (`core/backtest/protocol.py`)

```python
class StrategyContext:
    """Read-only view стратегии на текущее состояние."""
    current_candle: Kline
    history: Sequence[Kline]   # все закрытые свечи до и включая current
    equity: Decimal
    open_position: Position | None  # None если позиции нет
    pending_signals: int       # ждём fill — стратегия не должна слать новый


@runtime_checkable
class Strategy(Protocol):
    def on_candle_close(self, ctx: StrategyContext) -> OrderRequest | None: ...
    def on_fill(self, fill: FillEvent) -> None: ...  # информирование, не обязательно реагировать
```

Возвращает `OrderRequest` (модель из адаптера, переиспользуем). Если `None` — нет сигнала.

### 3.2 Симуляция fill

**MARKET ордер:**
- Исполняется по `open` **следующей** свечи (lag prevents lookahead bias).
- Slippage: `slippage_bps` от `open`. Для BUY — выше, для SELL — ниже.
- Fee: `taker_fee_pct` от notional.

**LIMIT ордер:**
- Если в следующей свече цена коснулась `price`: fill по этой `price`.
  - LONG limit (buy): `low ≤ price`.
  - SHORT limit (sell): `high ≥ price`.
- Иначе остаётся pending до конца окна (или конца теста).
- Fee: `maker_fee_pct` от notional.

**Attached SL/TP:** одновременно при открытии. На каждой свече **с открытой позицией**:
1. LONG: `low ≤ stop_price` → fill по stop_price (worst case). TP1: `high ≥ tp1_price` → reduce 50% по tp1_price.
2. SHORT: `high ≥ stop_price` → fill по stop_price. TP1: `low ≤ tp1_price` → reduce 50%.
3. **Приоритет SL над TP1** если оба касаются в одной свече (worst case — assumption).
4. После TP1: SL остатка → entry (breakeven). Trailing проверяется на close свечи.

### 3.3 Конфиг (`core/backtest/config.py`)

```yaml
fees:
  taker_pct: 0.05    # BingX USDT-M perp
  maker_pct: 0.02
slippage_bps: 10      # 10 bps по умолчанию; уточняется из live metrics.jsonl
initial_equity: 1000  # USDT
slippage_model: fixed_bps  # альтернатива на будущее: spread_bps_from_atr
```

### 3.4 Модели результата (`core/backtest/models.py`)

```python
class FillEvent(BaseModel):
    timestamp_ms: int
    side: OrderSide
    price: Decimal
    quantity: Decimal
    fee: Decimal
    reason: Literal["ENTRY", "STOP_LOSS", "TAKE_PROFIT", "MANUAL_CLOSE", "TRAILING"]


class Trade(BaseModel):
    entry: FillEvent
    exits: list[FillEvent]
    pnl: Decimal
    pnl_pct: Decimal
    duration_ms: int
    max_favorable_excursion_pct: Decimal   # пик прибыли в моменте
    max_adverse_excursion_pct: Decimal     # просадка в моменте


class BacktestResult(BaseModel):
    config: BacktestConfig
    trades: list[Trade]
    equity_curve: list[tuple[int, Decimal]]   # (timestamp_ms, equity)
    summary: BacktestSummary


class BacktestSummary(BaseModel):
    total_trades: int
    win_rate: Decimal
    avg_win_pct: Decimal
    avg_loss_pct: Decimal
    profit_factor: Decimal
    sharpe_ratio: Decimal      # на returns от trade-to-trade
    max_drawdown_pct: Decimal
    final_equity: Decimal
    total_pnl_pct: Decimal
    avg_trade_duration_minutes: Decimal
```

### 3.5 `BacktestEngine.run(strategy, candles, config) -> BacktestResult`

Алгоритм:
1. Загрузка `candles` (sequence `Kline`, отсортирована ASC по `open_time_ms`).
2. Инициализация: `equity = initial_equity`, `open_position = None`, `pending_order = None`, `history = []`.
3. Для каждой свечи `c` в `candles`:
   a. Если есть `pending_order` (MARKET от прошлой свечи): эмулируем fill по `c.open + slippage`. Открываем позицию.
   b. Если есть `open_position`:
      - Проверяем attached SL/TP на `c.low/c.high` (приоритет SL).
      - Если TP1 ещё не сработал и `c.close < tp2_trailing_ema` (для LONG) → закрываем по `c.close` (worst case allowed; для конкретной стратегии можно `c.open` следующей свечи, но это lookahead).
      - На fill: обновляем `equity`, фиксируем `Trade`.
   c. Вызываем `strategy.on_candle_close(ctx)` с `c` как current и `history` (включая `c`).
   d. Если signal != None и нет open position и нет pending — записываем `pending_order = signal`.
   e. Добавляем `c` в `history`.
4. По окончании — собираем `BacktestResult`.

### 3.6 Метрики

- `win_rate` = `wins / total_trades`.
- `profit_factor` = `Σ gains / |Σ losses|`.
- `sharpe_ratio` = `mean(returns) / stdev(returns) × sqrt(N_per_year)` где returns — pnl_pct per trade. Для сделок: `N_per_year = 252 × avg_trades_per_day` (annualized rough).
- `max_drawdown_pct` = `max((peak - trough) / peak × 100)` по equity_curve.
- `MFE / MAE` per trade: пик прибыли и пик просадки между entry и exit.

### 3.7 Чистота от lookahead

**Жёсткие правила (unit-тестом проверяются):**
1. На свече `c` стратегия видит `history` включая `c`. **Не видит `c+1` и далее.**
2. MARKET fill — по `open` свечи `c+1`. **Не по `close` свечи `c`.**
3. Индикаторы (ATR, SMA, EMA, Donchian) — считаются на `history` без подсматривания.

Стратегия не должна писать ничего самостоятельно — только использовать `ctx.history`. На случай нарушения — unit-тест проверяет, что результат backtest НЕ меняется при «перемешивании будущих» свечей.

## 4. Чек-лист

- [ ] `core/backtest/__init__.py` + `models.py` + `protocol.py` + `engine.py` + `metrics.py` + `config.py` + `config.yaml`.
- [ ] Unit-тесты: ≥ 12 кейсов:
  - Стратегия всегда LONG market → equity curve растёт со slippage/fees.
  - Стратегия всегда отказывается → 0 сделок, equity = initial.
  - Stop loss срабатывает: low ≤ stop → fill по stop.
  - TP1 срабатывает: high ≥ tp1 → reduce 50%.
  - SL и TP касаются в одной свече: приоритет SL.
  - LIMIT не достигнут → ордер просрочен, нет fill.
  - Метрики: win_rate, profit_factor, max_drawdown, Sharpe.
  - Lookahead-проверка: меняем будущие свечи → результат не меняется.
- [ ] `pyproject.toml`: добавить `core/backtest/tests` в `testpaths`.
- [ ] ruff + mypy strict — чисто.
- [ ] PR + авто-мерж.

## 5. Резюме

**Было:** стратегия (план 08) и RiskEngine (план 09) есть, но нет способа проверить edge на истории до запуска на demo. Это значит — слепой риск 4 недель demo и денег на live.

**Будет:** event-driven backtester с реалистичной симуляцией fees / slippage / attached SL+TP, метриками для go/no-go решения. На 6 мес BTC-USDT 15m прогоняется за секунды, результат — JSON + markdown summary.

**Альтернатива «backtest на pandas vectorize»:** провал — vectorized SL/TP логика становится монстром, скрытые баги lookahead практически невозможно найти. Event-driven читается как реальный flow адаптера.

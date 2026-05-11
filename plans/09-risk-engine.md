# План 09 — RiskEngine: размер позиции + circuit breakers

**Дата:** 2026-05-11
**Статус:** актуальный — план + реализация в той же сессии
**Связано:** [[plans/08-стратегия-btc-breakout]] §3.5, [[бизнес/риск-профиль]] (источник всех чисел), [[plans/01-bingx-адаптер]] §3 «Защитные инварианты»

---

## 1. Контекст

Стратегия BTC breakout (план 08) запрашивает у RiskEngine: «эквити=X, entry=Y, stop=Z — сколько брать?». Сейчас этой компоненты нет. Без неё:
- Стратегия не может рассчитать `quantity` для `place_order`.
- Не работают circuit breakers (дневной/недельный/месячный стопы).
- Нет валидации «леverage ≤ 5» и «расстояние до ликвидации ≥ 30% от стопа».

## 2. Цель плана

`core/risk/` — чистый модуль (без зависимости от BingX-адаптера), который:
1. Принимает `RiskInputs` (equity, day_pnl, day_trades, side, entry, stop, tier).
2. Возвращает `RiskDecision`: `Approval(quantity, notional, effective_leverage)` или `Rejection(reason)`.
3. Все числа — из `риск-профиль.md`, через `core/risk/config.yaml`. Никакого хардкода.

**Что НЕ делаем:**
- ❌ Учёт fills и P&L бухгалтерии — это задача стратегии/orchestrator. RiskEngine — stateless функция.
- ❌ Persistence (журнал сделок) — у нас уже `OrderJournal` в адаптере.
- ❌ Расчёт ликвидации — для perp BingX это сложно (cross/isolated, margin tier). На MVP принимаем `liquidation_price` от вызывающей стороны (адаптер может посчитать через `/positions` после открытия). Если не передан — проверка skip с warning.

## 3. Спецификация

### 3.1 Модели (`core/risk/models.py`)

```python
class RiskTier(StrEnum):
    B = "B"     # стандарт, 1%
    A = "A"     # подтверждённый, 1.5%
    A_PLUS = "A+"  # премиум, 2%

class Side(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"

class RiskInputs(BaseModel):
    equity: Decimal               # USDT
    day_pnl: Decimal              # USDT (отрицательный = в убытке)
    day_trades_count: int         # сегодняшних сделок (не только убыточных)
    consecutive_losses: int       # последние подряд убыточные
    week_pnl: Decimal | None      # для недельного лимита
    month_pnl: Decimal | None     # для месячного
    side: Side
    entry_price: Decimal
    stop_price: Decimal
    tier: RiskTier = RiskTier.B
    liquidation_price: Decimal | None = None  # опц.

class RiskApproval(BaseModel):
    quantity: Decimal             # размер в базовой валюте (BTC)
    notional: Decimal             # в USDT
    effective_leverage: Decimal
    stop_distance_pct: Decimal
    tier: RiskTier

class RiskRejection(BaseModel):
    reason: str
    code: str  # машинно-читаемый: DAILY_LIMIT / LEVERAGE / STOP_TOO_TIGHT / ...
    details: dict[str, str] = {}

RiskDecision = RiskApproval | RiskRejection
```

### 3.2 `RiskEngine.evaluate(inputs) -> RiskDecision`

Алгоритм (в порядке проверок — fast-fail):

1. **Sanity:** `equity > 0`, `entry_price > 0`, `stop_price > 0`, `side ∈ {LONG, SHORT}`. Иначе `Rejection(INVALID_INPUT)`.
2. **Направление стопа:**
   - LONG: `stop_price < entry_price`. Иначе `Rejection(INVALID_STOP)`.
   - SHORT: `stop_price > entry_price`.
3. **Stop too tight:** `|entry - stop| / entry < stop_min_pct (0.5%)` → `Rejection(STOP_TOO_TIGHT)`.
4. **Circuit breakers (выключают стратегию):**
   - `day_pnl <= -3% × equity` → `Rejection(DAILY_LOSS_LIMIT)`.
   - `day_trades_count >= 3` → `Rejection(DAILY_TRADES_LIMIT)`.
   - `consecutive_losses >= 3` → `Rejection(CONSECUTIVE_LOSSES)`.
   - `week_pnl <= -7% × equity` (если задан) → `Rejection(WEEKLY_LOSS_LIMIT)`.
   - `month_pnl <= -15% × equity` (если задан) → `Rejection(MONTHLY_LOSS_LIMIT)`.
5. **Размер:**
   - `risk_pct = config.risk_pct[tier]` (1.0 / 1.5 / 2.0).
   - `stop_distance_pct = |entry - stop| / entry × 100`.
   - `notional = equity × risk_pct / 100 / (stop_distance_pct / 100) = equity × risk_pct / stop_distance_pct`.
   - `quantity = notional / entry`.
   - `effective_leverage = notional / equity`.
6. **Leverage cap:** `effective_leverage > 5` → `Rejection(LEVERAGE_OVER_CAP)`.
7. **Liquidation buffer (если liquidation_price задан):**
   - LONG: `(stop_price - liquidation_price) / |entry - stop| < 0.3` → `Rejection(LIQUIDATION_TOO_CLOSE)`.
   - SHORT: `(liquidation_price - stop_price) / |entry - stop| < 0.3` → `Rejection(LIQUIDATION_TOO_CLOSE)`.
8. **Approval:** `RiskApproval(quantity, notional, effective_leverage, stop_distance_pct, tier)`.

### 3.3 Конфиг (`core/risk/config.yaml`)

```yaml
# Все числа — из бизнес/риск-профиль.md.
# При изменении: сначала риск-профиль, потом сюда.

risk_pct:
  B: 1.0
  A: 1.5
  A_PLUS: 2.0

limits:
  max_effective_leverage: 5
  stop_min_pct: 0.5
  liquidation_buffer_ratio: 0.3   # (stop - liq) >= 30% от расстояния стопа

circuit_breakers:
  daily_loss_pct: -3.0
  weekly_loss_pct: -7.0
  monthly_loss_pct: -15.0
  max_daily_trades: 3
  max_consecutive_losses: 3
```

### 3.4 `RiskEngine` API

```python
class RiskEngine:
    def __init__(self, config: RiskConfig | None = None): ...
    def evaluate(self, inputs: RiskInputs) -> RiskDecision: ...
```

Чистая функция: один input → один output. Без сети, без persistence.

## 4. Unit-тесты

Минимум 15 кейсов:

- Approval: B-tier, обычная сделка, leverage ≈ 2x.
- Approval: A+ tier, ту же сделку — больше size.
- Reject: equity ≤ 0.
- Reject: entry ≤ 0.
- Reject: stop > entry на LONG.
- Reject: stop < entry на SHORT.
- Reject: stop_distance < 0.5%.
- Reject: daily P&L = -3%.
- Reject: 3 сделки сегодня.
- Reject: 3 проигрыша подряд.
- Reject: weekly P&L = -7%.
- Reject: monthly P&L = -15%.
- Reject: leverage > 5 (например, риск 1% при стопе 0.1% — нельзя).
- Reject: liquidation в 10% за стопом, расстояние до стопа 5% → buffer < 30%.
- Approval: без liquidation_price — проверка skip.

## 5. Что не входит (отложено)

- Реальный расчёт `liquidation_price` (нужно знать `maintenance margin rate` per symbol). Адаптер вернёт его из `/user/positions` после открытия.
- Tier-классификатор (B/A/A+ — кто решает? стратегия передаёт явно).
- Корреляции между инструментами (фаза 2+).
- Volatility-based circuit breaker (volatility > 5% за 5 мин → пауза) — это для adapter-уровня, не RiskEngine.

## 6. Чек-лист

- [ ] `core/risk/config.yaml` со всеми числами.
- [ ] `core/risk/config.py` (pydantic-валидация).
- [ ] `core/risk/models.py` (RiskInputs/RiskApproval/RiskRejection).
- [ ] `core/risk/engine.py` (RiskEngine).
- [ ] `core/risk/__init__.py` экспорты.
- [ ] `core/risk/tests/test_engine.py` (≥ 15 кейсов).
- [ ] `pyproject.toml`: include `core` в setuptools.
- [ ] ruff + mypy strict — чисто.
- [ ] PR + авто-мерж.

## 7. Резюме

**Было:** стратегия (план 08) описана, но не может работать — нет компоненты которая считает размер и валидирует против лимитов.

**Будет:** чистый stateless модуль `core/risk/`. Stateless = легко тестировать, легко переиспользовать (на gold, индексы — тот же RiskEngine). Все числа из риск-профиля, никакого хардкода.

**Альтернатива «сделать RiskEngine частью стратегии»:** провал — повторение для каждой стратегии, нарушение DRY, разные правила для разных инструментов = расхождение с риск-профилем.

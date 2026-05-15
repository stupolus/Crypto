# План 21 — Стратегия liquidation_reversal (Phase 1 спека)

## Дата: 2026-05-15 · Родитель: plans/20-стратегия-из-курса.md

> 🔔 **TODO / напоминание (2026-05-15):** Пользователь одобрил бюджет
> на **Coinglass historical API**, ключи даст 2026-05-16. Когда ключи
> придут: добавить в `.env` (`COINGLASS_API_KEY`), реализовать
> historical-фетчер ликвидаций+OI → полноценный 2-летний IS/OOS
> бэктест (фаза 21.4). До ключей — фазы 21.1-21.3 не блокированы.
> **Claude: подними этот вопрос при следующем заходе пользователя.**

Формализация методологии Щукина (выжимки:
`бизнес/материалы/курсы/dmitry-shukin/`). Spec ДО кода (CLAUDE.md).

## Композит из готовых примитивов

| Примитив | Роль в стратегии | Статус |
|----------|------------------|--------|
| `detect_liquidation_sweep` | триггер: крупная свеча ликвидаций | ✅ есть |
| `detect_oi_trend` | gate направления (RISING/FALLING/breakout) | ✅ есть (#139) |
| `detect_order_flow` / `compute_imbalance` | CVD/дельта подтверждение | ✅ есть |
| `detect_funding_extreme` | фильтр (фандинг ≤ −1.5% → не шортить) | ✅ есть |
| `donchian_channel` | «значимый экстремум» (хай/лой за N) | ✅ есть |

Новый код = только **оркестрация** этих примитивов в `Strategy`
protocol. Никаких новых индикаторов.

## Сетап A1 — LONG Liquidation Reversal

Все на закрытых свечах. Срабатывает если ВСЕ:
1. **Экстремум:** `candle.close <= donchian_low(closed, N_level)`
   (цена у/под значимым минимумом). N_level — кандидат 50 (как gold,
   «значимый» = не локальный шум). НЕ подбирать по бэктесту.
2. **Ликвидация LONG:** `detect_liquidation_sweep` вернул
   `action=="BUY"` (доминируют long-ликвидации) И `spike_ratio >=
   spike_min` (кандидат 5x — дефолт примитива). Это «крупная свеча
   ликвидаций больше предыдущих».
3. **Цикл завершён:** свеча ликвидации НЕ текущая — прошло
   `cycle_wait` свечей (кандидат 1-3) с момента sweep без нового
   sweep ≥ порога. (state machine, см. ниже).
4. **Подтверждение (≥2 из 3):**
   - OI: `detect_oi_trend` state != FALLING (перестал падать/растёт)
   - CVD: `compute_imbalance` за окно > 0 (покупатель появился) ИЛИ
     дивергенция (price lower-low, CVD higher-low)
   - Импульсная зелёная свеча (close > open, тело > ATR*k)

→ `OrderRequest(side=BUY)`, SL/TP по риск-блоку.

## Сетап A2 — SHORT (зеркало A1)

1. `candle.close >= donchian_high(closed, N_level)`.
2. `detect_liquidation_sweep` → `action=="SELL"` (short-ликвидации),
   `spike_ratio >= spike_min`.
3. Цикл завершён.
4. **Жёсткий gate:** `detect_oi_trend` state == **FALLING**
   (обязательно — методология: не шортить пока OI растёт).
5. Подтверждение: CVD < 0 (продавец) ИЛИ дивергенция (price
   higher-high, CVD не higher-high).

## Сетап B — OI-Breakout LONG (опционально, фаза 2)

1. `detect_oi_trend` → `state==RISING AND breakout_from_low==True`.
2. Цена синхронно растёт (`candle.close > donchian` середины окна).
3. → BUY. Без ожидания ликвидаций (ранний trend-entry).

MVP: A1+A2 сначала. B — после валидации A (отдельная итерация),
т.к. B концептуально другой (trend vs reversal), смешивать рискованно.

## Риск-блок (из риск-менеджмент.md, совпадает с RiskEngine)

- Риск 1% (tier B). Размер = `RiskEngine.evaluate` (как btc_breakout).
- SL: структурный — за `donchian_low/high(closed, N_level)` ± buffer,
  ИЛИ min 0.5% (риск-профиль). Берём дальний (как `_compute_stop`).
- TP1: **3R** (курс: старт 1:3; btc_breakout 1.5R — занижено).
  `tp1_r_multiple: 3.0` в config.
- Split-вход (50%+50% на доборе) — ОТЛОЖЕНО (усложняет MVP, риск).

## Данные: ключевая архитектурная проблема

`StrategyContext` сейчас = candle/history/equity/open_position.
Стратегии нужны ДОПОЛНИТЕЛЬНО: liquidation buckets, OI-ряд, delta.
Текущий паттерн (btc_breakout) — DI-провайдеры (funding/news/blacklist).

**Решение (consistent с проектом):** добавить DI-провайдеры:
- `LiquidationProvider.get_bucket(symbol, ts) -> LiquidationBucket | None`
- `OpenInterestProvider.get_series(symbol, ts, n) -> list[Decimal]`
- `DeltaProvider.get_cvd(symbol, ts, n) -> list[Decimal]`

Live: обёртки над Coinglass/BingX (poll). Backtest/тест: Static*
заглушки (как `StaticFundingProvider`). Стратегия зависит только от
протоколов — testable без сети.

## Блокер B2 (бэктест) — честно

Live данные есть (Coinglass live + BingX OI snapshot poll). Для
**бэктеста** на 2+ года нужна ИСТОРИЯ ликвидаций+OI+CVD. Варианты:
1. Coinglass historical API (платный? проверить лимиты) — лучший.
2. Reconstruct: ликвидации ≈ аномальные knot-свечи объёма+волатильности
   (грубое приближение, отметить как proxy в бэктесте).
3. Прогон только live forward-test на VST 4+ недели (CLAUDE.md и так
   требует 4 нед demo) → собрать реальную статистику вместо history.

Рекомендация: **(3) + (2)**. Forward-test на VST накопит честные
данные; proxy-бэктест — груба санити-проверка что логика не ломается.
Чистый history-бэктест отложить до решения по Coinglass (вопрос
пользователю: есть ли платный Coinglass план / бюджет на данные?).

## Фазы реализации (каждая = PR)

- **21.1** DI-протоколы + Static-заглушки (`core/signals/providers.py`
  расширить) + тесты. Без стратегии.
- **21.2** `strategies/liquidation_reversal/` — A1+A2, config, unit-тесты
  (синтетика через Static-провайдеры).
- **21.3** Live-провайдеры (Coinglass/BingX-OI обёртки) + wire в
  llm_runner (как gold/oil/stock).
- **21.4** Proxy-бэктест (вариант 2) + forward-test setup на VST.
- **21.5** (после 4 нед VST) анализ edge → решение go/no-go.

## 10 причин провала (дополнение к плану 20)

1. «Значимый экстремум» = дискреционно в курсе; donchian-50 может не
   совпасть с тем что имел в виду автор → ложные/пропущенные сетапы.
2. «Цикл ликвидаций завершён» формализован грубо (N свечей) — реально
   автор смотрит на глаз. Риск ранний/поздний вход.
3. OI snapshot poll имеет лаг; на быстрых движениях gate запоздает.
4. CVD из BingX aggTrades ≠ то что показывает Coinglass автору.
5. Composite из 5 условий → редкие сигналы (как gold: мало сделок,
   статистически слабо). Может оказаться нетестируемо за разумное время.
6. Курс — youtube-маркетинг; edge мог не существовать вовсе (бэктест
   плана 19 уже показал что «очевидные» сетапы не работают).
7. Look-ahead: легко случайно использовать данные будущей свечи в
   liquidation/OI выравнивании по времени. Строгая проверка.
8. Forward-test на VST: ликвидности RWA/alt на VST мало → исполнение
   нереалистично. Тестировать на BTC/ETH/SOL где VST ликвиден.
9. Coinglass история платная/недоступна → чистого бэктеста не будет,
   только forward — медленно (недели на статистику).
10. Переусложнение: 3 новых провайдера + 3 сетапа = большая
    поверхность багов. Жёстко держать MVP = только A1+A2.

## Вопрос пользователю (не блокирует 21.1-21.2)

Есть ли бюджет/доступ к **Coinglass historical API** (или другому
источнику истории ликвидаций+OI)? От этого зависит: будет ли
полноценный 2-летний бэктест или только VST forward-test 4+ недели.

# План 31 — composite-сигнал: стратегия + forward-test на демо

## Дата: 2026-05-18 · База: план 30 (вся библиотека без edge), принцип 3

## Зачем

Ре-валидация старого исчерпана (план 30): btc_breakout/trend/us_session
— edge нет. Принцип 3: один скринер = шум, композит (≥2-3 ортогональных
сигнала) = сигнал. Строим composite-стратегию.

## Что уже есть (переиспользуем, не пишем с нуля)

`core/signals/` — собранная и протестированная инфра:
- `aggregate_extended_signals(funding, order_flow, liquidation)` →
  `SignalCandidate` если **≥2 из 3 согласны** по направлению, иначе
  None (1 сигнал/конфликт = шум). Это и есть композит принципа 3.
- `detect_funding_extreme`, `detect_order_flow`, `detect_liquidation_sweep`,
  `detect_oi_trend` — детекторы с конфигами.
- Провайдеры (Static/Rolling) + RiskEngine — как в liquidation_reversal.

Стратегия = сборка этих кирпичей под `Strategy` protocol (как
liquidation_reversal). Нового сигнального кода — минимум.

## ЧЕСТНЫЙ feasibility-блокер (определяет путь)

Историю для бэктеста имеют НЕ все входы:
- funding: ✅ `download_funding` (BingX fundingRate).
- klines: ✅.
- **Open Interest: ряда НЕТ** — BingX отдаёт OI снапшотом
  (`live_providers.py`: «не временной ряд»).
- **Liquidations / CVD: истории НЕТ** — нет BingX-эндпоинта; Coinglass-
  адаптера не существует (ключи есть, адаптер — отдельный крупный проект).

⇒ Композит **нельзя честно бэктестить** на доступных данных (как и
equity-арка). Историческая WF-валидация невозможна **by data**.

## Путь (вытекает из блокера)

Для сигналов без истории среда валидации — **forward-test на демо
(VST, бумажные деньги)**. Это методологически валидно ТОЛЬКО как
**pre-registered эксперимент с kill-критерием**, не «включил и смотрю».

Последовательность:
1. **Build** composite-стратегия + config + тесты (чистая логика).
2. **Partial sanity** — бэктест funding-only подсигнала (там, где
   история есть) + прогон с Static-провайдерами на синтетике (тест,
   что стратегия эмитит ордера корректно). НЕ выдаём за валидацию edge.
3. **Pre-registered forward-test design** (в этом плане, см. ниже).
4. **Demo-wiring** в VST-раннер — ТОЛЬКО после подтверждения
   пользователем параметров эксперимента (дата-старт, символы,
   длительность, kill). Демо тратит общий ресурс/может пересечься с D3
   — флипаю не молча.
5. Через горизонт — оценка по критерию, решение live/kill.

## Pre-registered forward-test (заполнить перед demo-вкл)

- Символы: ETH, BTC + (TBD).
- Горизонт: ≥ 4 недели реального времени (минимум для не-sample-luck).
- Success: реализованный PF ≥ 1.5 И net PnL > 0 после комиссий И
  ≥ 55% недель в плюсе.
- **Kill (жёстко):** −5% демо-эквити ИЛИ 5 убытков подряд ИЛИ PF < 0.8
  на ≥ 30 сделках → стоп, разбор, без «дотягивания».
- Параметры детекторов — дефолтные, НЕ подгоняются в ходе теста.

## Шаги (этой итерации — только 1-3)

### 31.1 — `strategies/composite_signal/`
`strategy.py` (Strategy protocol, по образцу liquidation_reversal:
DI-провайдеры funding/oi/liq/delta, aggregate_extended_signals + OI-gate,
RiskEngine, ATR-стоп + R-кратный TP), `config.py`, `config.yaml`,
`__init__.py`.

### 31.2 — тесты
`strategies/composite_signal/tests/`: консенсус ≥2 → ордер; 1
сигнал/конфликт → None; OI-gate режет против тренда; RiskEngine-reject
→ None. Static-провайдеры, без сети.

### 31.3 — wiring в `run_backtest`/`walk_forward` choices + sanity-прогон
на Static/синтетике (эмитит ли ордера). Отчёт-заготовка.

### Демо (31.4+) — отдельным шагом, ПОСЛЕ подтверждения forward-дизайна.

## Definition of Done (этой итерации)
- Пакет стратегии + тесты зелёные; ruff/format/mypy strict; pytest -q.
- Честно зафиксировано: историческая валидация невозможна, демо =
  pre-registered forward-test.
- Forward-дизайн вынесен пользователю на подтверждение ДО demo-вкл.
- Прод `core/risk/config.yaml`, существующие раннеры/D3 не тронуты.

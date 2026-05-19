# План 44 — composite v3: session-time gate (одно улучшение, не «пять»)

## Дата: 2026-05-19 · База: план 43 (v2)

## Жёсткое условие (то же, что v2)

v3 = **отдельный кандидат** (`config-v3.yaml`), opt-in поле с
дефолтом = v2. config.yaml / config-4h-demo.yaml (forward-демо) **не
тронуты**. Параметры работающего эксперимента менять «на ходу» =
оверфит. v3 в live НЕ идёт; ту же планку (iter#4) проходит на
нормальных данных, не на сегодняшних 4 OOS-сделках.

## ОДНО улучшение, не пять

### 44.1 — Session-time gate (UTC-часы)

Теория (микроструктура): ликвидационные каскады, funding-экстремы и
OI-смены концентрируются в часы US/EU-овлапа (≈13–21 UTC). Азиатская
сессия в одиночку — низкая ликвидность, шумные движения; контртрендовые
setup'ы (funding/liq) там фейлят чаще. У composite сейчас нулевой
session-context.

Config-поле: `session_hours_utc: list[int] | None = None` (None =
выкл, любое время). Pre-trade gate: `dt = datetime.fromtimestamp(
candle.open_time_ms/1000, UTC).hour`; если `session_hours_utc` задан
и `dt not in session_hours_utc` → skip.

**Pre-registered v3** (`config-v3.yaml`): `session_hours_utc =
[13..21]` (US-pre + США + EU-overlap end) + всё из v2.

## Что НЕ делаем (честно)

- **НЕ** добавляю ещё фильтров/порогов ради «улучшить цифру». Каждый
  такой = подгонка к 4–7 сделкам = ложный edge.
- **НЕ** прогоняю v3 vs v2 на Coinglass 4h — выборка ≤4 OOS-сделок,
  любой результат = шум, не вердикт. Сравнение v3↔v2 = шаг плана 45
  (после апгрейда тарифа Coinglass).
- **НЕ** меняю демо v1.

## Definition of Done

- Поле в `CompositeConfig` + ветка в strategy.py + `config-v3.yaml`.
- Unit-тест: дефолт (None) пропускает любой ts; v3-band пропускает
  внутри / режет снаружи.
- Прежние 11 тестов composite зелёные → v1/v2 не изменились.
- ruff/format/mypy strict, pytest -q. Прод/демо/core-risk не тронуты.
- Валидация — после апгрейда тарифа (план 45), не сейчас.

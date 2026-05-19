# План 32 — composite: backfill-валидация ДО демо (исправление)

## Дата: 2026-05-18 · База: план 31, parsers/coinglass

## Исправление моей ошибки (важно)

Планы 28/31 утверждали: «историческая валидация composite невозможна
(нет рядов OI/liq/CVD), поэтому сразу демо». **Это неверно — я
недоисследовал.** `parsers/coinglass/backfill.py` уже умеет тянуть
ИСТОРИЮ:
- `get_liquidation_history`, `get_open_interest_history`,
  `get_cvd_history`, funding-rate history (Coinglass API).
- `backfill_providers(...)` строит исторические провайдеры → стратегия
  «гоняется офлайн» (бэктест).

⇒ composite **можно и нужно бэктестить на истории**, а не «вслепую на
демо». Слепое демо непроверенной стратегии = ровно ошибка D3, которую
вся сессия документировала. Дисциплина требует backfill→backtest→WF
ДО любого демо.

## Блокер окружения (честно)

В этом эфемерном cloud-контейнере **нет `COINGLASS_API_KEY`** (нет
`.env`, свежий clone). Поэтому ни backfill, ни демо отсюда запустить
нельзя — это делается в окружении с ключом (локально/VPS). Я делаю
всё turnkey, но «врубить» из этой сессии не могу и не имитирую.

## Что сделано в коде (turnkey)

- `composite_signal` подключён в `live_runner` (как liquidation_reversal:
  без Coinglass-провайдеров = безопасный no-op, не торгует) + в choices.
- Стратегия + бэктест-харнес (план 31) готовы принять
  Coinglass-backfilled провайдеры.

## Правильная последовательность (в окружении с ключом)

### 32.1 — backfill истории
`python -m parsers.coinglass.backfill` для ETH/BTC (liq+OI+CVD+funding,
≥12 мес) → исторические провайдеры/jsonl.

### 32.2 — composite backtest + полный WF
Прогнать `CompositeSignalStrategy` через backtest-харнес с
backfilled-провайдерами; полный walk-forward; вердикт по критерию
iter#4 (PF>1.5 И PnL>+2% И OOS+≥2/3). Параметры — дефолт, не подгонять.

### 32.3 — gate
- Прошёл критерий → forward-test на демо (pre-registered дизайн
  плана 31: ETH+BTC, ≥4 нед, kill −5%/5 losses/PF<0.8@30).
- Не прошёл → честно зафиксировать, composite не в демо. Не натягивать.

### 32.4 — demo-wiring (только после 32.3 pass)
Coinglass-live-провайдеры в live_runner + VST-контейнеры (изолированно
от D3), деплой на VPS.

## Definition of Done (этой итерации — только код+план)
- composite в live_runner (no-op) + choices; гейты зелёные.
- Ошибка планов 28/31 исправлена явно (этот план + retro).
- Чёткая turnkey-инструкция; блокер ключа назван честно.
- Прод/D3 не тронуты. Демо НЕ включено (нечем валидировать здесь).

# Ретро 2026-05-15 — asset-стратегии, дашборд, разворот к курсу

## Тема сессии

Мега-сессия: 25 PR (#119-#144) за один день. Три фазы:
1. Asset-стратегии (gold/oil/stock) + multi-runner инфраструктура
2. Прод-фиксы по реальным VST-инцидентам
3. Стратегический разворот: бэктест провалил всё → переход к
   формализации проверенной методологии (курс Щукина).

## Что было / что стало

### Фаза 1 — asset-стратегии (план 19)
- **Было:** только btc_breakout, один runner.
- **Стало:** GoldSafetyHaven / OilEiaAvoid / StockEarningsAvoid +
  generic `direction_bias`, WeeklyEventCalendar (EIA), earnings
  blackout, wire в runner, systemd multi-instance, backtest CLI +
  cross-strategy comparator.

### Фаза 2 — прод-фиксы (по скриншотам Telegram/Manus)
- **101400 SL wrong side** → llm_gate direction-валидация (#121).
- **101429 position limit** → диагностический лог (root cause ждёт
  свежий инцидент).
- **109425 symbol not exist** → BingX VST реальные имена
  (XAU→XAUT, CL→NCCO1OILWTI2USD, TSLA→NCSKTSLA2USD) (#130).
- Дашборд: multi-runner DB-агрегация, symbol-filter, strategy
  leaderboard, equity-snapshots, Trade Replay, iOS PWA.
- correlation gate (max 1 позиция на asset class), instance-tag в
  Telegram, live equity snapshots.

### Фаза 3 — разворот стратегии (планы 20-21)
- **Бэктест 6 мес IS/OOS показал: edge нет ни у одной стратегии.**
  btc_breakout PnL −2.4% OOS PF 0.91; gold 5 сделок (шум);
  oil/stock явно убыточны.
- Решение пользователя: формализовать курс «Криптограмотность»
  (Щукин) вместо выдуманных Donchian-параметров.
- 100 транскриптов → 6 выжимок по 4 вёдрам → план 21 → стратегия
  `liquidation_reversal` (composite: ликвидации + OI + CVD + funding).
- OI-фид (#139), DI-провайдеры (#141), стратегия A1/A2 (#142),
  live-OI (#143), wire (#144).

## Чему научились

1. **«Логичная идея» ≠ edge.** План 19: gold/oil/stock —
   обоснованные сетапы, но бэктест разнёс. Только данные решают.
   То же скептически применяем к курсу Щукина (YouTube-маркетинг).
2. **Прод ловит то что тесты не ловят.** SL-direction и symbol-
   naming баги вылезли только на живом VST через Telegram-алерты.
   Вывод: диагностический лог в alert (qty/sl/tp) окупился.
3. **Данные — узкое место.** Методология Щукина построена на OI/
   ликвидациях, которых не было в проекте. Полноценный бэктест
   требует Coinglass historical (платно). Без данных стратегия
   не валидируема — отложено до ключа.
4. **DI-провайдеры масштабируются.** Паттерн StaticFundingProvider
   переиспользован для Liquidation/OI/Delta — стратегия testable
   без сети, live-обёртки подключаются отдельно.
5. **Анти-look-ahead — явный риск.** В провайдерах сделали
   get_baseline СТРОГО до ts; зафиксировано тестом. Легко
   случайно заглянуть в будущее при выравнивании ликвидаций/OI.

## Что отложено / TODO

- 🔔 **Coinglass historical ключ — 2026-05-16** (бюджет одобрен).
  Блокирует: live-ликвидации, CVD, 2-летний бэктест liquidation_
  reversal. TODO в `plans/21-liquidation-reversal-strategy.md`.
- **101429 root cause** — ждёт свежий прод-инцидент с диагностикой.
- PR #138 (транскрипты + выжимки) — merge за пользователем
  (cross-session content-PR).
- gold/oil/stock на VST крутятся как данные-сбор (edge не доказан) —
  решение go/no-go после 4 нед demo (CLAUDE.md).

## Метрика дисциплины

- Параметры стратегий НЕ подгонялись под бэктест (AGENTS.md).
- Каждая фаза = план в `plans/` до кода (CLAUDE.md).
- Убыточные стратегии не отключены силой, но и edge не приписан —
  честно задокументировано в `курсы/dmitry-shukin/что-проверить.md`.
- 25/25 PR: ruff + ruff format + mypy strict + тесты зелёные до merge.

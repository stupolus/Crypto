# 2026-05-26 — Paper-runner и инфраструктура деплоя готовы (Шаги 6+7)

## Что закрыли

**Шаг 06 — Paper-runner** (план `plans/06-paper-runner-2026-05-22.md`):

- `paper/feed.py` — поллер закрытых свечей с close_grace_ms.
- `paper/journal.py` — SQLite-журнал (trades, equity_points, runner_state,
  daily_summary), WAL, транзакции, restart-safe.
- `paper/engine.py` — тот же fill-контракт, что в `backtest.engine`:
  сигнал на свече N → MARKET-fill по open свечи N+1; стоп/тейк по
  high/low; при обоих внутри бара — стоп. Поднимает circuit breakers
  (kill-switch −15%, daily stop, consecutive losses).
- `paper/reporter.py` — Telegram-нотификатор, env-gated, no-op без
  токена. Rate-limit 30/час. Сетевой вызов через инжектируемый sender,
  тесты не дёргают сеть.
- `paper/runner.py` — оркестратор: warmup истории, шаг polling по всем
  символам, heartbeat в SQLite, daily summary.
- `paper/config.py` + `config/paper.yaml` — символы PAXG/XAUT, 15m,
  taker 0.05%, slippage 0.05%, journal `/var/lib/gold-bot/paper.sqlite`.
- `scripts/run_paper.py` — CLI: дефолт-режим, `--dry-run` (только warmup),
  `--once` (один step и выход).
- Тесты: 33 unit'а на feed/journal/engine/reporter/config (всё без сети).

**Шаг 07 — Деплой** (план `plans/07-deploy-2026-05-22.md`):

- `deploy/Dockerfile` — `python:3.12-slim`, non-root uid 1000, paper-only
  ENTRYPOINT (`python -m scripts.run_paper`).
- `deploy/docker-compose.yaml` — `restart: unless-stopped`, healthcheck
  по heartbeat в SQLite, лимит логов 50MB × 5 файлов, env_file.
- `deploy/.env.example` — только Telegram-переменные (биржевых ключей
  на paper-стороне нет).
- `deploy/systemd/gold-bot-paper.service` + `gold-bot-daily-report.{service,timer}`
  — резервный путь без Docker.
- `deploy/README.md` — операционная инструкция.
- `scripts/daily_report.py` — сводка за прошедший UTC-день: trades,
  winrate, PF, gross/costs/net, equity_close. Запуск из cron @ 00:05 UTC.
- Тесты: 5 unit'ов на `_summarize` / `_format`.

## Гейты

- 162 теста зелёные (было 129 до фазы 6, +28 paper + 5 daily_report).
- `ruff check` — clean.
- `ruff format --check` — clean.
- `mypy --strict` — clean по `paper/`, `scripts/` (21 source files).

## Где мы по master-плану

| Шаг | Статус |
|-----|--------|
| 00 ccxt-адаптер BingX+Bybit | ✅ |
| 01 plan + код адаптера | ✅ |
| 02 data layer (parquet) | ✅ |
| 03 indicators + RiskEngine + kill-switch | ✅ |
| 04 event-driven бэктест + walk-forward | ✅ |
| 05 стратегия mean-reversion VWAP | ✅ |
| **06 paper-runner** | **✅ (этот коммит)** |
| **07 деплой VPS** | **✅ (этот коммит)** |

## Что блокирует переход в live (по плану и /goal)

Капитал остаётся на $0. Переход в фазу 2 (mini-real $1k) требует:

1. **OOS-вердикт бэктеста по реальным свечам с BingX.** Бэктест-команда
   ждёт прогона на VPS (через Манус). Пороги (`plans/00-master-plan`):
   PF ≥ 1.3, max DD ≤ 8%, ≥ 30 сделок/окно, ≥ 3 OOS-окон.
2. **≥ 4 календарные недели paper-наблюдения** на PAXG/XAUT с runner'ом,
   деплоенным по плану 07. С журналом сделок в SQLite и сравнением
   «бэктест vs paper» в `journal/`.
3. **Champion-challenger каркас** (план 08, ещё не написан) —
   нужен, чтобы новые стратегии тестировались на бумаге параллельно
   и не вытесняли champion'а после удачной серии.
4. **Live-runner** (план 09, ещё не написан) — отдельный модуль с
   реальными ордерами, attached stop-loss, sync положений на старте.
   Будет писаться **только после** того, как paper покажет PF ≥ 1.2
   и max DD ≤ 6% за 4 недели.
5. **Явное письменное «да» пользователя на конкретную стратегию.**

## Запреты, которые остаются в силе до перехода в live

- Никаких реальных ордеров. Адаптер на paper-стороне используется только
  для `fetch_markets` / `fetch_ohlcv` (CLAUDE.md §6, plan 06 §«Ключевые
  инварианты»).
- Никаких изменений `risk-profile.md` / `risk.yaml` без отдельного
  обоснования.
- Никакого live-режима в Dockerfile / systemd-юните.
- Никакого debugging на live (CLAUDE.md §6).

## Что делает Манус прямо сейчас (на VPS)

1. Обновляет `gold-bot/` из `origin/gold` (фикс download_klines от 92c8b38).
2. Качает 6 месяцев 15m свечей PAXG/XAUT/BTC.
3. Прогоняет walk-forward бэктест по PAXG и XAUT.
4. Отправит вывод.

После вывода — обновлю этот файл с фактическим OOS-вердиктом и решением
(идти в paper-наблюдение или менять гипотезу).

## Следующая работа (после OOS-вердикта)

Если OOS прошёл пороги:
- Деплой paper-runner'а на VPS по `deploy/README.md`.
- Старт 4-недельного paper-наблюдения с daily-report.
- Параллельно — план 08 (champion-challenger каркас).

Если OOS не прошёл:
- Не «крутить параметры». Записать честный провал в `journal/`.
- Сформулировать следующую гипотезу (mean-reversion на другой полосе?
  momentum-breakout по объёму на открытии Лондона? funding-arb?).
- Новый план в `plans/08-...-strategy-N2.md`.

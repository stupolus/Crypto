# 08 — Champion-challenger (параллельные paper-кандидаты + промоушен)

Дата: 2026-05-26
Статус: первичный, готов к реализации

## Цель

Реализовать Шаг 5 master-плана: **одна стратегия торгует капиталом (champion),
N других учатся и тестируются НА БУМАГЕ параллельно (challengers)**.
Промоушен challenger → champion **только при статзначимом преимуществе на
out-of-sample**, не «после пары удачных дней» (/goal §5).

## Чего НЕ делаем

- Не оптимизируем параметры боевой стратегии ежедневно. Champion-параметры
  меняются только через коммит + ретроспективный бэктест.
- Не обучаем ML на торговом счёте. Никакого онлайн-обучения.
- Challengers — это **другие гипотезы / другие параметры**, не «дочерние
  модели» champion'а. По одному кандидату — один план в `plans/`.

## Архитектура

```
paper/
├── competition.py     # CompetitionRunner: ведёт champion + N challengers
├── promotion.py       # PromotionDecision: статтест champion vs challenger
└── tests/             # unit'ы на оба
```

`CompetitionRunner` — обёртка над несколькими `PaperRunner`-инстансами.
Каждая стратегия пишет в **свой PaperJournal** (отдельный SQLite-файл или
`:memory:` для тестов). Изоляция гарантирована.

`PromotionDecision`:
1. Берёт последние N дней trades champion и каждого challenger.
2. Считает per-trade returns (`net_pnl / starting_equity`).
3. Тест значимости: bootstrap-difference в медиане + non-parametric sign-test
   на минимум 30 сделок у обоих.
4. Возвращает `Promote(challenger_id)` только если p-value < α/N (Bonferroni)
   И разница в PF ≥ 0.2 И max DD challenger'а не хуже на 2 п.п.

## Конфиг

`config/competition.yaml`:

```yaml
champion: mean_reversion_vwap.v1
challengers:
  - mean_reversion_vwap.v1_tighter   # k_entry=2.2 вместо 1.8 — гипотеза «значимее = ниже шум»
  - mean_reversion_vwap.v1_atr_period_21  # ATR 21 — медленнее, реже сигналы
evaluation_window_days: 28
min_trades_per_window: 30
significance_level: 0.01
min_pf_advantage: 0.2
max_drawdown_tolerance_pp: 0.02
```

Каждый `challenger` ссылается на параметры в `config/strategies/<id>.yaml`
(новый каталог) — base-параметры лежат в `strategies/mean_reversion_vwap/config.yaml`,
варианты — отдельными файлами, чтобы не плодить «магических чисел».

## Инварианты

1. **Champion и challengers получают тот же поток свечей.** Один `PaperFeed`
   на символ, broadcast в N движков. Это исключает «удача с тайминга».
2. **Каждый participant имеет свой PaperJournal.** RiskState изолирован —
   challengers не могут провалить дневной/недельный лимит champion'а.
3. **Промоушен — только из контекста CLI** `scripts/promote_challenger.py`.
   Никакого автоматического переключения боевых параметров в живом runner'е.
4. **Промоушен меняет конфиг + ретробэктест**. Команда:
   - читает `config/competition.yaml`
   - выводит `PromotionDecision`
   - если PASS — печатает diff конфига для коммита (но **не коммитит сама**)
5. **Журнал решений**. Каждый запуск promote — строка в SQLite-таблице
   `promotion_log` (timestamp, champion_id, candidate_id, decision, p_value,
   metrics_dump).

## Порядок реализации

1. **08A — competition.py + конфиг + тесты.** Broadcast feed, журналы по
   participant'у. ✅ реализовано в этом коммите.
2. **08B — promotion.py + scripts/promote_challenger.py + тесты.** Статтест,
   CLI-выдача diff'а конфига. ✅ модуль и тесты в этом коммите; CLI
   `promote_challenger.py` — следующая фаза (нужны реальные paper-данные).
3. **08C — деплой.** Расширить docker-compose ENTRYPOINT'ом
   `scripts.run_competition`. Daily-report — отдельно по champion и
   challenger'ам. Делается после первой недели paper-наблюдения.

## 10 причин почему может не получиться

1. **Один SQLite → конкурентная запись N движков → блокировки.** Решение:
   каждый participant — свой PaperJournal-файл; всё в одном asyncio-loop'е,
   последовательные вызовы `process_closed_candle`.
2. **Common-cause bias: champion и все challengers — варианты одной идеи,
   значит провал общий.** В `plans/08+N`-файлах требуем что новая гипотеза
   имеет независимый edge (другая фича, другой класс), не только «крутим
   `k_entry`».
3. **Статтест по 30 сделкам — низкая мощность.** На 15m PAXG это ≈ 2 недели
   активности. Решение: окно 28 дней (`evaluation_window_days`).
4. **Подсматривание (multiple comparisons): сравниваем champion с 5 challenger'ами,
   p-value 0.01 одного из них найдётся случайно.** Bonferroni: эффективный
   порог = 0.01 / N. Зафиксировано в коде.
5. **Challenger открывает позицию которую champion не открывает, но движок
   ставит её в `runner_state.open_position:champion`** — ошибка namespace'а.
   Решение: разные журналы (доказано тестом `test_broadcast_to_two_participants`).
6. **Промоушен случается в момент когда challenger ещё не выходил из открытой
   позиции** — учёт незакрытой сделки нечестен. Решение: статтест считается
   только по **закрытым** сделкам в окне.
7. **Champion и challenger с одинаковыми параметрами → identical trades**, тест
   ничего не покажет. Решение: pre-flight проверка `params_hash` уникален.
8. **Конфиг challenger меняется на лету в файле без коммита** — невоспроизводимо.
   `competition.yaml` хеш-чексумится на старте, hash пишется в journal.
9. **Manus / оператор переименовывает strategy_id в конфиге** — потеря истории.
   `strategy_id` immutable в схеме (PK), переименование = новый id, история
   старого остаётся.
10. **Champion провалился по daily-stop и halted, а challenger остался активен**
    — выглядит как «преимущество» challenger'а, на самом деле shadow-эффект.
    Решение: статтест отдельно учитывает halted-дни (исключает их у обоих).

## Критерии приёмки

- Unit-тесты `paper/competition.py` (broadcast, namespace state, isolation). ✅
- Unit-тесты `paper/promotion.py` (bootstrap-stat, sign-test, Bonferroni). ✅
- `scripts/run_competition.py --once` запускает шаг по 1 свече FakeAdapter'а,
  каждая стратегия пишет в свой namespace, нет cross-write — следующая фаза.
- `scripts/promote_challenger.py --dry-run` печатает текущее состояние без
  решения (PASS требует ≥30 закрытых сделок) — следующая фаза.
- `ruff`, `ruff format`, `mypy --strict` clean. ✅

## Зависимости

- План 06 (paper-runner) — есть, переиспользуем PaperEngine/Feed/Journal.
- Plan 05 (стратегия) — есть.

## Что после плана 08

- Реальный paper-старт на VPS (плана 07 деплой).
- 28 дней наблюдения с тремя challenger'ами.
- Решение по промоушену.
- План 09 (live-runner) — пишется **только если champion прошёл статтест
  и пользователь дал письменное «да»**.

## История

| Дата | Изменение |
|---|---|
| 2026-05-26 | Создан план. Реализованы фазы 08A и часть 08B (модули + тесты). |

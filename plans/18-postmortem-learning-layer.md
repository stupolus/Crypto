# План 18 — Layer 6: Post-Mortem & Learning

**Дата:** 2026-05-12
**Статус:** первичный — план до кода
**Связано:** [[plans/17-llm-composite-subagents]] (Layer 6 расширение), [[plans/16-деплой-24-7]] (operational), [[CLAUDE.md]] §«Поток работы»

---

## 1. Контекст

После плана #17 у нас есть LLM-команда (5 субагентов) которая принимает торговые решения. **Чего нет:** механизма **обучения на собственных ошибках**.

Без этого слоя:
- Каждое плохое решение остаётся в журнале как «случилось»
- Те же ошибки повторяются (LLM не помнит прошлый опыт между decisions)
- Нет систематического разбора «почему мы потеряли»
- Нет улучшения промптов на основе реальной производительности

**Цель Layer 6:** превратить торговый журнал из **архива** в **активную память** которая влияет на каждое следующее решение.

## 2. Архитектура

```
┌─ Layer 5 (Execution) — каждый ордер закрывается ─────────────────────┐
│  - Запись TradeOutcome в journal/trades/<trade_id>.json              │
│  - Полный контекст: signal, все subagent decisions, market state     │
└──────────────────────┬───────────────────────────────────────────────┘
                       │
┌─ Layer 6.1: Trade Outcome Logger (sync) ─────────────────────────────┐
│  Сохраняет ВСЁ что привело к сделке + результат:                     │
│    - SignalCandidate (Layer 2)                                       │
│    - Все 5 ответов субагентов (Layer 3)                              │
│    - Macro snapshot на момент входа                                  │
│    - Risk Engine validation result (Layer 4)                         │
│    - Execution params (price/SL/TP)                                  │
│    - Outcome: PnL%, holding time, exit reason (TP/SL/manual/timeout) │
└──────────────────────┬───────────────────────────────────────────────┘
                       │
┌─ Layer 6.2: Mistake Library (постоянная память) ─────────────────────┐
│  При закрытии каждой убыточной сделки:                                │
│  - Auto-classify: что пошло не так?                                  │
│    (signal_wrong, sentiment_wrong, market_changed, slippage_high,     │
│     risk_overlooked, execution_late, …)                              │
│  - Если NEW pattern (не похоже на прошлые) → новая запись в           │
│    journal/mistakes/<дата>-<категория>.md                            │
│  - Embedding-based similarity search для retrieval                   │
└──────────────────────┬───────────────────────────────────────────────┘
                       │
┌─ Layer 6.3: Past-Mistakes Context Injector ──────────────────────────┐
│  Перед каждым LLM-decision:                                          │
│  - Текущий signal + контекст                                          │
│  - Embedding similarity → топ-3 похожих past mistakes                │
│  - Подаются в Coordinator + Risk Overseer как:                       │
│    "Past mistakes relevant to this setup:                            │
│     1. 2026-04-15: похожий BTC breakout failed because [reason]      │
│     2. 2026-04-22: похожий sentiment overshooted, exit was late      │
│     ..."                                                              │
│  → не повторяем то на чём горели                                     │
└──────────────────────┬───────────────────────────────────────────────┘
                       │
┌─ Layer 6.4: Weekly Review (research agent через paperclip) ──────────┐
│  Раз в неделю Claude Opus 4.7 анализирует все trades за неделю:      │
│  1. Топ-3 убыточных: что общего? Что упустили?                       │
│  2. Топ-3 прибыльных: какой паттерн? Воспроизводим ли?               │
│  3. Какой субагент чаще всего ошибается? Промпт нужно тюнить?        │
│  4. В каком market regime мы теряем чаще?                            │
│  5. Slippage vs backtest assumptions: насколько сильно расходятся?   │
│  Output:                                                              │
│  - retro/<дата>-weekly-review.md (для пользователя)                  │
│  - PR с tuning предложениями для промптов субагентов                 │
│  - PR с обновлением risk-параметров если нужно                       │
└──────────────────────┬───────────────────────────────────────────────┘
                       │
┌─ Layer 6.5: Code Bug Detector (real-time + weekly) ──────────────────┐
│  Real-time: structured log analysis по lognum/severity               │
│  Weekly: pattern detection в crashes / WARNING-storms                │
│  Output: GitHub issues с диагнозом + suggested fix PRs               │
└──────────────────────────────────────────────────────────────────────┘
```

## 3. Layer 6.1: Trade Outcome Logger

### Расширение `OrderJournal` (SQLite)

Добавляем таблицу `trade_outcomes`:

```sql
CREATE TABLE IF NOT EXISTS trade_outcomes (
  trade_id           TEXT PRIMARY KEY,
  symbol             TEXT NOT NULL,
  side               TEXT NOT NULL,
  entry_time_ms      INTEGER NOT NULL,
  exit_time_ms       INTEGER,
  entry_price        TEXT NOT NULL,
  exit_price         TEXT,
  size               TEXT NOT NULL,
  pnl_usd            TEXT,
  pnl_pct            TEXT,
  exit_reason        TEXT,           -- TP1 / TP2 / SL / TIMEOUT / MANUAL / RISK_OFF
  holding_time_min   INTEGER,
  -- LLM context snapshot
  signal_candidate   TEXT NOT NULL,  -- JSON
  market_analyst     TEXT NOT NULL,  -- JSON, ответ субагента
  sentiment_analyst  TEXT NOT NULL,  -- JSON
  risk_overseer      TEXT NOT NULL,  -- JSON
  execution_optimizer TEXT NOT NULL, -- JSON
  coordinator        TEXT NOT NULL,  -- JSON
  macro_snapshot     TEXT,           -- JSON
  -- Performance metrics
  latency_decision_ms INTEGER,
  latency_execution_ms INTEGER,
  slippage_bps       TEXT
);
CREATE INDEX idx_outcomes_symbol ON trade_outcomes(symbol);
CREATE INDEX idx_outcomes_exit_reason ON trade_outcomes(exit_reason);
CREATE INDEX idx_outcomes_pnl ON trade_outcomes(pnl_pct);
```

### API

```python
class TradeOutcomeLogger:
    async def record_entry(self, trade_id: str, ctx: DecisionContext) -> None:
        """Сохраняет всё что привело к открытию сделки."""

    async def record_exit(self, trade_id: str, exit_data: ExitData) -> None:
        """Дополняет запись после закрытия. Триггерит auto-classify."""

    async def get_by_pattern(self, query_embedding: list[float], k: int = 3) -> list[TradeOutcome]:
        """Embedding similarity search для Past-Mistakes Context Injector."""
```

## 4. Layer 6.2: Mistake Library

### Auto-classification

После закрытия каждой убыточной сделки (PnL < 0) — LLM классификатор:

```
Дано: TradeOutcome {entry_ctx, exit_data, all subagent decisions}

Задача: классифицируй тип ошибки. Категории:
1. signal_wrong — Layer 2 сигнал был ложным
2. sentiment_wrong — sentiment indicator оказался не предсказательным
3. market_regime_changed — на момент входа было OK, regime сменился
4. slippage_high — execution price отклонился от expected на >2bps
5. risk_overlooked — субагенты пропустили red flag
6. execution_late — задержка между сигналом и ордером > 10 сек
7. tp_too_aggressive — цена дошла до 80% TP, развернулась
8. sl_too_tight — стоп выбило, потом цена пошла в нашу сторону
9. correlation_overlooked — открыли коррелированную позицию
10. macro_event_missed — торговали против важного события

Output JSON:
{
  "primary_category": "...",
  "secondary_categories": [...],
  "what_went_wrong": "1-2 строки",
  "what_we_should_have_seen": "...",
  "confidence_in_diagnosis": 0..1
}
```

**Стоимость:** ~$0.05 на убыточную сделку (Sonnet 4.6). При 30% win-rate и 60 сделок/мес = 42 убыточных × $0.05 = **$2.10/мес**.

### Mistake document template

`journal/mistakes/2026-XX-XX-<категория>-<short-id>.md`:

```markdown
# Mistake: <краткое название>

**Date:** 2026-05-15 14:32 UTC
**Trade ID:** abc123def
**Symbol:** BTC-USDT
**PnL:** -$487 (-0.51% equity)
**Category:** signal_wrong + market_regime_changed

## Что произошло

Long BTC от 80,500 на breakout сетапе. Цена пошла в SL на 79,800 за 23 минуты.

## Что упустили

Macro Analyst за час до входа отметил RISK_OFF (DXY +0.8%, VIX +12%).
Но Risk Overseer не учёл этот context при approve. Coordinator тоже
не пересмотрел composite confidence в свете macro.

## Урок

При RISK_OFF режиме breakout-сетапы имеют меньшую вероятность
успеха. Нужно либо:
- Risk Overseer должен иметь +20% threshold для breakout в RISK_OFF
- Или Coordinator должен снижать composite_confidence на 0.15
  если macro = RISK_OFF

## Фикс предложен

PR #XX — обновлены промпты Risk Overseer и Coordinator с учётом
macro_regime в их weights.

## Связанные mistakes

- 2026-04-22 (similar setup, similar mistake)
- 2026-03-15 (другая категория, но похожий контекст)
```

### Embedding similarity для retrieval

При новом decision Coordinator получает топ-3 похожих past mistakes:

```python
async def get_relevant_mistakes(current_signal: SignalCandidate,
                                 current_context: DecisionContext,
                                 k: int = 3) -> list[Mistake]:
    # Embed current context
    query_text = f"{current_signal.symbol} {current_signal.action} " \
                 f"market_state={current_context.market_state}"
    query_emb = await embed(query_text)

    # Cosine similarity vs all past mistakes embeddings
    return await mistake_library.search(query_emb, k=k)
```

**Embedding:** `voyage-3-lite` или `text-embedding-3-small` ($0.02/1M tokens — копейки). Локальная FAISS-индексация всех mistake embeddings.

## 5. Layer 6.3: Past-Mistakes Context Injector

Перед каждым Coordinator-вызовом:

```python
relevant_mistakes = await mistake_library.get_relevant(signal, context, k=3)

coordinator_prompt = f"""
... [обычный промпт coordinator]

PAST MISTAKES RELEVANT TO THIS SETUP:
{format_mistakes(relevant_mistakes)}

В свете прошлых ошибок — пересмотри своё мнение перед финальным
решением. Если этот сетап похож на mistake X — снизь confidence.
"""
```

**Эффект:** LLM **помнит** через retrieval, не через context window.

## 6. Layer 6.4: Weekly Review (research agent)

Запускается на paperclip раз в неделю (cron heartbeat).

### Что делает

```python
async def weekly_review() -> WeeklyReviewResult:
    trades = await get_trades_last_7_days()

    # 1. Aggregate stats
    by_signal_type = group_by(trades, "signal_type")
    by_market_regime = group_by(trades, "macro_snapshot.regime")
    by_subagent_decision = correlate(trades, "subagent_decisions")

    # 2. Find patterns в losses
    losses = [t for t in trades if t.pnl_pct < 0]
    loss_pattern_analysis = await opus_analyze(
        prompt="Найди общие паттерны в этих 12 убыточных сделках",
        trades=losses,
    )

    # 3. Find patterns в wins
    wins = [t for t in trades if t.pnl_pct > 0]
    win_pattern_analysis = await opus_analyze(
        prompt="Что общего у топ-3 прибыльных сделок? Воспроизводимо ли?",
        trades=wins,
    )

    # 4. Subagent accuracy analysis
    subagent_perf = analyze_subagent_predictions_vs_outcomes(trades)
    # → "Risk Overseer был прав в 73% approval cases"
    # → "Sentiment Analyst точность 41% — нужен тюнинг промпта"

    # 5. Slippage vs backtest
    slippage_analysis = compare_to_backtest_assumptions(trades)

    # 6. Generate retro doc + PRs
    write_retro(f"retro/{date}-weekly-review.md", findings)
    if needs_prompt_tuning(subagent_perf):
        create_pr_with_prompt_changes(subagent_perf)
    if needs_risk_param_changes(loss_pattern_analysis):
        create_pr_with_risk_changes(loss_pattern_analysis)
```

### Output

1. **`retro/<дата>-weekly-review.md`** — summary для пользователя
2. **GitHub PR** с предложениями (промпты, риск-параметры) — пользователь review + approve
3. **Telegram notification** — «weekly review готов, X PR на review»

### Стоимость

Opus 4.7 для глубокого анализа: ~$1-3 на review × 4 раза/мес = **$4-12/мес**.

## 7. Layer 6.5: Code Bug Detector

### Real-time

```python
# В core/observability/log_analyzer.py
class LogAnomalyDetector:
    """Sliding window анализ structured logs."""

    def on_log_event(self, event: LogEvent) -> None:
        if event.level == "ERROR":
            self.error_buffer.append(event)
            if self.is_anomaly_pattern(event):
                self.alert.send_critical(f"Anomaly: {event.summary}")

        if event.level == "WARNING":
            self.warning_buffer.append(event)
            if self.is_warning_storm():  # >10 warnings/min
                self.alert.send_warning("WARNING storm — investigate")
```

### Weekly bug pattern review

Часть Layer 6.4 weekly review:
- Анализ всех ERROR/WARNING за неделю
- Кластеризация по корневой причине
- Если новый класс bag → создать GitHub issue с диагнозом

### Bug fix workflow

1. Issue создан (auto или manual)
2. **В новой Claude-сессии** Claude видит issue → читает → диагностирует → пишет PR
3. Локально все CI gates → ты review → merge
4. **Никогда не auto-merge bug-fix PR** — слишком рискованно для денег

## 8. Бюджет Layer 6

| Компонент | Стоимость/мес |
|-----------|---------------|
| Trade Outcome Logger | ~$0 (просто SQL) |
| Mistake Library auto-classify | $2-5 (Sonnet, на каждую loss-сделку) |
| Embedding indexing | <$1 (voyage-3-lite или OpenAI small) |
| Past-Mistakes Context Injector | ~$0 (запросы к локальной FAISS) |
| Weekly Review (Opus) | $4-12 |
| Code Bug Detector | ~$0 (только log analysis) |
| **Total** | **$10-20/мес** |

В рамках общего LLM-бюджета $100-150/мес из плана #17 — небольшая добавка с большим возвратом.

## 9. Этапы реализации

### Фаза α: Storage extension (1 неделя)
- Schema миграция OrderJournal: + `trade_outcomes` table
- Backfill из текущих данных (если есть)
- Unit-тесты CRUD

### Фаза β: Trade Outcome Logger в hot path (1 неделя)
- Модификация `_handle_closed_candle` и `_handle_user_event`
- Сохранение subagent decisions при entry
- Сохранение exit context при close
- Integration tests на VST

### Фаза γ: Mistake Library (2 недели)
- Auto-classifier (LLM-based)
- Mistake document generator
- Embedding indexing (FAISS)
- Search API

### Фаза δ: Past-Mistakes Context Injector (1 неделя)
- Интеграция в Coordinator prompt
- A/B test: с injector vs без — измеряем PnL improvement

### Фаза ε: Weekly Review (2 недели)
- Research agent на paperclip
- Cron heartbeat
- PR generation
- Telegram notification

### Фаза ζ: Code Bug Detector (1 неделя)
- Log analyzer
- Anomaly patterns library
- GitHub issue automation

**Итого: 8 недель.** Идёт **параллельно** с другими этапами плана #17 (например, Layer 6 строится параллельно с Layer 1 интеграциями).

## 10. Метрики успеха

После 3 месяцев работы:

1. **Mistake repeat rate**: % случаев когда новая ошибка похожа на прошлую → должен **падать** месяц-к-месяцу.
2. **Subagent accuracy**: точность каждого субагента → растёт после PR с tuning промптов.
3. **Sharpe improvement**: Sharpe ratio до/после Layer 6 → ожидаем +0.2-0.5.
4. **Bug detection latency**: время от появления бага до GitHub issue → <24 часа.
5. **PR velocity**: количество self-generated improvement PR в месяц → 2-5.

Если за 3 месяца **mistake repeat rate не падает** — Layer 6 не работает, kill-switch.

## 11. Принципы

1. **Все subagent decisions логируются.** Без этого нет анализа.
2. **Mistake categories — закрытый список.** Иначе LLM выдумает 1000 категорий.
3. **Прошлые mistakes подаются в контекст via retrieval, не in-context training.** Это дешевле и точнее.
4. **Promt-tuning PRs — всегда review человеком.** Auto-merge запрещён для tuning.
5. **Weekly review — артефакт для пользователя.** Не «черный ящик», который сам себя обновляет.
6. **Не overlearn.** Если pattern встречен 1 раз — это шум. Только 3+ повторений = pattern.

## 12. Что НЕ делается

- ❌ Online RL — слишком сложно, нет данных, риск catastrophic forgetting
- ❌ Auto-merge improvement PRs — слишком опасно
- ❌ ML на trade outcomes — пока нет данных (вернёмся через 6 мес)
- ❌ Realtime hot-patching кода — стабильность важнее

## 13. Связанные документы

- [[plans/17-llm-composite-subagents]] — основная архитектура
- [[plans/16-деплой-24-7]] — operational
- [[бизнес/правила-торговли/анти-хедж-той-же-монеты]] — пример формализованного правила
- [[CLAUDE.md]] §«Поток работы» — после важной сессии — retro
- [[journal/]] — куда пишутся mistakes и weekly reviews

## 14. Главное

Без Layer 6 LLM-бот будет повторять одни и те же ошибки. Это **критично** для денег.

С Layer 6 каждая ошибка становится **активной памятью** которая влияет на все следующие решения. Через 3-6 месяцев у нас будет уникальный dataset который никто другой не имеет — наша **собственная торговая история с полным контекстом каждого решения**.

Это и есть «бот, который учится» — не через ML, а через структурированную retrospective.

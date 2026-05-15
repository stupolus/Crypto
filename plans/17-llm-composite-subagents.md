# План 17 — LLM Composite Analyzer + субагенты + research agent

**Дата:** 2026-05-12
**Статус:** первичный — план до кода
**Связано:** [[plans/00-стратегия-проекта-2026-05-09]] (фаза 1+), [[plans/01-bingx-адаптер]] (Layer 5), [[plans/16-деплой-24-7]] (production)

---

## 1. Контекст и решение

После того как D3 (rule-based стратегии на VST) подтвердил что инфра работает — переходим к **LLM-усиленной архитектуре** под капитал $100-200k.

**Ключевое изменение vs текущий бот:**
- Было: rule-based стратегии (Donchian/EMA/sessions) → ордер
- Будет: rule-based **сигналы как кандидаты** → LLM команда оценивает контекст → ордер

**Бот по-прежнему детерминирован для исполнения** (Layer 4 risk + Layer 5 execution). LLM влияет только на «брать сделку или нет», и не на объём.

## 2. 5-слойная архитектура

```
┌─ Layer 1: DATA INGESTION (real-time) ────────────────────────────────┐
│  TradingView webhooks (Pine alerts)                                  │
│  Coinglass API (heatmap, OI, funding, liquidations)                  │
│  BingX REST+WS (price, orderbook, наши позиции)                      │
│  Twitter (Apify scraper) → Groq classifier                           │
│  News API + RSS                                                      │
│  TG channels (свой парсер, plans/13 D5.1)                            │
│  On-chain (Glassnode / CryptoQuant)                                  │
│         │                                                            │
│         └─► Event Bus (Redis Streams для старта, Kafka позже)        │
└──────────────────────────┬───────────────────────────────────────────┘
                           │
┌─ Layer 2: SIGNAL GENERATION (rule-based, deterministic) ─────────────┐
│  signals/breakout/donchian.py     (наш ✓)                            │
│  signals/mean_reversion/extended.py                                  │
│  signals/liquidation_sweep.py                                        │
│  signals/funding_extreme.py                                          │
│  signals/order_flow.py                                               │
│  signals/session_breakout.py      (наш ✓)                            │
│                                                                      │
│  Каждый сигнал = SignalCandidate:                                    │
│    {symbol, action, confidence_raw, indicators_dict, timestamp}       │
└──────────────────────────┬───────────────────────────────────────────┘
                           │ если хоть один сигнал firing → дёргаем Layer 3
┌─ Layer 3: LLM COMPOSITE TEAM (субагенты) ────────────────────────────┐
│                                                                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │
│  │ MARKET      │  │ SENTIMENT   │  │ RISK        │  │ EXECUTION   │ │
│  │ ANALYST     │  │ ANALYST     │  │ OVERSEER    │  │ OPTIMIZER   │ │
│  │ (Sonnet 4.6)│  │ (Haiku 4.5) │  │ (Opus 4.7)  │  │ (Sonnet 4.6)│ │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘ │
│         └───────┬─────────┴───────┬─────────┘                │       │
│                 │                 │                          │       │
│            ┌────▼─────────────────▼────┐                     │       │
│            │   COORDINATOR (Opus 4.7)  │                     │       │
│            │   синтез всех мнений →    │                     │       │
│            │   final {action, confid}  │                     │       │
│            └────────────┬──────────────┘                     │       │
│                         └─────────────────┬───────────────────┘       │
│                                           │                          │
│                                  TradeProposal                       │
└──────────────────────────────────────────┬───────────────────────────┘
                                           │
┌─ Layer 4: RISK ENGINE (HARD rules — LLM НЕ обходит) ─────────────────┐
│  - Position sizing формула: 1% риск × equity / (entry - SL)          │
│  - Daily stop: -3% equity → блок до завтра                           │
│  - Weekly stop: -7% → пауза неделя + ретро                           │
│  - Monthly stop: -15% → СТОП проекта                                 │
│  - Max leverage: 5x effective                                        │
│  - Correlation cap: max 2 коррелированных позиций                    │
│  - Liquidation buffer: 50% от distance to liq                        │
│  - Если LLM просит size > limit → режется до limit, alert            │
└──────────────────────────┬───────────────────────────────────────────┘
                           │
┌─ Layer 5: EXECUTION (deterministic) ─────────────────────────────────┐
│  BingX adapter (наш ✓)                                               │
│  - place_order с attached SL/TP                                      │
│  - compensating-close если SL не подтверждён                         │
│  - User Data Stream для push fills                                   │
│  - Journal + metrics + reconcile                                     │
└──────────────────────────────────────────────────────────────────────┘
```

## 3. Субагенты — детализация

### 3.1 Market Analyst (Sonnet 4.6, ~$0.03/call)

**Вход:** свечи последних N периодов + индикаторы + текущий orderbook + funding/OI snapshot

**Промпт:**
```
Ты — quant-аналитик с 10 годами опыта. Анализируешь техническую картину.

Дано:
- Symbol: {symbol}
- TF: {timeframe}
- Candles last 50: {ohlcv_json}
- Indicators: ATR={atr}, Donchian high/low={dh}/{dl}, EMA20={e20}, EMA50={e50}
- Orderbook depth: bid_5={b5} ask_5={a5}, imbalance={imb}
- Funding rate now: {funding}
- OI 24h change: {oi_pct}

Задача: оцени текущий market state одним из:
- TRENDING_UP / TRENDING_DOWN
- RANGE_BOUND
- VOLATILE_NO_TREND
- BREAKOUT_PENDING
- BREAKDOWN_PENDING
- POST_BREAKOUT_FATIGUE

Также определи:
- Key levels: support/resistance в радиусе ±2 ATR
- Volatility regime: low/normal/high (vs последние 30 дней)
- Liquidity: нормальная / тонкая

Output JSON:
{
  "state": "...",
  "key_levels": {"support": [...], "resistance": [...]},
  "volatility": "...",
  "liquidity": "...",
  "notes": "1-2 строки на естественном языке"
}
```

### 3.2 Sentiment Analyst (Haiku 4.5, ~$0.005/call)

**Вход:** твиты за последний час (отфильтрованные Groq'ом по релевантности), новостные заголовки, funding extremes, TG-каналы агрегат

**Промпт:** аналогичный, выдаёт `{sentiment_score: -1..+1, key_events: [...], risk_flags: [...]}`

**Дешёвый Haiku** — потому что задача классификационная.

### 3.3 Risk Overseer (Opus 4.7, ~$0.10/call)

**Вход:** TradeProposal + текущий portfolio state + risk-engine state (daily PnL, open positions, correlation)

**Промпт:**
```
Ты — Chief Risk Officer хедж-фонда. Твоя задача — НЕ зарабатывать,
а защищать капитал. Должен критически оценить предложенную сделку.

Trade proposal: {signal + market + sentiment context}

Текущий state:
- Equity: {equity}
- Open positions: {positions}
- Daily PnL: {daily_pnl}
- Correlation matrix: {corr}
- Recent trades (last 10): {trades}

Задача: одобрить, отклонить или задать risk cap (меньше чем proposed).

Учти:
1. Не повторяем недавние ошибки (проверь recent trades)
2. Корреляция с открытыми позициями
3. Не превышаем daily/weekly/monthly limits
4. Sanity check: разумна ли entry vs current price?
5. Black swan чек: не торгуем во время известных high-impact событий

Output JSON:
{
  "approved": true|false,
  "max_risk_pct": 0.0..1.0,  // cap to risk engine, может быть < 1.0%
  "reasoning": "...",
  "concerns": [...],
  "confidence": 0..1
}
```

**Risk Overseer — единственный subагент с veto power.** Если он сказал no — не идём, даже если остальные «за».

### 3.4 Execution Optimizer (Sonnet 4.6, ~$0.02/call)

**Вход:** approved trade + текущий orderbook (5 уровней) + последние 20 минут price action

**Задача:** определить **оптимальную цену entry** (limit vs market) и **точное место SL/TP** с учётом spread/spread/microstructure.

**Output:**
```json
{
  "order_type": "MARKET" | "LIMIT",
  "limit_price": 80543.2,  // если LIMIT
  "stop_loss": 79800,      // строгая цена SL
  "take_profit_1": 81200,  // 1.5R
  "take_profit_2": 82000,  // trailing после TP1
  "reasoning": "..."
}
```

### 3.5 Macro Analyst (Sonnet 4.6, ~$0.04/call, раз в час)

**Вход:** макро-данные за последние 24ч — DXY, VIX, S&P futures, NDX, gold, oil, 10Y yield, FED calendar events. Источники из Layer 1: yfinance + FRED + EDGAR.

**Что делает:** определяет market regime для crypto-портфеля (RISK_ON / NEUTRAL / RISK_OFF / CRISIS). Кешируется на 1 час, hot-loop sub-agents видят последний macro snapshot.

**Output:**
```json
{
  "regime": "...",
  "confidence": 0..1,
  "rationale": "...",
  "portfolio_hedge_recommended": true|false,
  "hedge_size_pct_of_long_exposure": 0..50,
  "risk_off_drivers": [...],
  "duration_estimate_hours": ...
}
```

**Использование:** Coordinator + Risk Overseer получают macro-context при каждом decision. На RISK_OFF — Risk Overseer более строгий, на CRISIS — все лонги отклоняются.

### 3.6 Portfolio Hedger (Sonnet 4.6, ~$0.03/call, по событию)

**Не агент в classic смысле, а функция-эскалатор.** Срабатывает когда:
- Macro Analyst поставил `portfolio_hedge_recommended: true`
- Текущая crypto-длинная экспозиция > 50% от max risk budget
- Открытых hedge-шортов нет

**Что делает:** предлагает SHORT BTC (или ETH если уже есть SHORT BTC) размером 30-50% от суммарной long-delta. Передаёт в Risk Overseer для veto.

**ЖЁСТКОЕ ПРАВИЛО** (см. `бизнес/правила-торговли/анти-хедж-той-же-монеты.md`):

Hedge **НИКОГДА не открывается в том же символе** что существующая позиция в противоположную сторону. Если у нас Long BTC — hedge может быть Short ETH или Short SOL, но **НЕ Short BTC**.

Это страховка для **портфеля**, не для **отдельной позиции**. Same-asset «зелёный хедж» = заморозка убытка + двойной funding. Запрещён на 3 уровнях:
1. Code-level в Layer 4 (RuleViolation exception)
2. Risk Overseer prompt-level (veto)
3. Portfolio Hedger sym-selection logic

### 3.7 Coordinator (Opus 4.7, ~$0.08/call)

**Вход:** все ответы от Market + Sentiment + Risk Overseer + Execution Optimizer

**Задача:** синтезировать в финальное решение. Это **последний gate** перед Layer 4.

```
Получил мнения 4 субагентов. Синтезируй финальное решение.

Рулз:
1. Если Risk Overseer сказал НЕТ — финальный ответ HOLD.
2. Если Sentiment сильно negative (< -0.5) и Market в BREAKDOWN_PENDING — увеличь caution.
3. Composite confidence = взвешенное среднее всех confidences (Risk Overseer вес 2x).
4. Если composite confidence < 0.6 — HOLD.

Output:
{
  "action": "BUY|SELL|HOLD",
  "size_risk_pct": 0..2.0,  // <= max_risk_pct от Risk Overseer
  "entry_price": ...,
  "sl_price": ...,
  "tp_prices": [...],
  "reasoning": "...",  // на русском, для журнала + телеграм
  "composite_confidence": 0..1
}
```

## 4. Бюджет API на месяц

Предположим **15 сигналов/неделя × 4 символа** = 60 сигналов/мес.

| Агент | Модель | $/call | Calls/мес | $/мес |
|-------|--------|--------|-----------|-------|
| Market Analyst | Sonnet 4.6 | 0.03 | 60 | 1.80 |
| Sentiment Analyst | Haiku 4.5 | 0.005 | 60 | 0.30 |
| Risk Overseer | Opus 4.7 | 0.10 | 60 | 6.00 |
| Execution Optimizer | Sonnet 4.6 | 0.02 | 60 | 1.20 |
| Macro Analyst | Sonnet 4.6 | 0.04 | 720 (1/час) | 28.80 |
| Portfolio Hedger | Sonnet 4.6 | 0.03 | ~5 (по событию) | 0.15 |
| Coordinator | Opus 4.7 | 0.08 | 60 | 4.80 |
| **Hot loop + Macro итого** | | | | **~$43/мес** |

**Дополнительно:**
- Twitter/News classification через Groq: ~$10-20/мес (зависит от объёма)
- Research agent (paperclip, отдельно): ~$50-100/мес
- Periodic regime analyzer (раз в час Sonnet): ~$30/мес

**Total monthly LLM budget: ~$100-150**

При капитале $100k и edge 10%/year — это $25/мес операций, окупается легко.

## 5. Research Agent (paperclip.ing)

Отдельно от hot loop. Задачи:

1. **Market regime monitor** (раз в день).
   - Анализирует overall crypto market: BTC dominance, total cap, alt seasons indicator
   - Вывод: regime для бота (`bull / bear / range / panic`) — фильтр для всех сделок

2. **Hypothesis generator** (раз в неделю).
   - Смотрит на последние сделки, ищет паттерны "что работало / не работало"
   - Предлагает новые гипотезы стратегий
   - Создаёт `plans/<следующий>-<идея>.md` для review человеком

3. **News/event aggregator** (постоянно).
   - Подписан на crypto news feeds
   - Группирует события, классифицирует impact (low/med/high/critical)
   - При CRITICAL событии — алертит в Telegram немедленно

4. **Performance analyzer** (раз в неделю).
   - Анализирует trades за неделю
   - Находит ошибки в LLM-решениях ретроспективно
   - Генерирует tuning suggestions для промптов субагентов

**Хост на paperclip:** их UI даёт пользователю dashboard всех агентов, бюджеты, аудит. Задачи запускаются по cron (heartbeats).

## 6. Data flow (concrete пример)

```
00:15:00  TradingView Pine alert: BTC-USDT donchian_breakout
          → POST /webhook → Layer 1 → Event Bus
          
00:15:01  Layer 2 detects SignalCandidate{BTC, BUY, conf=0.7}
          → Layer 3 dispatch
          
00:15:01  Layer 3 параллельно зовёт:
          - Market Analyst (~2 сек)
          - Sentiment Analyst (~0.5 сек, Haiku быстрее)
          - Risk Overseer (~3 сек)
          
00:15:04  Все ответили → Coordinator (~3 сек)
          → TradeProposal{BUY, size=0.8% risk, entry=80500, sl=79800, tp1=81200}
          
00:15:07  Layer 4 Risk Engine validates:
          - daily_pnl OK (-1.2%, ниже -3% лимита)
          - position_size 0.8% < cap 1% ✓
          - SL distance OK (700 pts = 0.87%)
          - liquidation buffer OK
          → APPROVED
          
00:15:07  Layer 5 Execution:
          - place_order(BUY, BTC-USDT, qty=..., type=LIMIT@80500, SL=79800)
          - log в journal
          
00:15:08  TG: "📈 BUY BTC @ 80500, SL 79800, size 0.8% — donchian breakout + bullish sentiment"
```

**Total decision-to-order latency: ~7-8 секунд.** Допустимо для 15m TF.

## 7. Реализация — этапы

### Фаза A: Foundation (2 недели)
- `core/agents/` директория
- `BaseAgent` интерфейс (асинхронный prompt → JSON response)
- `AgentRegistry` для DI
- Unit-тесты с моками Anthropic
- `core/agents/coordinator.py` — синтез
- Mock-режим (без реальных API-вызовов) для разработки

### Фаза B: Прототипы агентов (3 недели)
- `core/agents/market_analyst.py` + промпт + тесты
- `core/agents/sentiment_analyst.py` + Groq клиент
- `core/agents/risk_overseer.py` + интеграция с RiskEngine
- `core/agents/execution_optimizer.py` + orderbook depth парсер
- `core/agents/coordinator.py` (полная имплементация)

### Фаза C: Layer 1 интеграции (3 недели)
- `parsers/tradingview/webhook.py` — FastAPI endpoint
- `parsers/coinglass/adapter.py` — REST + heatmap
- `parsers/twitter/apify_scraper.py` — Twitter ingestion
- `core/groq_client.py` — wrapper для Groq inference
- `parsers/news/aggregator.py` — RSS + News API

### Фаза D: Layer 2 расширение (1 неделя)
- `signals/liquidation_sweep.py`
- `signals/funding_extreme.py`
- `signals/order_flow.py`

### Фаза E: Integration (2 недели)
- `runners/llm_composite_runner.py` — заменяет live_runner для LLM-режима
- E2E тесты на mock'ах
- Rate limiting + circuit breakers (если Anthropic API лежит — fallback на rule-only)

### Фаза F: Backtesting LLM (2 недели)
- Симулятор: подаём исторический контекст в LLM, оцениваем решения
- **Дорого** ($2-3k за 6 мес backtest), но необходимо
- Сравнение с rule-only базовой линией

### Фаза G: Paper trading (4 недели)
- На live данных, симулированные ордера
- Накапливаем реальную статистику LLM решений
- Тюнинг промптов

### Фаза H: $5-10k live demo (4 недели)
- Маленькие позиции, реальные деньги
- Проверка slippage / fills / latency
- Сравнение с paper trading

### Фаза I: Постепенный scale (8 недель)
- Раунды по $20-30k каждые 2 недели
- Только если PnL положителен в предыдущем раунде

**Всего: ~7 месяцев от сегодня до $100k+ live.**

## 8. Что НЕ делается в этом плане

- ❌ Multi-exchange (BingX + Bybit + ...) — фаза 4+
- ❌ ML-модели (классические) — после года работы LLM
- ❌ Высокочастотный трейдинг (<5 мин TF) — никогда (см. CLAUDE.md правило)
- ❌ Replicator/copy-trading — не наша игра
- ❌ Token launches / IDO — не торгуем

## 9. Риски (10 причин провала)

1. **LLM теряет edge при апдейтах модели.** Митигация: version-pin модели, тестирование каждого update.
2. **Anthropic API outage.** Митигация: fallback на rule-only режим при API down >5 мин.
3. **Hallucination в критичный момент.** Митигация: Risk Overseer veto + cap на confidence.
4. **Стоимость LLM растёт со временем.** Митигация: Haiku где можно, prompt caching.
5. **Twitter API дорожает / блокируется.** Митигация: 2-3 источника параллельно (Apify + Nitter + готовый агрегатор).
6. **Регуляторика крипто меняется.** Митигация: модульная архитектура, можно отключить отдельные источники.
7. **BingX блокирует страну.** Митигация: multi-exchange после фазы 4.
8. **Edge не воспроизводится на live.** Митигация: kill-switch — Sharpe < 1.0 за 8 недель = откат к rule-only.
9. **Психология: соблазн вмешаться вручную.** Митигация: автоматизация = нет рук, правило «не лезть».
10. **Catastrophic loss при black swan.** Митигация: daily/weekly/monthly stops + diversification + не более 5x leverage.

## 10. Decisions требуемые от пользователя до старта

1. ✅ Архитектура (5 layers + субагенты + research) — одобрена
2. ⏳ Twitter source: Apify ($50/мес) или другое?
3. ⏳ Coinglass tier: Standard ($29) для тестов, Pro ($129) для prod — когда?
4. ⏳ TradingView: Premium для webhook'ов — когда?
5. ⏳ paperclip регистрация: ты или я?
6. ⏳ Anthropic API ключ: отдельный от чата (биллинг отдельно)
7. ⏳ Groq API ключ: дашь
8. ⏳ News API: NewsAPI.org ($449/мес) или RSS-only бесплатно?
9. ⏳ On-chain: Glassnode ($30/мес базовый) или CryptoQuant?
10. ⏳ Бюджет на LLM-бэктесты: $5-10k одноразово на 3-4 месяца тестов

## 11. Главное

Этот план — **большой**, рассчитан на 7 месяцев. Но он строится **поверх** уже работающей инфры:

- BingX adapter ✓
- Risk engine ✓
- Backtest engine ✓ (для Layer 2 валидации)
- Live runner ✓
- Telegram alerts ✓

Каждая фаза — отдельный PR с валидацией. **D3 продолжает работать в течение всего этого срока**, накапливает baseline статистику для сравнения.

LLM-композит **не заменяет** проверенные стратегии — **усиливает** их через многоисточниковый контекст и risk overseer.

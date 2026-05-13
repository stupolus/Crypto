# Ретро сессии 2026-05-13 — VPS production deploy

**Дата:** 2026-05-13
**Тема:** деплой D3 demo на VPS в Docker + закрытие архитектурных планов на 7 месяцев
**Контекст:** продолжение сессии 2026-05-12 (запуск D3 в sandbox среде + написание архитектуры).

---

## 1. Главное достижение

**D3 demo работает 24/7 на Hostinger VPS в production среде.**

3 контейнера (BTC/ETH/XRP USDT) с btc_breakout стратегией на VST. Auto-restart при крэше через `docker compose restart: unless-stopped`. Telegram алерты на телефон пользователя. Логи через `journalctl`. Изоляция от Odoo ERP на том же VPS (resource limits, отдельная network, non-root, read-only FS).

---

## 2. Хронология PR'ов (52 за две сессии, #41-52)

| PR | Тема | Влияние |
|----|------|---------|
| #41 | TelegramAlerter: реальный POST в Bot API | Алерты на телефон |
| #42 | Retro 2026-05-12 | Документация |
| #43 | Plan 16: деплой 24/7 | План VPS-инфры |
| #44 | Deploy scripts: install.sh + systemd | Чистый VPS вариант |
| #45 | Фикс Telegram .env loading | Критичный баг alerter |
| #46 | Plan 17: LLM Composite + субагенты (7 мес roadmap) | Архитектура на 7 месяцев |
| #47 | Twitter аккаунты (~57 в 5 тирах) | Sentiment Layer 1 |
| #48 | Backlog: Perplexity, Bloomberg отложены | Решения зафиксированы |
| #49 | Анти-хедж + Macro Analyst + Portfolio Hedger | Правило проекта + субагенты |
| #50 | Plan 18: Layer 6 Post-Mortem & Learning | Бот учится на ошибках |
| #51 | Docker deploy (для VPS с другими сервисами) | Изоляция + resource limits |
| #52 | Фикс Docker healthcheck (heartbeat вместо metrics) | На CI, готов к мержу |

---

## 3. Архитектурные решения сегодня

### 3.1 LLM-композит вместо одного LLM-вызова

Пользователь подкинул идею субагентов — она оказалась правильной. Архитектура:

```
Layer 3 LLM TEAM:
  Market Analyst (Sonnet 4.6) — техническая картина
  Sentiment Analyst (Haiku 4.5) — Twitter + news + funding
  Risk Overseer (Opus 4.7) — veto power на сделку
  Macro Analyst (Sonnet 4.6) — DXY/VIX/S&P → market regime
  Portfolio Hedger (Sonnet) — cross-asset хеджи (не той же монеты!)
  Execution Optimizer (Sonnet) — entry/SL/TP уточнение
  Coordinator (Opus 4.7) — синтез финального решения
```

Бюджет ~$43/мес (hot loop + macro), ~$100-150/мес с research agent на paperclip.

### 3.2 Multi-asset через макро-контекст

Пользователь упомянул: фьючерсы на акции, золото, нефть, COMEX, инвесторские отчёты. Решение:

- Сейчас (фаза 1): крипто на BingX, **но макро-контекст в Layer 3 через бесплатные источники** (yfinance, FRED, EDGAR, CME delayed). Улучшает crypto-сигналы без расширения торговых инструментов.
- Фаза 2 ($100k+): RWA-перпы на BingX (золото, индексы — тот же адаптер!).
- Фаза 3 ($500k+): отдельный брокер для real stock futures (IBKR).
- Фаза 4 ($1M+): полный multi-asset, dedicated data feeds.

### 3.3 Twitter + Groq архитектура

Пользователь дал Telegram токен. Также упомянул Groq для парсинга Twitter. Уточнили: Groq — это inference платформа (Llama 3.1 70B быстро), Twitter — это data source (Apify $50/мес рекомендован).

Pipeline: Apify → Groq classifier → SentimentSnapshot → Sentiment Analyst (Layer 3).

Курируемый список 57 аккаунтов в 5 тирах: Vitalik/CZ/Saylor/Trump/Powell (T0), Wu Blockchain/The Block/Bloomberg (T1), Glassnode/lookonchain/whale_alert (T2), Bianco/El-Erian/Lyn Alden (T3), CryptoCred/Hsaka/Cobie (T4).

### 3.4 Анти-хедж той же монеты — жёсткое правило

Пользователь предложил: при падении открывать обратную позицию, при возврате — закрыть обе. Это **классическая ловушка** ритейлера: математически блокирует убыток на текущем уровне + добавляет funding на обе стороны.

Записано как правило проекта (`бизнес/правила-торговли/анти-хедж-той-же-монеты.md`) с enforcement на 3 уровнях:
1. Layer 4 code-level (RuleViolation exception)
2. Risk Overseer prompt-level (veto)
3. Portfolio Hedger sym-selection logic

Разрешён правильный хедж: cross-asset (long-strong / short-weak), portfolio-level (short BTC поверх лонгов при RISK_OFF), options OTM puts (фаза 3+).

### 3.5 Layer 6 — Post-Mortem & Learning

Без этого бот повторяет ошибки. Архитектура:
- Trade Outcome Logger (расширенная SQLite схема с полным LLM-контекстом каждого решения)
- Mistake Library (auto-classify + embedding retrieval)
- Past-Mistakes Context Injector (RAG в Coordinator)
- Weekly Review (Opus на paperclip → auto-PR с tuning промптов)
- Code Bug Detector (real-time log analysis + GitHub issues)

Бюджет $10-20/мес. Реализация 8 недель параллельно с Layer 1.

### 3.6 Решено пропустить (с обоснованием)

- **Perplexity** — hot loop не нуждается (есть Claude/Groq), возможен в research agent позже.
- **Bloomberg Terminal** — $24k/год, фаза 4+ (>$1M depo).
- **Классическое ML сейчас** — нет данных, неэффективно. Через год торговой истории — да.
- **Real-time hot-patching кода** — слишком опасно для денег.

---

## 4. Боевой деплой на VPS (история)

### Препятствия преодолены

1. **VPS уже занят** — Odoo + Postgres + 7 других контейнеров на Hostinger
   → решение: Docker-контейнеры с изоляцией (resource limits, read-only FS, отдельная network, cap_drop ALL)
2. **VPS принимает только SSH-ключ** — пользователь не имел ключа
   → сгенерили на MacBook, через Hostinger Browser Terminal добавили в authorized_keys
3. **Репо приватный** — git clone требовал пароль
   → создали read-only SSH deploy key (vps-crypto-bot), добавили на GitHub
4. **Mac auto-bracketing URL** в paste-операциях
   → `sed -i 's/[<>]//g'` для cleanup config, `printf '\n'` вместо heredoc
5. **Browser Terminal disconnects** — Hostinger веб-терминал прерывает сессию
   → используем SSH с Mac когда стабильно, Browser Terminal как backup
6. **SSH timeout** после нескольких failed attempts
   → fail2ban временно блокирует IP, ждём 10-15 мин ИЛИ Browser Terminal
7. **`(unhealthy)` контейнеры после успешного деплоя** — false alarm
   → фикс в PR #52: heartbeat-файл вместо metrics.jsonl freshness

### Финальные параметры production

| Метрика | Значение |
|---------|----------|
| VPS | Hostinger 187.124.41.13 / erp-exemera.cloud |
| OS | Ubuntu 25.10 |
| Docker | 29.3.0 |
| Контейнеры | crypto-btc, crypto-eth, crypto-xrp |
| Образ | crypto-bot:latest (multi-stage slim) |
| Resource limits | 0.5 CPU + 512MB RAM × 3 |
| Network | crypto-net (изолирована от Odoo) |
| Volume | crypto-data:/var/lib/crypto |
| Telegram | @Cryptoopus_bot → chat 239373620 |
| BingX env | VST (testnet, $99999.9365) |
| Стратегия | btc_breakout, 15m TF |

---

## 5. Что закрыли по плану vs что отложили

### Закрыли в эту сессию

- ✅ Production деплой на VPS
- ✅ Telegram алерты end-to-end (verified: 3 "runner starting" arrived)
- ✅ Архитектура на 7 месяцев (планы #16-#18)
- ✅ Twitter accounts список
- ✅ Анти-хедж правило проекта
- ✅ Docker isolation от Odoo ERP

### Открытые задачи (для следующей сессии)

1. **Применить PR #52 на VPS** — `git pull && docker compose up -d` после мержа healthcheck-фикса
2. **Иmплементация Layer 6** (8 недель, Post-Mortem & Learning)
3. **Стартовать Layer 1 интеграции:**
   - Twitter source (Apify $50/мес) когда пользователь решит
   - Coinglass API ключ
   - TradingView Premium для webhook'ов
   - Groq API ключ (есть у пользователя)
   - paperclip регистрация (research agent)
4. **Subagent skeleton** — `core/agents/` с base classes
5. **Watchtower disable label** — добавить чтобы Watchtower не auto-обновлял наши контейнеры

---

## 6. Что важно для следующей сессии

### Состояние на 2026-05-13 22:50 UTC

- D3 на VPS работает: 3 контейнера up, Telegram алерты ✓
- Сигналов btc_breakout пока нет (рынок в range)
- Equity: $99999.9365 (никаких сделок не было)
- Все 12 PR смержены, PR #52 на CI

### Команды мониторинга на VPS

```bash
# Из SSH:
cd /opt/crypto-bot
docker compose -f scripts/deploy/docker-compose.yml ps          # статус
docker compose -f scripts/deploy/docker-compose.yml logs -f      # live логи
docker logs crypto-btc | grep "candle closed" | tail -5         # последние closes
docker stats --no-stream crypto-btc crypto-eth crypto-xrp       # resource usage
```

### Когда увидим первый сигнал

`btc_breakout` ждёт `close > donchian_upper` или `close < donchian_lower` за последние 20 свечей (5 часов). На текущем range BTC 80k ± 1k, ETH 2270 ± 30, XRP 1.44 ± 0.03 — пока далеко. Сигнал ожидаем при сильном movement >2% за час.

### Решения требуемые от пользователя до старта Layer 1

1. Twitter source: Apify ($50/мес) или другое?
2. Coinglass tier (Standard $29 / Pro $129)?
3. TradingView Premium для webhook'ов
4. Groq API ключ (есть)
5. paperclip регистрация (research agent)
6. Anthropic API ключ отдельный для бота
7. Бюджет на LLM-бэктесты: $5-10k одноразово
8. NewsAPI ($449/мес) или RSS-only бесплатно

---

## 7. Метрики двух сессий

| Метрика | 2026-05-12 | 2026-05-13 | Итого |
|---------|-----------|-----------|-------|
| PR смержено | 7 (#35-#42) | 5 (#41-#51) | 12 |
| Unit-тестов | 183 → 198 | 198 (stable) | 198 |
| Стратегий walk-forward | iter#1,#3,#4 ✓ | — | 3 |
| Деплой среда | sandbox | VPS production | ✓ |
| Telegram алерты | wire | live verified | ✓ |
| Архитектурных планов | — | 3 (#16, #17, #18) | 3 |

---

## 8. Главное

**Бот работает в production.** Дальше — это либо ждать когда стратегия даст сигнал на VST (несколько дней-недель), либо начинать имплементацию Layer 1 (Twitter/Coinglass/Macro source).

D3 demo рассчитан на 4 недели. После него — решение по реальному capital.

Архитектура на 7 месяцев расписана детально. Параметры известны. Бюджеты понятны. Что от пользователя нужно — записано.

**Перевод от "пишем код" к "наблюдаем и итеративно улучшаем"** — это и есть успех фазы D3.

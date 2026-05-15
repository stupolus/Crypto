# Twitter (X) аккаунты для трекинга — курируемый список

**Дата:** 2026-05-12
**Цель:** какие аккаунты парсить через Apify → классифицировать через Groq → подавать в Sentiment Analyst (Layer 3)
**Связано:** [[plans/17-llm-composite-subagents]] §3.2

## Принцип отбора

1. **Влияние > болтливость.** Один твит CZ или Vitalik двигает рынок сильнее чем 100 твитов рандомного инфлюенсера.
2. **Сигнал > мнение.** Аккаунты которые **сообщают факты** (CoinDesk, on-chain analytics, биржевые announce'ы) — выше приоритет чем аналитики.
3. **Скорость > глубина.** В hot loop важна реакция первой минуты. Лонгриды и threads — для research agent'а отдельно.
4. **Фильтр Groq'ом.** Не все твиты с этих аккаунтов важны. Groq классифицирует: relevant / noise / spam.

## Тиры

### TIER 0 — Критическое влияние (~10 аккаунтов)

Это аккаунты, **один твит которых может двигать рынок на 1-5%** в моменте. Полная подписка, любой их твит = немедленный анализ.

| Handle | Кто | Почему |
|--------|-----|--------|
| `@VitalikButerin` | Co-founder Ethereum | Любое заявление по ETH/scaling = market move |
| `@cz_binance` | Ex-CEO Binance, ещё активен | Глубокий market mover |
| `@brian_armstrong` | CEO Coinbase | Регуляторика, листинги, breaking |
| `@saylor` | Michael Saylor (Strategy / MSTR) | BTC treasury, корпоративный adoption |
| `@elonmusk` | Илон Маск | DOGE, периодически BTC |
| `@realDonaldTrump` | Дональд Трамп | Регуляторика, государственный BTC stockpile |
| `@SECGov` | SEC official | Regulatory, ETF approvals/rejections |
| `@federalreserve` | Federal Reserve | Macro, rate decisions |
| `@jpowell` (если активен) | Jerome Powell, Fed Chair | Macro |
| `@JustinSunTron` | Justin Sun (Tron) | Опасный, но влиятельный |

**Action на твит:** немедленный анализ Groq → если sentiment shift > 0.3 → push в Layer 3 → возможный exit/reversal.

### TIER 1 — Crypto Native News & Breaking (~15 аккаунтов)

Журналисты и медиа которые **первыми публикуют breaking news**. Часто опережают официальные пресс-релизы на 5-30 мин.

| Handle | Кто | Профиль |
|--------|-----|---------|
| `@WuBlockchain` | Wu Blockchain (Colin Wu) | Asia-focused, часто первый в Bybit/OKX/Binance Asia events |
| `@DocumentingBTC` | BTC events compiler | Митинг ETF inflows, hash rate |
| `@TheBlock__` | The Block (media) | Industry news |
| `@CoinDesk` | CoinDesk | Mainstream crypto media |
| `@cointelegraph` | Cointelegraph | High volume — много шума, но иногда breaking |
| `@DBCrypto` | DB Crypto Research | Hedge fund flows, OTC desk reports |
| `@unusual_whales` | Unusual options flows | Не крипто, но коррелирует с crypto risk-on/off |
| `@WatcherGuru` | Watcher Guru | Breaking + macro headlines |
| `@CoinMarketCap` | CMC | Listings, новые токены |
| `@FoxBusiness` (crypto reporters) | Eleanor Terrett, Charles Gasparino | Regulatory leaks |
| `@BloombergCrypto` | Bloomberg crypto | Institutional perspective |
| `@TheStreetCrypto` | TheStreet | Mainstream finance + crypto |
| `@CryptoTwitter` (compilation) | CT highlights | Aggregator |
| `@BitcoinNewsCom` | Breaking BTC news | High volume |
| `@Reuters` (crypto часть) | Reuters | Wire service, минимальный bias |

### TIER 2 — On-chain Analytics & Whale Tracking (~12 аккаунтов)

Источники **on-chain данных**: large transfers, exchange flows, whale movements, miner activity.

| Handle | Кто | Что |
|--------|-----|-----|
| `@whale_alert` | Whale Alert | Large transfers (>$10M) — automated |
| `@lookonchain` | Lookonchain | Smart money flows, whale wallets |
| `@spotonchain` | Spot On Chain | Whale wallets + DEX activity |
| `@glassnode` | Glassnode | Daily on-chain metrics threads |
| `@cryptoquant_com` | CryptoQuant | Exchange flows, miner positions |
| `@santimentfeed` | Santiment | On-chain + social sentiment |
| `@checkmatey_` | Checkmate (Glassnode lead analyst) | Deep on-chain analysis threads |
| `@_pinda` | Pinda | Active wallet tracking |
| `@MartyParty` | MartyParty | Macro + on-chain |
| `@mononautical` | Mononaut (mempool.space) | Mempool, BTC fees, miner behavior |
| `@MEVStocktail` | MEV detection | DEX/sandwich attacks |
| `@etherscan` | Etherscan | Network status, gas |

### TIER 3 — Macro & Cross-Asset (~10 аккаунтов)

Макро-аккаунты которые **drive risk-on / risk-off**. Crypto коррелирует с tech / equities / DXY.

| Handle | Кто | Почему |
|--------|-----|--------|
| `@zerohedge` | ZeroHedge | Macro narratives, market panic detection |
| `@LizAnnSonders` | Liz Ann Sonders (Schwab CIO) | Quality macro |
| `@biancoresearch` | Jim Bianco | Bond market, Fed |
| `@elerianm` | Mohamed El-Erian | Macro economist |
| `@RaoulGMI` | Raoul Pal | Crypto-friendly macro |
| `@LynAldenContact` | Lyn Alden | BTC + macro thesis |
| `@PeterSchiff` | Peter Schiff (BTC bear) | Anti-crypto perspective — useful for contrarian read |
| `@LTCG_Capital` | Long Term Capital | Quality investor |
| `@MichaelGoldstein` | Bitstein | BTC philosophy |
| `@DocumentingBTC` | Documenting BTC | Already in T1 |

### TIER 4 — Trading Twitter (selective) (~10 аккаунтов)

**Осторожно:** многие на crypto Twitter — шум / шиллинг. Эти выбраны за **долгую track record и проверяемые позиции**.

| Handle | Кто | Профиль |
|--------|-----|---------|
| `@CryptoCred` | CryptoCred | Чистый TA, без шиллинга |
| `@hsakatrades` | Hsaka | Quant trader, рынок-нейтральный |
| `@CryptoCondom` | CryptoCondom | Fundamentals + risk discipline |
| `@AltcoinPsycho` | Altcoin Psycho | Active trader, transparent |
| `@CryptoKaleo` | Kaleo | Actionable calls (не всегда правильные) |
| `@SmartContracter` | Smart Contracter | TA + fundamentals |
| `@inversebrah` | Inversebrah | Sentiment indicator (когда крипто-хомяки в одной стороне — обратная) |
| `@CryptoCobain` | Cobie | Ex-trader, инфо иногда первый |
| `@CryptoBitlord` | Bitlord | Fundamentals |
| `@TraderXO` | Trader XO | Disciplined, charts |

### TIER 5 — Project-specific (динамический список)

**Для каждой монеты в портфеле — отдельный список.** Например для BTC:
- `@BTCKing555`
- `@MaxKeiser`
- `@adam3us` (Adam Back, Blockstream)

Для ETH:
- `@drakefjustin` (Justin Drake, EF researcher)
- `@dankrad` (Dankrad Feist)
- `@TimBeiko` (ETH client coordination)

Для XRP:
- `@bgarlinghouse` (Brad Garlinghouse, CEO Ripple)
- `@JoelKatz` (David Schwartz, CTO Ripple)

Этот тир **обновляется** когда меняется состав портфеля.

## Что НЕ трекать

- ❌ Анонимные «инсайдер» аккаунты с большим followers и нулевым track record — 99% шум
- ❌ Pump-and-dump каналы / Telegram-связки
- ❌ NFT-инфлюенсеры (отдельный мир, не наш фокус)
- ❌ AI/tech generic аккаунты без crypto-фокуса (в первой итерации)
- ❌ Memecoin-only аккаунты

## Pipeline обработки (Layer 1 + Groq)

```
Apify Twitter Scraper
  ├─ Polling каждые 60 сек
  ├─ ~57 аккаунтов в подписке
  ├─ Filter: только tweets за последний час, не RT
  └─ Output: ~50-200 твитов/час (зависит от активности)
       │
       ▼
Groq classifier (Llama 3.1 70B / 8B)
  ├─ Параллельно по 10 твитов
  ├─ Промпт: "классифицируй tweet → JSON"
  ├─ Output:
  │     {
  │       "relevance": "high|medium|low|noise",
  │       "sentiment": -1.0..+1.0,
  │       "mentioned_tokens": ["BTC", "ETH"],
  │       "is_breaking": true|false,
  │       "summary": "1 предложение"
  │     }
  └─ Cost: ~$0.0001 per tweet → $1-2/месяц
       │
       ▼
Aggregator
  ├─ За окно 1ч / 4ч / 24ч:
  │   - average sentiment per token
  │   - count of breaking news
  │   - top mentioned tokens (volume of mentions)
  └─ Output: SentimentSnapshot per token
       │
       ▼
Sentiment Analyst (Haiku 4.5) — Layer 3
  └─ Получает SentimentSnapshot + final read для Coordinator
```

## Метрики качества списка

После 2-4 недель работы оцениваем:

1. **Hit rate** — сколько твитов из tier 0/1 реально предшествовали движению (>1% за 1 час)
2. **Noise ratio** — сколько % твитов классифицируется как "noise"/"low" — если >70%, аккаунт можно убрать
3. **Latency** — за сколько мс мы получаем твит после публикации (target: <60 сек)

## Эволюция списка

- Раз в месяц **research agent** (paperclip) делает анализ:
  - Какие аккаунты добавить (на основе crosslinks от tier 0)
  - Какие убрать (низкий hit rate)
  - Авто-предлагает изменения в этот файл через PR

## Не входит в этот файл (отдельные источники)

- **TG-каналы** — отдельный список в `бизнес/материалы/каналы/`
- **YouTube каналы** — для долгосрочного research (видео → Whisper → выжимки), не hot loop
- **Crypto Discord servers** — пока не парсим
- **Reddit** — слишком шумно, не добавляем

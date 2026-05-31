# Web-источники — реестр

Публичные веб-сервисы как источники сигналов и данных для исследования
стратегий. **Только описания и доступ**, парсеры и интеграция — отдельным
планом в `plans/` после явного «да» владельца.

Принципы (CLAUDE.md):
- Если источник предоставляет сигнал — он проходит конвейер: гипотеза →
  данные → edge (OOS+WF+cost) → правило. Сырой сигнал в live-вход нельзя.
- Если источник предоставляет данные — оформляется парсер с тестами и
  кешированием, как Coinglass/Yahoo.

---

## 1. OpenInsider — http://openinsider.com/

**Что:** Свободный публичный агрегатор SEC Form 4 (US insider buys/sells
публичных компаний). Альтернатива прямому парсингу EDGAR — данные
сгруппированы, отсортированы, есть фильтры.

**Доступ:** бесплатно, без auth. HTML-страницы (парсить через
`urllib`/`requests` + BeautifulSoup или встроенный CSV-экспорт по
конкретным фильтрам).

**Формат данных:**
- Insider name + role (CEO, CFO, Director, 10% owner, etc.).
- Transaction type (P=buy, S=sell, F=tax, etc.).
- Date + shares + price + value.
- Per-ticker history.

**Релевантность проекту:**
- **План 48 (insider/13F-фильтр)** — это **готовый источник Form 4**
  без необходимости парсить EDGAR. Закрывает фазу 48.1 (данные)
  по части инсайдеров. Для 13F-агрегации нужен отдельный источник
  (WhaleWisdom / собственный парсер EDGAR).
- **Стратегии на BingX TradFi-перпах** (NCSKTSLA/NCSKNVDA/NCSKGOOGL/...):
  cluster-buying у CEO/CFO — потенциальный фильтр для long-entry. Cluster
  selling — для short-side / risk-off.
- **GTAA equity-legs overlay** (NCSISP500/NCSINASDAQ100) — агрегированный
  инсайдерский buy/sell ratio как режимный фильтр.

**Технические особенности:**
- Tickers напрямую (`TSLA`, `NVDA`) — наш проектный формат
  `NCSK<TICKER>2USD-USDT` маппится через `core/data/cross_venue.py`
  (TradFi сейчас без proxy на Bybit, но source-side это insider data, не
  цена).
- Rate-limit: разумно ~1 req/sec, иначе блокируют по IP.
- Архив доступен примерно с 2003 — для бэктестов на S&P500-стратегиях
  длины достаточно.

---

## 2. Myfxbook — https://www.myfxbook.com/

**Что:** Community trader rankings + **community sentiment** (% long vs
short позиций реальных розничных трейдеров) по FX/CFD/commodity-парам.

**Доступ:** бесплатно, без auth для community-sentiment-виджета
(встраиваемая страница `/community/outlook`); API доступен с регистрацией.

**Формат данных (community outlook):**
- Symbol (EURUSD, XAUUSD, BTCUSD, etc.).
- % traders long / % short.
- Total positions count.
- Update timestamp.

**Релевантность проекту:**
- **Контр-крауд гипотеза** (план 33.13 — был отклонён на крипте, но на
  FX/commodity может выживать). Розница на myfxbook исторически
  «попадает не туда» на экстремумах — классический contrarian-источник.
- **XAUUSD, EURUSD, BTCUSD, GBPUSD** есть на myfxbook → можно связать с
  BingX-перпами (golden cross-venue, BTC напрямую). Для NCCOGOLD-перпа
  myfxbook XAUUSD = более чистый сентимент-сигнал на золото.
- **Гипотеза для нового плана:** «розничный sentiment ≥80% long или ≥80%
  short → contrarian-фильтр для следующих 1-3 дней по нашему перпу».
  Требует бэктеста перед использованием.

**Технические особенности:**
- HTML-парсинг community outlook (нет официального публичного REST для
  sentiment без авторизации).
- Update ~раз в минуту, но архивную историю sentiment'а получить
  сложно (требуется ежедневный self-collected snapshot).
- Платная подписка для глубокой истории.

---

## 3. Glint Trade Terminal — https://glint.trade/terminal

**Что:** Order-flow / footprint / volume profile terminal (продвинутый
платный терминал). Сами не использовали — нужно уточнить, что именно
доступно без подписки.

**Доступ:** требует регистрации. Бесплатная демо-версия — TBD (нужно
проверить из VPS, поскольку cloud-IP блокируются многими данными).

**Релевантность проекту:**
- Если есть API/feed по footprint данным (тапе ордер-флоу,
  кумулятивные дельты с детализацией по уровням) — это потенциальный
  усилитель composite_signal (план 31) или новый класс данных для DOLF
  (на iontraday).
- Если только GUI без feed-доступа — **не подходит** для systematic
  стратегии (нечем кормить бэктест).

**Действие:** до использования — проверить владельцем тип доступа (есть
ли API/CSV/WS-feed или только просмотр чартов). Без feed-доступа этот
источник остаётся как «GUI для ручного глаза», не для бота.

---

## 4. CoinMarketCap — https://coinmarketcap.com/

**Что:** Крупнейший публичный агрегатор по криптоактивам. Цены,
капитализация, объёмы, доминация, рейтинги, листинги/делистинги,
исторические ряды, новости.

**Доступ:**
- HTML без auth (для UI / спорадического парсинга).
- **CMC Pro API** (`pro-api.coinmarketcap.com`): бесплатный tier
  `Basic` — 10K calls/мес, до 333/день, основные эндпоинты
  (`/v1/cryptocurrency/quotes/latest`, `/v1/cryptocurrency/listings/latest`,
  `/v1/global-metrics/quotes/latest`). API-key обязателен (бесплатный по
  email).

**Формат данных:**
- Per-symbol quotes (USD): price, volume_24h, market_cap, percent_change_*.
- Global: total_market_cap, total_volume_24h, **BTC dominance**, **ETH
  dominance**, stablecoin_market_cap.
- Listings: новые монеты, ранжирование, теги (DeFi, AI, RWA, ...).
- Категории/секторы — готовые корзины (AI-tokens, GameFi, Layer-1, ...).

**Релевантность проекту:**
- **Cross-source price verification** — третий источник цены (помимо
  BingX/Bybit/Yahoo). При расхождении BingX-перпа и CMC-spot — флаг для
  диагностики (manipulated mark price, делистинг и т.п.).
- **BTC/ETH dominance как режимный фильтр** — классический риск-он/риск-офф
  индикатор (низкая доминация BTC = эра альтов; высокая = bear-mode).
  Может быть фильтром для альт-стратегий (например — `composite_signal`
  только при dominance > X% / < Y%).
- **Sector rotation** — какие сектора в топе по 7d / 30d performance.
  Гипотеза: ротация сектор-лидеров как catalyst для long-momentum
  внутри сектора. Требует бэктеста.
- **Total market cap + stablecoin cap ratio** — индикатор liquidity-flow
  в рынок (растёт stablecoin cap → приток фиата готовится → потенциально
  bullish для крипты).
- **Новые листинги CMC vs Bybit/BingX** — обычно CMC видит листинг
  быстрее → можно использовать как early-warning для добавления новых
  перпов в наш универс.

**Технические особенности:**
- API-key хранится в `.env` как `COINMARKETCAP_API_KEY` (не коммитить).
- Rate-limit: на Basic-плане ~10 req/мин в среднем — много для нашего
  use-case (achity ≤ 1 req/час по доминации).
- Кэшируем ответы в parquet (по образцу Coinglass) — экономим квоту.
- Историческая глубина: на Basic-плане только current quotes. Для
  исторических нужен платный plan (~$30/мес) или собственный self-collected
  daily snapshot.

**Anti-pattern:** не пытаться брать цены отдельных перпов с CMC — это
spot-агрегат, у нас цена должна быть с биржи исполнения (BingX/Bybit).
CMC = global metrics + sentiment-like signals + cross-source verification.

---

## 5. Finviz — https://finviz.com/

**Что:** Популярный stock screener + новостной агрегатор + insider
trading + heatmap S&P500 + fundamental snapshot per ticker.

**Доступ (probe 2026-05-31):**
- HTML с UA + follow redirects (`-L`) — ✅ работает, ~180-300 KB страницы.
- Старые URL `/quote.ashx?t=NVDA` → 301 редирект на `/stock?t=NVDA`.
- **CSV-export без auth не работает** (`/export.ashx?...` отдаёт HTML, а не CSV).
- Elite-подписка ($25/мес) даёт REST API + intraday + расширенные фильтры.
- Cloudflare фильтр (как Myfxbook): нужен Mozilla User-Agent, иначе блок.

**Формат данных (HTML scraping):**
- `quote.ashx?t=TICKER` → snapshot-table2 с фундаменталом:
  P/E, EPS, dividend yield, market cap, beta, sector, RSI(14), etc.
- `insidertrading.ashx` → insider feed (overlap с OpenInsider, но
  агрегировано по тикерам удобнее).
- `news.ashx?t=TICKER` → tagged news per ticker.
- `screener.ashx?...` → filter-based stock lists.

**Релевантность проекту:**
- **Plan 24 (фундаментал акций)** — был отложен; Finviz снимает блокер
  с фундаментальными данными для US-stocks (BingX TradFi-перпы
  NCSKAAPL/NCSKNVDA/NCSKTSLA/NCSKGOOGL/NCSKMETA/NCSKMSTR).
- **Catalyst tracking** — earnings dates, news per ticker для конкретных
  стоковых стратегий.
- **Heatmap S&P500** — режимный фильтр (broad-market color = вес equity).
- **Insider** — overlap с OpenInsider; не строим параллельный парсер,
  если openinsider покрывает.

**Технические особенности (probe-результаты):**
- Структура HTML изменилась: новые классы `snapshot-table2`,
  `body-table styled-table-new`. Старые селекторы из туториалов 2018-2020
  не работают.
- Часть данных рендерится JS — для полного scraping может понадобиться
  Playwright/Selenium (overkill для нашего use-case).
- Rate-limit: разумно ≤1 req/sec, иначе Cloudflare заблокирует.

**Действие:** добавить отдельным планом если плану 24 или новой стоковой
стратегии понадобятся фундаментальные метрики. Парсер сложнее
OpenInsider — JS-render и часто меняющиеся CSS-классы.

---

## Workflow при добавлении нового web-источника

1. Запись в этот файл (что, доступ, формат, релевантность).
2. Если связан с существующим планом — добавить ссылку из плана.
3. Если требует парсера — отдельный план в `plans/<NN>-<имя>-парсер-<дата>.md`.
4. Парсер с тестами, кешированием, rate-limit-обходом.
5. Использование в стратегии — только после edge-проверки (OOS+WF).

## Anti-patterns

- Не качать данные «на всякий случай» — каждый источник связан с
  конкретной гипотезой.
- Не запускать парсер в live-стратегии до бэктеста.
- Если источник платный — отдельное решение по бюджету ДО подписки.

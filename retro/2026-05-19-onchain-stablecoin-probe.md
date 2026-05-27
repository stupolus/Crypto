# Retro 2026-05-19 — on-chain stablecoin probe (план 47)

Запрос: «давай on-chain». Выбран бесплатный first-step через
DefiLlama (3094 дневных точек с 2017-11). Та же дисциплина, что
macro-probe (план 46): pre-registered, permutation, Bonferroni.

## Pre-registered гипотезы

H0: дневная Δ совокупного USD-stablecoin-supply НЕ опережает дневной
ΔBTC на лагах 1..3.

Тесты: lag-corr + conditional-mean (top/bottom 10%), 2000 шаффлов,
seed=42, Bonferroni α/12 = 0.00417.

## Реальный прогон (DefiLlama + Yahoo BTC-USD)

Source: `stablecoins.llama.fi/stablecoincharts/all` (free, no key).
n=3060 совпавших дней (2018-2026), 8.4 года.

```
Lag-correlation (perm test, ΔSupply → ΔBTC):
  k=1  obs=+0.0224  p=0.1574
  k=2  obs=+0.0141  p=0.2909
  k=3  obs=-0.0228  p=0.1559

Conditional mean (top vs bottom decile by ΔSupply):
  k=1  obs=-0.0012  p=0.7076
  k=2  obs=+0.0040  p=0.1994
  k=3  obs=-0.0012  p=0.7276
```

## Вердикт

**Гипотеза 47.1 отклонена.** Ни один из 6 тестов даже не близок к
Bonferroni-порогу (минимум p=0.156). На 3060 точках это **отсутствие
edge**, не «мало данных». Дневной lead-edge stablecoin-supply → BTC
не подтверждается.

Не делаем: «прикрутить 7 лагов вместо 3», «попробовать USDT отдельно
от USDC», «другие децили» — задним числом запрещено (p-hacking).
Если хотим — это **новая** гипотеза с **новой** pre-registered
регистрацией, отдельный план.

## Системный итог (info-edge candidates, free, daily)

| Источник | Тест | Результат |
|---|---|---|
| DXY/VIX → BTC (план 46) | 12 perm-тестов на n=2105 | Отклонён (мин p=0.044) |
| Stablecoin supply → BTC (план 47) | 6 perm-тестов на n=3060 | Отклонён (мин p=0.156) |

**Free daily-lead-edge не нашёлся** ни в одной из двух самых
ожидаемых семей. Это согласуется с известным фактом: daily lead-lag
на уровне asset-класса в значительной части priced in.

## Что НЕ закрыто (требует ресурсов)

- **Hyperliquid OI/funding (free)** — нет исторического эндпоинта,
  нужно поллить вперёд недели → данных пока нет, не можем
  бэктестить.
- **CryptoQuant** ($30-300/мес) — классические биржевые потоки
  (BTC inflow/outflow к биржам), miner outflows. Самый сильный
  анекдотический edge. Требует бюджет.
- **Intraday on-chain** — не доступно бесплатно в нужном объёме.

## Рекомендация

Закрываю поиск free info-edge на дневном горизонте — повторять то же
с другими free-источниками будет давать тот же null-результат, это
не «надо ещё попробовать», это структурно. Реальные варианты дальше:

1. **CryptoQuant подписка** ($30 хотя бы базовый) → новый pre-registered
   probe (exchange BTC inflow → ΔBTC, та же методика).
2. **Hyperliquid forward-data collection** — начать поллить OI/funding
   через `parsers/hyperliquid`, через 4-8 недель будет data для probe.
3. **Ждать ≥1-2 нед forward-демо v1** (уже идёт) — реальный сигнал
   из real-world эксперимента.
4. **Закрыть info-edge поиски** до результата (1) и (3).

Прод/демо/core-risk не тронуты. Ключей не использовал (всё бесплатно).

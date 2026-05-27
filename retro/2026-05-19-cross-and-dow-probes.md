# Retro 2026-05-19 — два info-edge probe (план 48) + OOS-robustness

## Probe A: Cross-crypto BTC↔ETH lead-lag

Pre-registered: 12 тестов (2 направления × 3 лага × 2 теста),
Bonferroni α/12 = 0.00417. n=3060 дней (2018-2026).

Полная выборка:
```
ETH→BTC lag-corr k=1   obs=-0.0662  p=0.0005  ★ значимо
BTC→ETH lag-corr k=1   obs=-0.0569  p=0.0025  ★ значимо
ETH→BTC cond-mean k=1  obs=-0.0068  p=0.0375  —
прочие 9 тестов        p ∈ [0.06, 0.76]       —
```

ETH→BTC k=1 даже **прошло session-wide Bonferroni** (α/37 ≈ 0.00135,
p=0.0005). Эффект: отрицательная корреляция — mean-reversion BTC↔ETH
на лаге 1 (день большого ETH-роста → следующий день BTC слабее).

### OOS-split robustness (pre-registered ДО прогона)

Сэмпл 3060 дней разделён по midpoint 1530-1530. Критерий robustness:
ОБА half'а должны дать `corr<0` И `p<0.05`.

```
ETH→BTC k=1  H1 (early 2018-2022)  obs=-0.0749  p=0.0020   ✓
ETH→BTC k=1  H2 (late  2022-2026)  obs=-0.0484  p=0.0545   ✗
BTC→ETH k=1  H1                     obs=-0.0612  p=0.0145   ✓
BTC→ETH k=1  H2                     obs=-0.0485  p=0.0590   ✗
```

**Pre-registered robustness НЕ пройден.** Направление эффекта
сохранилось (обе половины отрицательные), но H2 (последние 4 года) на
грани/выше α=0.05. Эффект **затухает**; полная-выборка-значимость
была вытянута H1.

### Вердикт A

- Статистический lead-effect ETH↔BTC daily mean-reversion **существует
  исторически**, но **не робастен** на свежем периоде.
- Effect size крошечный: r ≈ −0.05, r² ≈ 0.0025 (объясняет 0.25%
  дисперсии).
- НЕ tradeable edge после комиссий, **НЕ game-changer**.
- В composite НЕ добавляем. Пре-регистрация спасла от ложного claim.

## Probe B: Day-of-week BTC

Pre-registered: 7 тестов, Bonferroni α/7 = 0.00714.

```
Thu  mean_diff=-0.00455  p=0.0080  —  (на грани, не проходит)
прочие 6 дней            p ∈ [0.11, 0.86]  —
```

Thursday — **на грани** (p=0.0080 vs порог 0.00714); НЕ проходит даже
local Bonferroni, не говоря о session-wide. **Гипотеза отклонена.**
Не дотягиваю (убрать выходные = p-hacking, запрещено планом 48).

## Системный итог free info-edge сессии

| Probe | Hypothesis | Verdict |
|---|---|---|
| 46 | DXY/VIX → BTC | Отклонён (мин p=0.044, Bonferroni α=0.00417) |
| 47 | Stablecoin supply → BTC | Отклонён (мин p=0.156) |
| 48A | BTC↔ETH lead-lag | Эффект есть, **но не робастен** (H2 fail) |
| 48B | Day-of-week BTC | Отклонён (мин p=0.0080 vs α=0.00714) |

**Game-changer не найден.** Единственный пре-регистрационно-значимый
эффект (48A) развалился на OOS-сплите — направление есть, но не
tradeable. Это **не неудача дисциплины**, это **успех дисциплины**:
без pre-registration + OOS-split мы бы объявили «edge», натянули в
композит и потеряли деньги. Сейчас — честно зафиксировали.

## Дальше

Free-info-edge candidates на дневном горизонте исчерпаны на
структурно-разных гипотезах. Что **может** дать настоящий signal:

1. **Paid data** (CryptoQuant exchange-flows, $30+/мес) — другой
   мехашизм («smart money»), не пробовался.
2. **Intraday lead-lag** через upgraded Coinglass — другая частота.
3. **Hyperliquid forward-сбор** (недели) → собственная история DEX-OI.
4. **Forward-демо v1** (уже идёт) — реальный сигнал из real-world.

**Моя честная позиция:** дальнейшие free daily probes структурно
маловероятны дать game-changer. Имеет смысл (a) ждать демо, (b)
рассмотреть paid CryptoQuant, (c) Hyperliquid-forward как параллельный
фон. Прод/демо/core-risk не тронуты, ключей не использовал.

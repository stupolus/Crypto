# План 46 — VAA-G4 Aggressive (Keller 2017) через строгий гейт

## Контекст и почему именно VAA после Dual Momentum

Dual Momentum (план 44) НЕ прошёл OOS Sharpe 0.68 < 0.8.
Известная причина (SVRN, InvestResolve): дегенерация
post-2014 — стратегия медленно реагирует, когда один из
активов проваливается. **VAA-G4** (Keller, Keuning 2017,
SSRN «Breadth Momentum and Vigilant Asset Allocation») — это
прямой ответ на эту проблему: добавляет **breadth-momentum**
триггер (если хоть один из 4 активов offensive-универсалии
имеет негативный момент → весь портфель в defensive).

Концептуально другая идея, чем GEM Antonacci: вместо
сравнения SPY-vs-T-bill использует **взвешенный композитный
score** (heavier weight on recent) и breadth-проверку всей
оборонительной группы. Канонически опубликовано, falsifiable.

## Канон (FIXED, 5 независимых источников согласованы)

Источники: allocatesmartly.com, TradingView script, TrendXplorer,
portfoliodb.co/vigilant-asset-allocation-g4-aggressive,
Finimize.

- **Offensive (G4)**: SPY, EFA, EEM, AGG
- **Defensive**: LQD, IEF, SHY
- **Score 13612W**: `12·r1 + 4·r3 + 2·r6 + 1·r12` где
  `rN = price[EOM_t]/price[EOM_{t-N}] − 1`.
- **Правило T=1 / B=1** (Aggressive variant):
  - Если ВСЕ 4 offensive score > 0 → 100% в offensive с
    максимальным score.
  - Иначе → 100% в defensive с максимальным score (знак не
    важен).
- Ребаланс EOM, удержание 1 месяц, кост на смену актива.

## Строгий гейт (= планы 43-44)

OOS ann-Sharpe>0.8 ∧ PF>1.3 ∧ t>2 ∧ MaxDD<BH(^GSPC) ∧
WF≥3/4 ∧ cost-sweep PF>1.0 @ 0.20%. Один тест, фикс. канон.

## 10 причин провала (априорно)

1. AGG в offensive → бонды могут «спойлить» (sign-кратко
   negative — весь портфель в defensive). Note AllocateSmartly:
   «AGG was held <1% of months — мог быть spoiler».
2. 2022 rate-shock одновременно ударил AGG и LQD/IEF — breadth
   provision не помогает когда defensive тоже отрицателен.
3. 2008/2020 sharp resets: monthly ребаланс опаздывает.
4. Окно 2004+ короче канон-теста Keller 1925-2016.
5. Single-asset concentration → high volatility.
6. EEM пост-2014 хроническая underperformance vs SPY.
7. Защитные ETF после ZIRP/2022 платят слишком мало.
8. Bonferroni: 4-й тест опубликованной стратегии в сессии —
   если пройдёт, ещё санити-чек.
9. AllocateSmartly после 1995 показывает CAGR ~10%, ниже
   маркетинговых 16% (book-survivorship).
10. Даже + бэктест ≠ + форвард.

## Фазы

- 46.1 (этот файл) план.
- 46.2 `scripts/vaa_aggressive_eval.py` — бэктест по канону.
- 46.3 Вердикт:
  - **Прошёл** → 4-й проверенный edge, кандидат на demo.
  - **НЕ прошёл** → честно отрицательный итог, как Dual Momentum.

## 46.3 ВЕРДИКТ (2026-05-19) — НЕ ПРОШЁЛ (OOS Sharpe 0.66 < 0.8)

`scripts/vaa_aggressive_eval.py`. Окно 2004-09→2026-05
(260 мес), OOS split 2015-08 (N=130).

| Срез | ann-Sharpe | PF | t | DD | WF | Sweep |
|---|---|---|---|---|---|---|
| FULL | 0.93 | 2.32 | 4.35 | −20.0% | — | — |
| **OOS** | **0.66** ❌ | 1.78 ✓ | 2.19 ✓ | < BH ✓ | 4/4 ✓ | устойчив ✓ |

Аллокация мес-долей: SPY 35 / EFA 21 / EEM 64 / **AGG 0** /
LQD 32 / IEF 46 / SHY 62. AGG не использовался ни разу
(AllocateSmartly отмечает то же: AGG <1% — действует как
«spoiler» в G4-универсалии). 54% времени в defensive.

**Тот же паттерн, что Dual Momentum**: один проваленный
порог (OOS Sharpe), всё остальное прошло. DualMom OOS Sharpe
0.68, VAA OOS Sharpe 0.66 — практически идентично. Это
**независимое подтверждение** деградации tactical-стратегий
пост-2015 (отмечается SVRN, InvestResolve, AllocateSmartly).

**Не подгонка-spoiler:** в обоих случаях гейт жёсткий и
одинаковый; обе стратегии проходят 5 из 6 критериев; их
проблема — именно annualized Sharpe на современном окне.

**Контраст с Faber-GTAA**: OOS Sharpe 1.09 (план 43) — реально
выделяется среди published tactical, не маркетинговый шум.

Faber-single (план 41) + Faber-GTAA (план 43) — единственные
прошедшие edge сессии. VAA Aggressive — 4-я отвергнутая
внешняя гипотеза после EIA-нефть и Dual Momentum, при том
что все три «выглядят прибыльно» на FULL-периоде. План 46
закрыт. Артефакт оставлен проверяемым.

## Жёсткие стопы

- Параметры FIXED: 13612W, T=1, B=1, 7 ETF, monthly.
- НЕ оптимизируем breadth (B=1 → B=2 был бы скан).
- Все срезы пишутся в вердикт.
- Live — отдельным «да» после demo-критерия.

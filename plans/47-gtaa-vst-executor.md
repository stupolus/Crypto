# План 47 — GTAA-4 executor на BingX VST (заменяет Faber-single)

## Контекст и решение

План 43 подтвердил Faber-GTAA на 5 активах строгим гейтом
(OOS Sharpe 1.09). План 45 показал: на BingX VST доступны
4/5 классов (нет bond-перпа). Side-test 4-актив GTAA
**прошёл тот же строгий гейт** (OOS Sharpe 1.03, MaxDD −13.8%
vs BH ^GSPC −52.6%).

Решение владельца (2026-05-19): **GTAA-4 заменяет
Faber-single на demo**. Причина: GTAA-4 функционально
superset Faber-single (NDX = 1 из 4 активов), запускать оба
на одном VST-аккаунте = конфликт за NDX-позицию. Faber-single
не успел отработать ни одного полного цикла → потеря нулевая.

## Маппинг VST-перпов (FIXED, из плана 45.2)

| Yahoo-индекс | BingX VST perp |
|---|---|
| `^GSPC` | `NCSISP5002USD-USDT` |
| `^NDX` | `NCSINASDAQ1002USD-USDT` |
| `GC=F` | `NCCOGOLD2USD-USDT` |
| `CL=F` | `NCCO1OILWTI2USD-USDT` |

Все 4 в hedge-mode (фикс #164 разблокировал rebalance).

## Правило (канон Faber 2007, FIXED, плана 43)

На последний торговый день месяца (по Yahoo-данным):
1. Для каждого из 4 индексов: signal = `close > SMA200`.
2. Целевая аллокация: equal-weight `1/4` эквити **per ON-актив**,
   `0` для OFF-активов. Не реинвестируем OFF-вес в ON (как
   в каноне Faber: cash-leg при OFF).
3. Реконсиляция к target позиции через RiskEngine на каждый
   ON-актив (1/4 эквити риск-сайз 1% B-tier).
4. Стоп-лосс на бирже = SMA200-уровень, перенесённый из
   Yahoo-индекса на VST-перп пропорцией close-цен.
5. Удержание до следующего EOM. Идемпотентно (повторный
   запуск в том же месяце = noop).

## Schedule + state

- systemd `gtaa-vst.timer`: daily 21:30 UTC (после US-close).
- Скрипт track'ит `state.last_rebalance_eom` (дата). Если
  максимальная Yahoo-EOM-дата по 4 активам > last_rebalance_eom
  → ребаланс + апдейт state. Иначе noop.
- Это даёт ровно один ребаланс/месяц + автонагон при простое
  VPS (Persistent=true тоже работает).
- `state.day_trades`, `consecutive_losses` per месячный цикл —
  для circuit-breakers RiskEngine.

## Жёсткие предусловия (НЕ меняются)

- `BINGX_ENV=vst` hard-assert (как у Faber).
- B-tier ≤3x потолок плеча (общий по портфелю фактически
  ≤1.0x при всех ON: 4×0.25=1.0).
- Pre-entry liq-buffer через `estimate_liq_price` (план 41.6)
  → `RiskInputs.liquidation_price` для каждого ON-входа.
- Kill-switch `ops/gtaa_HALT` (зеркало Faber).
- HARD-assert env==vst, без live keys.
- НЕ live. Live = отдельным «да» после ≥4 недель demo и
  пройденного критерия плана 40.

## Артефакты

- `scripts/gtaa_vst_executor.py` — асинхронный исполнитель,
  переиспользует `estimate_liq_price`, `decide` (per-asset),
  `period_keys`, `roll_state` из `faber_vst_executor`.
- `scripts/deploy/gtaa-vst.service` — systemd oneshot
  (по образцу faber-vst.service).
- `scripts/deploy/gtaa-vst.timer` — daily 21:30 UTC.
- `scripts/deploy/install.sh` — ставит новые юниты, не ломает
  старые (faber-vst остаётся для совместимости, но не
  включается).
- `scripts/tests/test_gtaa_vst_decide.py` — юнит-тесты
  чистых функций (signal-eval, allocation, last-EOM-detection,
  reconcile decision per asset).
- Миграция на VPS: документирована в `scripts/deploy/README.md`
  (stop faber-vst.timer, enable gtaa-vst.timer).

## Тесты

Без сети: чистые функции
- `_signals_from_eoms`: 4 актива, all ON → 1/4 каждый;
  частичные OFF → cash; all OFF → flat портфель.
- `_should_rebalance`: true только когда max(EOM) > state.
- `_decide_per_asset`: target=0 + cur=0 → noop;
  target>0 + cur=0 → open_long; target=0 + cur>0 → close;
  иначе → rebalance/noop по толерансу.
- `period_keys`, `roll_state` — переиспользуются из faber.

## 10 причин провала (априорно)

1. 4 перпа одновременно → больше сетевых вызовов / partial
   failure middle-rebalance.
2. SMA200 на Yahoo-индекс vs цена VST-перпа: ratio-мэппинг
   стопа может разъехаться при сильных gap'ах spot vs perp.
3. Yahoo lag: если индекс ещё не обновился, EOM-детект
   сработает с опозданием (исправляется через persistent
   таймер: догонит на след. трригере).
4. EOM-обнаружение: разные индексы могут иметь разные
   trading calendars (^NDX vs GC=F vs CL=F). Беру **max
   EOM** по всем 4 → консервативно (ребаланс только когда
   ВСЕ индексы обновились).
5. RiskEngine может отклонить часть из 4 активов (например
   stop_min) → partial allocation, не 1/4. Нормально, лог
   reject.
6. 4 одновременных market-ордера → суммарный slippage выше
   моделируемого в backtest.
7. NCCOGOLD/NCCO1OILWTI ликвидность ниже NCSINASDAQ100 →
   wider spreads.
8. Конфликт со старыми crypto-runner@*.service на VPS
   (composite_signal на BTC/ETH/XRP) — они на разных
   символах, конфликта быть не должно, но **проверить
   что не задевают TradFi-перпы**.
9. Bonferroni-учёт уже сделан (план 43): t=3.69 проходит
   с запасом.
10. Даже + бэктест ≠ + demo — арбитр demo (план 40 критерий).

## Фазы

- 47.1 (этот файл) план.
- 47.2 Реализация executor + юниты + тесты + миграция-doc.
- 47.3 Манус на VPS: `git pull` → `install.sh` →
  `systemctl disable --now faber-vst.timer` →
  `systemctl enable --now gtaa-vst.timer`. Проверка вывода.
- 47.4 ≥4 недели demo → вердикт по DEMO_CRITERIA ниже.

## Живые находки (preflight + первый реальный прогон на VST, 2026-05-22)

Исполнитель прогнан против РЕАЛЬНОГО BingX VST из dev-среды
(демо-деньги, авторизовано «запусти demo на VST»). Что подтвердилось
и что вскрылось:

**Подтверждено живыми данными:**
- DEMO_CRITERIA 2/3: SMA200 по 4 индексам на реальных Yahoo-данных
  и сигналы корректны (GSPC/NDX/GC/CL — все LONG на 2026-05-22).
- Hedge-LONG **open** работает (GSPC, GC открыты со стопами).
- Hedge **close+reopen** (NDX) работает ПОСЛЕ фикса reduceOnly.
- DEMO_CRITERIA 5: повторный прогон → `noop` по уже верным позициям,
  **дублей нет** (идемпотентность доказана живьём).

**Баги, найденные и исправленные (только живой прогон бы их поймал):**
1. Ошибка чтения BingX (`100410` rate-limit) роняла `_rebalance`
   трейсбеком → фикс: graceful ABORT без записи state (#171).
2. Hedge-close слал `reduceOnly` → BingX `109400` «In the Hedge
   mode, the 'ReduceOnly' field can not be filled». Close-leg
   ребаланса падал на TradFi-перпах. Фикс: в hedge `reduceOnly`
   опускается (`closes_position` флаг в OrderRequest), one-way —
   как раньше. #164 чинил `positionSide`, этот фикс — `reduceOnly`.

**Находка для решения владельца (НЕ баг, RiskEngine работает верно):**
- CL (нефть) с сигналом LONG **отклонён** RiskEngine:
  `LIQUIDATION_TOO_CLOSE` — стоп Faber по нефти ~26% (широкий), а
  консервативная пред-входная оценка liq при потолке 3x даёт буфер
  5.97 < требуемых 7.64 (30% расстояния стопа). Следствие: при
  широком стопе нефть НЕ аллоцируется → портфель фактически ¾
  (GSPC+NDX+GC), CL в кэше даже при LONG-сигнале.
  - Это безопасное, КОНСЕРВАТИВНОЕ поведение: реальный risk-based
    размер крошечный (1% риска / 26% стоп) → реальная liq далеко,
    но проверка берёт потолок 3x и режет.
  - Параметры RiskEngine FIXED (CLAUDE.md/AGENTS.md). НЕ трогаю.
  - **Решение за владельцем:** (A) принять ¾-аллокацию когда стоп
    широкий (честно отражает риск-лимиты); (B) отдельным планом
    пересмотреть пред-входную liq-оценку на risk-based плечо
    вместо потолка тира. Не «подгонять» под demo — через конвейер.

## DEMO_CRITERIA (что проверяет обкатка — ИСПОЛНЕНИЕ, не PnL)

Стратегия месячная: 4 недели ≈ 1 ребаланс. Как тест **доходности**
это статистический ноль — знак PnL по одному ребалансу ничего не
значит и НЕ является результатом. SMA200-аллокация по
S&P/NASDAQ/золото/нефть академически известна (план 43: OOS Sharpe
1.09; план 45 4-актив side-test: 1.03) — эдж искать не нужно. Demo
проверяет, что бот **исполняет** правило корректно.

Критерии успеха (все обязательны, период ≥4 недели):
1. **Таймер живой.** `gtaa-vst.timer` срабатывает ежедневно 21:30
   UTC без сбоев. Проверка: heartbeat-строка `action:"fired"` в
   `ops/gtaa_vst.jsonl` за каждый день (daily-report считает
   `fired/24ч`). Переживает ребут VPS (`Persistent=true` +
   `enable` → `WantedBy=timers.target`).
2. **SMA200 корректна.** По каждому из 4 индексов SMA200 считается
   на актуальных Yahoo-данных, EOM-дата определяется верно
   (последний торговый день месяца). Аудит: поля `idx_close`,
   `sma200`, `target_eom` в логе сверяются вручную с Yahoo.
3. **Сигнал корректен.** `close>SMA200 → LONG`, `close<SMA200 →
   CASH`. Поле `signal` в логе на каждый актив.
4. **Аллокация ¼.** Каждый ON-актив получает ≈1/4 эквити (с
   поправкой на RiskEngine reject/clamp); OFF — `target_qty=0`.
   Поле `equity_share`, `target_qty`.
5. **Ребаланс чистый.** Реконсиляция от фактической позиции,
   идемпотентна (повтор в том же месяце = `noop`), без дублей и
   зависших позиций. Hedge-режим (#164) отрабатывает — нет
   ошибок `position side`.
6. **Ноль ошибок исполнения.** За период ни одной строки
   `status:"error"` (или каждая объяснена и устранена). Сетевые
   обрывы поглощаются ретраями (`_http_get_json` 2/4/8s).

**Успех demo = пункты 1–6 выполнены (ноль необъяснённых ошибок
исполнения), а НЕ знак PnL.** Поймать и разобрать вручную хотя бы
один полный месячный ребаланс (зафиксировать фактическую EOM-дату).

## Вердикт (заполнить по итогу ≥4 недель → retro/)

```
GTAA-VST DEMO ВЕРДИКТ (период ____ — ____)
1. Таймер сработал N/N дней, ребут пережил: да/нет
2. SMA200 сверена с Yahoo: совпадает/расхождение ____
3. Сигналы корректны: да/нет
4. Аллокация ¼ соблюдена: да/нет (отклонения: ____)
5. Ребаланс чистый, дублей нет: да/нет
6. Ошибок исполнения: N (какие: ____)
ИСПОЛНЕНИЕ: НАДЁЖНО / ЕСТЬ БАГИ (____)
PnL за период: ____ (НЕ доказателен на 1 ребалансе — для оценки
  доходности нужен трек в месяцы)
GO/NO-GO к реальным деньгам: по надёжности исполнения + явное «да»
  владельца.
```

## Жёсткие стопы

- Канон FIXED: SMA=200, monthly EOM, equal-weight 1/4 ON,
  4 актива выше. БЕЗ оптимизации.
- Параметры RiskEngine FIXED (B-tier 1%, ≤3x, liq-buffer).
- Live = отдельным «да» после demo-критерия.
- При сомнениях ребаланса (partial fail, network) — лог
  reject и noop, не creative recovery в коде.

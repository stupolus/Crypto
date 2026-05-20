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
- 47.4 ≥4 недели demo → вердикт по критерию плана 40.

## Жёсткие стопы

- Канон FIXED: SMA=200, monthly EOM, equal-weight 1/4 ON,
  4 актива выше. БЕЗ оптимизации.
- Параметры RiskEngine FIXED (B-tier 1%, ≤3x, liq-buffer).
- Live = отдельным «да» после demo-критерия.
- При сомнениях ребаланса (partial fail, network) — лог
  reject и noop, не creative recovery в коде.

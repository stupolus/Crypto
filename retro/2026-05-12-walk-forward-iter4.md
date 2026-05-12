# Walk-forward iter#4 — us_session_breakout на 7 символах

**Дата:** 2026-05-12
**Параметры:** IS=60d, OOS=30d, step=30d (3 окна)

## Сводка

| Symbol | OOS PF (mean) | OOS PnL% (mean) | OOS+ wins | Trades |
|--------|---------------|-----------------|-----------|--------|
| **ETH**  | **2.37** | **+2.89%** | 2/3 | 20 |
| **ADA**  | **1.51** | **+2.34%** | 2/3 | 26 |
| XRP    | 1.23 | -0.70 | 1/3 | 27 |
| DOGE   | 1.10 | +0.06 | 1/3 | 24 |
| BTC    | 1.07 | -0.02 | 2/3 | 37 |
| SOL    | 0.97 | -1.53 | 1/3 | 26 |
| AVAX   | 0.90 | -1.17 | 1/3 | 30 |

## Выводы

1. **Стабильные плюсы:** ETH и ADA — PF > 1.5, OOS PnL > +2%, OOS+ ≥ 2/3.
2. **ETH — двойной winner.** Был топом и в iter#1 (btc_breakout) с PF 1.91, и здесь с PF 2.37. Самый надёжный кандидат на ранние сделки D3.
3. **ADA — уникальный winner iter#4.** Не проходит iter#1, но даёт PF 1.51 на us_session — даёт диверсификацию по стратегии × символ.
4. **BTC marginal на us_session.** Лучший на iter#1 (PF 1.79), но на us_session почти нулевой (PF 1.07, OOS PnL -0.02%). Логично: BTC breakout играет на трендовых движениях, а US-session — на range-фейках, у BTC они слабее чем у альтов.

## Решения

- **D3 на VST уже запущен** с btc_breakout на BTC + ETH + XRP (winners iter#1).
- **После 1-2 недель D3 на iter#1** добавить iter#4 на ETH + ADA параллельно — будет независимая edge.
- **Iter#3 (trend_ema_4h)** требует 4h-данных по DOGE/ADA/AVAX/XRP (сейчас есть только BTC/ETH/SOL). Отдельная задача — скачать через `scripts/download_klines.py --interval 4h`.

## Файлы

- `ops/wf-us-btc.json`, `ops/wf-us-xrp.json`, `ops/wf-us-doge.json`, `ops/wf-us-ada.json`, `ops/wf-us-avax.json` — детали по окнам.
- ETH и SOL были уже посчитаны ранее (`ops/walk-forward-1778566007.json` и `…008.json`).

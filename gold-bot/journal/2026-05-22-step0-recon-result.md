# Шаг 0 — результат recon на VPS (через Manus)

Дата: 2026-05-22. Разведка выполнена на VPS (у Manus есть сеть+SSH). Из dev-контейнера
сеть закрыта, поэтому фактический листинг — оттуда.

## Юниверс подтверждён (публичный листинг)

**Золото есть** — главный вывод: токенизированные золотые перпы листятся на обеих биржах.

### BingX (swap, USDT-perp)
| Символ | Taker | Maker |
|---|---|---|
| `XAUT/USDT:USDT` | 0.05% | 0.02% |
| `PAXG/USDT:USDT` | 0.05% | 0.02% |
| `NCCOGOLD2USD/USDT:USDT` | 0.05% | 0.02% |

### Bybit (swap)
| Символ | Lev max | Taker |
|---|---|---|
| `XAU/USDT:USDT` | 100x | 0.06% |
| `XAUT/USDT:USDT` | 75x | 0.06% |

Статус юниверса: золото — **листинг подтверждён**. Остаётся подтвердить доступность
конкретному аккаунту (KYC/ЕЭЗ) в UI биржи. Equity-перпы (TSLA/NVDA/...) в списке
recon не появились — вероятно недоступны/не листятся; план Б (золото + крипто-
калибровка) активен.

## Баг download_klines (0 свечей) — причина и фикс

Симптом: `[bingx] BTC/USDT:USDT 15m: 0 свечей`.
Причина: скрипт шёл на **VST/demo-эндпоинт**, а demo не отдаёт исторические
klines (это не формат символа — ccxt ждёт именно `BTC/USDT:USDT`; `BTC-USDT` наш
`to_canonical` всё равно нормализует).
Фикс: `download_klines` берёт свечи с **продакшн-эндпоинта без ключей** (свечи
публичны). VST остаётся только для торгового/paper-пути, не для данных.

## Следующие команды на VPS (после git pull ветки gold)

```bash
cd /root/Crypto && git pull --ff-only origin gold && cd gold-bot
# золото (основной инструмент) и крипто-калибровка
for s in PAXG/USDT:USDT XAUT/USDT:USDT BTC/USDT:USDT; do
  .venv/bin/python -m scripts.download_klines --exchange bingx --symbol "$s" --timeframe 15m --months 6
done
.venv/bin/python -m scripts.run_backtest --exchange bingx --symbol PAXG/USDT:USDT --timeframe 15m
.venv/bin/python -m scripts.run_backtest --exchange bingx --symbol XAUT/USDT:USDT --timeframe 15m
```

Если BingX отдаёт мало истории — уменьшить `--months`; для большей глубины по
золоту можно Bybit (`--exchange bybit --symbol XAU/USDT:USDT`).

## НАПОМИНАНИЕ (приоритет №1)

Пока ТОЛЬКО recon + download + backtest. **Не регистрировать systemd-сервис, не
запускать живую торговлю, не ставить BINGX_LIVE=1.** Paper-runner и OOS-вердикт — впереди.

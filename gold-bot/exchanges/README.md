# exchanges — биржевой слой gold-bot

Единый интерфейс к BingX и Bybit (USDT-перпы) поверх `ccxt`. Вышестоящий код
(стратегии, runner'ы) зависит от протокола `ExchangeAdapter`, а не от биржи.

## Модули

- `models.py` — pydantic-модели на `Decimal`. Ключевое: `OrderRequest`
  невозможно создать без `stop_price` и в cross-режиме (инварианты CLAUDE.md §6).
- `base.py` — протокол `ExchangeAdapter` (market / account / trading).
- `errors.py` — нормализованные исключения (независимы от ccxt).
- `normalize.py` — `to_canonical`: `BTC-USDT`/`BTCUSDT` → `BTC/USDT:USDT`.
- `logging_utils.py` — `mask_secrets`, `JsonFormatter`, `configure_logging`.
- `ccxt_base.py` — `CcxtAdapter`: общая реализация поверх ccxt.
- `bingx.py`, `bybit.py` — тонкие подклассы (внедряемый клиент для тестов).

## Использование

```python
from exchanges import BybitAdapter, OrderRequest, OrderSide, OrderType, MarginMode
from decimal import Decimal

adapter = BybitAdapter(api_key, api_secret, testnet=True)
await adapter.set_margin_mode("BTC/USDT:USDT", MarginMode.ISOLATED)  # cross → ошибка
req = OrderRequest(
    symbol="BTC-USDT", side=OrderSide.BUY, order_type=OrderType.MARKET,
    quantity=Decimal("0.001"), stop_price=Decimal("95000"),
)
result = await adapter.place_order(req)   # стоп уходит в параметрах ордера
await adapter.close()
```

## Тесты

```bash
pytest                 # unit (на моках, без сети)
pytest -m integration  # реальная сеть; testnet-цикл требует ключей в env
```

`isolated`-режим выставляется отдельно через `set_margin_mode` на уровне
runner'а (не внутри `place_order`, чтобы не ловить «not modified» на каждом ордере).

WS-потоки (`watch_*`) и user-data stream — отдельный план после бэктестера.

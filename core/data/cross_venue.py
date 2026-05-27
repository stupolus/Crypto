"""BingX ↔ Bybit cross-venue маппинг + ratio-перенос ценовых уровней.

Использование (план 49):
1. **Bybit как ИСТОЧНИК ДАННЫХ для BingX-исполнения** — стратегия считает
   сигнал на длинной Bybit-истории, ставит ордер на BingX-перпе.
   Стоп-уровень переносится через `transfer_price_level()` (по образцу
   GTAA-executor: Yahoo SMA200 → BingX perp через close-ratio).
2. **Symbol маппинг** — `bingx_to_bybit()` / `bybit_to_bingx()` для
   взаимной адресации.

Покрытие:
- Crypto major-пары (BTC/ETH/SOL/XRP/...) — 1-к-1 (`BTC-USDT` ↔ `BTCUSDT`).
- BingX TradFi-перпы (NCSI/NCCO/NCSK) — у Bybit прямого аналога обычно
  нет; для некоторых есть proxy (золото через `XAUT-USDT`).
- Если пары нет — `bingx_to_bybit()` возвращает None; вызывающий код
  явно выбирает что делать (отказаться / искать proxy).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from adapters.bingx.private_models import OrderSide
from adapters.bybit.symbol import from_project_format as _bybit_strip
from adapters.bybit.symbol import to_project_format as _bybit_add_hyphen


@dataclass(frozen=True)
class CrossVenuePair:
    """Соответствие одного актива на BingX и Bybit.

    ``bingx`` — символ в проектном формате (с дефисом, как везде).
    ``bybit`` — символ в проектном формате (тоже с дефисом; Bybit-адаптер
    переводит в `BTCUSDT` на уровне HTTP).
    ``note`` — пояснение (proxy / прямой / иной маппинг).
    """

    bingx: str
    bybit: str
    note: str = ""


# Реестр известных соответствий. Стартуем с majors;
# добавлять новые — только после явной проверки на обеих биржах.
_CRYPTO_MAJORS = (
    CrossVenuePair("BTC-USDT", "BTC-USDT"),
    CrossVenuePair("ETH-USDT", "ETH-USDT"),
    CrossVenuePair("SOL-USDT", "SOL-USDT"),
    CrossVenuePair("XRP-USDT", "XRP-USDT"),
    CrossVenuePair("BNB-USDT", "BNB-USDT"),
    CrossVenuePair("DOGE-USDT", "DOGE-USDT"),
    CrossVenuePair("ADA-USDT", "ADA-USDT"),
    CrossVenuePair("LTC-USDT", "LTC-USDT"),
    CrossVenuePair("LINK-USDT", "LINK-USDT"),
    CrossVenuePair("AVAX-USDT", "AVAX-USDT"),
)

# Tokenized RWA proxy: BingX-TradFi → Bybit-proxy через токенизированный
# актив, цена близкая, но НЕ идентичная (premium/discount XAUT vs spot
# золота). Использовать только как сигнал на signal-side, не для стопа.
_RWA_PROXIES = (
    CrossVenuePair(
        bingx="NCCOGOLD2USD-USDT",
        bybit="XAUT-USDT",
        note="Bybit XAUT (Tether Gold token) как proxy для BingX GOLD-перпа. "
        "Цены близкие, но имеют premium/discount — использовать как сигнал, "
        "не для прямого переноса стоп-уровня (нужен ratio).",
    ),
)

CROSS_VENUE_PAIRS: tuple[CrossVenuePair, ...] = _CRYPTO_MAJORS + _RWA_PROXIES


def bingx_to_bybit(bingx_symbol: str) -> str | None:
    """``BingX-символ`` → ``Bybit-символ`` (оба в проектном формате).

    Возвращает None если соответствия нет.
    """
    for pair in CROSS_VENUE_PAIRS:
        if pair.bingx == bingx_symbol:
            return pair.bybit
    return None


def bybit_to_bingx(bybit_symbol: str) -> str | None:
    """``Bybit-символ`` → ``BingX-символ`` (оба в проектном формате).

    Принимает оба формата Bybit: с дефисом (``BTC-USDT``) и без (``BTCUSDT``).
    Возвращает None если соответствия нет.
    """
    normalized = _bybit_add_hyphen(bybit_symbol)
    for pair in CROSS_VENUE_PAIRS:
        if pair.bybit == normalized:
            return pair.bingx
    return None


def cross_venue_price_ratio(bingx_close: Decimal, bybit_close: Decimal) -> Decimal:
    """Текущий коэффициент `bingx_close / bybit_close`.

    Используется для переноса абсолютных ценовых уровней между биржами.
    Защита от деления на ноль — ValueError, не безмолвный 0.
    """
    if bybit_close <= 0:
        raise ValueError(f"bybit_close must be > 0, got {bybit_close}")
    if bingx_close <= 0:
        raise ValueError(f"bingx_close must be > 0, got {bingx_close}")
    return bingx_close / bybit_close


def transfer_price_level(
    *,
    level_on_source: Decimal,
    source_close: Decimal,
    target_close: Decimal,
) -> Decimal:
    """Перенести абсолютный уровень с одной биржи на другую через ratio.

    Пример: на Bybit рассчитан SMA200 = $30 000, текущий close $35 000;
    BingX-перп торгуется на $35 100. Чтобы поставить эквивалентный
    стоп на BingX: ``transfer_price_level(level_on_source=30000,
    source_close=35000, target_close=35100) == 30085.71...``.

    Формула: `level_on_source × (target_close / source_close)`.
    Эквивалентна тому, как GTAA-executor переносит Yahoo-SMA200 на
    BingX-perp.
    """
    if source_close <= 0:
        raise ValueError(f"source_close must be > 0, got {source_close}")
    if target_close <= 0:
        raise ValueError(f"target_close must be > 0, got {target_close}")
    if level_on_source <= 0:
        raise ValueError(f"level_on_source must be > 0, got {level_on_source}")
    return level_on_source * target_close / source_close


def validate_side(side: str) -> OrderSide:
    """Узкая проверка: входной side принадлежит OrderSide-литералу.

    Не часть основного API — экспортируется для cross-venue вызывающих
    кодов, которые маршрутизируют один и тот же OrderRequest на оба
    адаптера и хотят явно ошибиться рано.
    """
    if side not in ("BUY", "SELL"):
        raise ValueError(f"side must be 'BUY' or 'SELL', got {side!r}")
    return side  # type: ignore[return-value]


# Реэкспорт для удобства — стратегии могут импортировать из одного места.
__all__ = [
    "CROSS_VENUE_PAIRS",
    "CrossVenuePair",
    "bingx_to_bybit",
    "bybit_to_bingx",
    "cross_venue_price_ratio",
    "transfer_price_level",
    "validate_side",
]

# Защищаем от случайных импортов «приватных» из этого модуля.
_ = _bybit_strip  # mark used (signal-side import for clarity)

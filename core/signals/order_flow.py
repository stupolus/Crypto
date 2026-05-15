"""Order-flow signal — обнаружение orderbook imbalance.

Концепт: imbalance = (volume_bids - volume_asks) / (volume_bids + volume_asks)
агрегированно по top N уровней orderbook. Значение в [-1, +1]:

- +1.0  → весь объём в bids (huge buying pressure)
- 0.0   → equal
- -1.0  → весь объём в asks (huge selling pressure)

Сигнал firing когда |imbalance| > threshold (например, 0.6). Direction
по знаку — positive → BUY pressure, negative → SELL pressure.

Это short-horizon signal: устаревает за минуты. Используется как один
из входов в композитный confidence (не как trigger сам по себе) — то же
требование, что и в funding_extreme.

Pure-function. Caller сам собирает orderbook (через BingX WS).

См. plan #17 §3.D — Layer 2 extended signals.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

logger = logging.getLogger(__name__)

_DEFAULT_THRESHOLD = Decimal("0.6")
_ZERO = Decimal("0")
_ONE = Decimal("1")
_NEG_ONE = Decimal("-1")


@dataclass(frozen=True)
class OrderFlowConfig:
    """Параметры детектора.

    ``threshold`` — минимальный |imbalance| для firing. 0.6 = одна сторона
    в 4 раза больше другой по объёму (75% / 25%).
    """

    threshold: Decimal = _DEFAULT_THRESHOLD


@dataclass(frozen=True)
class OrderFlowSignal:
    """Output детектора. ``action`` ∈ {BUY, SELL}.

    ``confidence_raw`` = |imbalance| (∈ [threshold, 1]).
    ``imbalance`` — raw signed value для аудита.
    """

    action: str
    confidence_raw: float
    imbalance: Decimal
    bid_volume: Decimal
    ask_volume: Decimal
    reason: str


def compute_imbalance(bid_volume: Decimal, ask_volume: Decimal) -> Decimal:
    """Computeschema imbalance = (B - A) / (B + A), clamped к [-1, 1].

    Возвращает ``0`` если total volume = 0 (нет сделок на этих уровнях).
    """
    total = bid_volume + ask_volume
    if total <= _ZERO:
        return _ZERO
    raw = (bid_volume - ask_volume) / total
    if raw > _ONE:
        return _ONE
    if raw < _NEG_ONE:
        return _NEG_ONE
    return raw


def detect_order_flow(
    bid_volume: Decimal,
    ask_volume: Decimal,
    config: OrderFlowConfig | None = None,
) -> OrderFlowSignal | None:
    """Определить order-flow imbalance.

    Args:
        bid_volume: суммарный bid volume по top N уровням (caller сам
            решает N — обычно 5..10).
        ask_volume: суммарный ask volume.
        config: пороги (опционально).

    Returns:
        ``OrderFlowSignal`` если |imbalance| > threshold, иначе ``None``.

    Negative-volume input или total=0 → ``None`` (некорректные данные).
    """
    if bid_volume < _ZERO or ask_volume < _ZERO:
        logger.warning(
            "detect_order_flow: negative volume bid=%s ask=%s — skip",
            bid_volume,
            ask_volume,
        )
        return None
    cfg = config or OrderFlowConfig()
    imbalance = compute_imbalance(bid_volume, ask_volume)
    abs_imb = abs(imbalance)
    if abs_imb <= cfg.threshold:
        return None

    confidence = float(abs_imb)
    if imbalance > _ZERO:
        return OrderFlowSignal(
            action="BUY",
            confidence_raw=confidence,
            imbalance=imbalance,
            bid_volume=bid_volume,
            ask_volume=ask_volume,
            reason=(f"orderbook imbalance={imbalance:.3f} (>{cfg.threshold}) — bid pressure"),
        )
    return OrderFlowSignal(
        action="SELL",
        confidence_raw=confidence,
        imbalance=imbalance,
        bid_volume=bid_volume,
        ask_volume=ask_volume,
        reason=(f"orderbook imbalance={imbalance:.3f} (<-{cfg.threshold}) — ask pressure"),
    )

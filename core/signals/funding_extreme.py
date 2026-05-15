"""Funding-extreme signal — обнаружение экстремальных funding rates.

Концепт: на perpetual-фьючерсах funding rate выплачивается каждые 8 часов
от longs к shorts (если positive) или наоборот. Когда funding выходит на
исторический экстремум — это знак переразогретой стороны рынка:

- Очень positive funding (longs платят shorts) → перекуплено, мания у
  лонгов → contrarian SHORT setup
- Очень negative funding (shorts платят longs) → переспроданно, паника
  у шортов → contrarian LONG setup

Чем дальше funding от историч. медианы — тем сильнее сигнал. Используем
percentile_rank: >threshold_high (например 95-й) → SHORT, <threshold_low
(5-й) → LONG.

Это pure-function detector. SignalCandidate отдаёт caller (стратегия или
meta-aggregator).

См. plan #17 §3.D — Layer 2 extended signals.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from core.signals.indicators import percentile_rank

logger = logging.getLogger(__name__)

_DEFAULT_PCT_HIGH = Decimal("0.95")  # 95-й перцентиль для SHORT
_DEFAULT_PCT_LOW = Decimal("0.05")  # 5-й перцентиль для LONG
_DEFAULT_MIN_HISTORY = 30


@dataclass(frozen=True)
class FundingExtremeConfig:
    """Параметры детектора. Defaults подобраны под 8h funding на крупных pairs.

    ``min_history`` — мин. количество записей funding (8h × 30 = 10 дней).
    Меньше — детектор молчит, percentile считать не на чем.
    """

    percentile_high: Decimal = _DEFAULT_PCT_HIGH
    percentile_low: Decimal = _DEFAULT_PCT_LOW
    min_history: int = _DEFAULT_MIN_HISTORY


@dataclass(frozen=True)
class FundingExtremeSignal:
    """Output детектора. ``action`` ∈ {BUY, SELL}.

    ``confidence_raw`` ∈ [0, 1] — насколько funding далеко от медианы.
    Используется LLM Coordinator'ом как один из входов в композитный
    confidence.
    """

    action: str  # "BUY" | "SELL"
    confidence_raw: float
    funding_rate: Decimal
    percentile: Decimal
    reason: str


def detect_funding_extreme(
    current_funding: Decimal,
    funding_history: Sequence[Decimal],
    config: FundingExtremeConfig | None = None,
) -> FundingExtremeSignal | None:
    """Определить funding-extreme на текущем срезе.

    Args:
        current_funding: текущий funding rate (e.g. ``Decimal("0.0008")``
            = 0.08% за 8h). Знак: positive = longs платят shorts.
        funding_history: последние N значений funding (без current).
            Чем длиннее история, тем стабильнее percentile.
        config: пороги (опционально).

    Returns:
        ``FundingExtremeSignal`` если funding в верхнем/нижнем percentile,
        иначе ``None`` (нейтральная зона / мало истории).

    Логика:
    - Если ``percentile_rank(history, current) >= percentile_high``
      (i.e. current выше 95% историч. значений) → contrarian SHORT.
    - Если ``percentile_rank(history, current) <= percentile_low``
      (current ниже 5% значений) → contrarian LONG.
    - Иначе ``None``.

    ``confidence_raw`` = расстояние от медианы (0.5) normalized к [0, 1].
    """
    cfg = config or FundingExtremeConfig()
    if len(funding_history) < cfg.min_history:
        logger.debug(
            "funding_extreme: history %d < min %d, skip",
            len(funding_history),
            cfg.min_history,
        )
        return None

    pct = percentile_rank(funding_history, current_funding)
    # Confidence: дистанция от 0.5 (медиана), normalized в [0, 1].
    # pct=1.0 или pct=0.0 → confidence=1.0. pct=0.5 → confidence=0.0.
    confidence = float(abs(pct - Decimal("0.5")) * Decimal("2"))

    if pct >= cfg.percentile_high:
        return FundingExtremeSignal(
            action="SELL",
            confidence_raw=confidence,
            funding_rate=current_funding,
            percentile=pct,
            reason=(
                f"funding {current_funding} в верхнем {cfg.percentile_high * 100}%"
                f" перцентиле (pct={pct}) → longs перегрелись → contrarian SHORT"
            ),
        )
    if pct <= cfg.percentile_low:
        return FundingExtremeSignal(
            action="BUY",
            confidence_raw=confidence,
            funding_rate=current_funding,
            percentile=pct,
            reason=(
                f"funding {current_funding} в нижнем {cfg.percentile_low * 100}%"
                f" перцентиле (pct={pct}) → shorts перегрелись → contrarian LONG"
            ),
        )
    return None

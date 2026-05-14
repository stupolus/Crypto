"""Liquidation-sweep signal — обнаружение каскада ликвидаций.

Концепт: на perp-фьючерсах ликвидации идут кластерно — когда цена
пробивает уровень со скоплением лонг-стопов, биржа force-закрывает
кучу позиций → каскад. После каскада цена часто откатывается обратно
(short squeeze в обратку): крупные игроки заходят как contrarian.

Detection:
- Считаем сумму liquidation volume за recent window (например, 5 минут)
- Сравниваем с историч. baseline (например, медиана за 24h)
- Если recent_volume / baseline > spike_threshold (например, 5x) → sweep
- Direction по типу ликвидаций: преобладают long-liqs → SHORT
  (contrarian вход после расчистки лонгов = ждём отскока ВВЕРХ через
  возвращение шортов... wait, нет — long-liqs → цена падала → дно
  → ждём отскок → BUY); short-liqs → SELL (squeeze исчерпан)

См. plan #17 §3.D — Layer 2 extended signals.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

logger = logging.getLogger(__name__)

_DEFAULT_SPIKE_THRESHOLD = Decimal("5")  # 5x median baseline
_DEFAULT_MIN_BASELINE = Decimal("100")  # минимальный baseline в USD
_DEFAULT_MIN_HISTORY = 12  # 1 час истории при 5-минутных бакетах


@dataclass(frozen=True)
class LiquidationBucket:
    """Один таймбакет ликвидаций.

    Объёмы в USD. ``long_volume`` — ликвидированные длинные позиции
    (force-close ниже entry), ``short_volume`` — короткие (force-close
    выше entry). На больших pairs (BTC) volume часто в миллионах.
    """

    long_volume: Decimal
    short_volume: Decimal

    @property
    def total(self) -> Decimal:
        return self.long_volume + self.short_volume


@dataclass(frozen=True)
class LiquidationSweepConfig:
    """Параметры детектора.

    ``spike_threshold`` — recent_total / baseline_median требуется чтобы
    считалось sweep'ом. 5x = в 5 раз выше медианы.

    ``min_baseline`` — защита от деления на (близкое к) нулю и от шумовых
    pairs где даже 100x от нуля = небольшой реальный объём.

    ``min_history`` — минимум baseline-бакетов для статистики.
    """

    spike_threshold: Decimal = _DEFAULT_SPIKE_THRESHOLD
    min_baseline: Decimal = _DEFAULT_MIN_BASELINE
    min_history: int = _DEFAULT_MIN_HISTORY


@dataclass(frozen=True)
class LiquidationSweepSignal:
    """Output детектора.

    ``action`` ∈ {BUY, SELL}:
    - BUY если доминируют long-ликвидации (цена выкупала вниз → отскок ↑)
    - SELL если доминируют short-ликвидации (squeeze исчерпан → откат ↓)

    ``confidence_raw`` = min(spike_ratio / 10, 1.0) — линейно растёт
    с silver/intensity, насыщается на 10x baseline.
    """

    action: str
    confidence_raw: float
    spike_ratio: Decimal
    recent_total: Decimal
    baseline_median: Decimal
    long_share: Decimal
    reason: str


def _median(values: Sequence[Decimal]) -> Decimal:
    """Чистая медиана. ValueError если empty."""
    if not values:
        raise ValueError("median: empty values")
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    mid = n // 2
    if n % 2 == 1:
        return sorted_vals[mid]
    return (sorted_vals[mid - 1] + sorted_vals[mid]) / Decimal("2")


def detect_liquidation_sweep(
    recent_bucket: LiquidationBucket,
    baseline_history: Sequence[LiquidationBucket],
    config: LiquidationSweepConfig | None = None,
) -> LiquidationSweepSignal | None:
    """Определить liquidation sweep.

    Args:
        recent_bucket: текущий window (например, последние 5 минут).
        baseline_history: prev N бакетов того же window-size (≥ min_history).
        config: пороги (опционально).

    Returns:
        ``LiquidationSweepSignal`` если recent_total > spike_threshold ×
        median(baseline) и median ≥ min_baseline, иначе ``None``.

    Direction:
    - long_share = long_vol / total. > 0.6 → BUY (contrarian после long
      liquidation cascade — ждём отскок). < 0.4 → SELL (short squeeze
      исчерпан). Между → no clear direction → None.
    """
    cfg = config or LiquidationSweepConfig()
    if len(baseline_history) < cfg.min_history:
        return None

    recent_total = recent_bucket.total
    if recent_total <= Decimal("0"):
        return None

    baseline_totals = [b.total for b in baseline_history]
    baseline_median = _median(baseline_totals)
    if baseline_median < cfg.min_baseline:
        logger.debug(
            "liquidation_sweep: baseline median %s < min %s — skipping noisy pair",
            baseline_median,
            cfg.min_baseline,
        )
        return None

    spike_ratio = recent_total / baseline_median
    if spike_ratio < cfg.spike_threshold:
        return None

    long_share = recent_bucket.long_volume / recent_total
    if Decimal("0.4") <= long_share <= Decimal("0.6"):
        # Объём всплеснул, но направление непонятно — не firing
        return None

    confidence = float(min(spike_ratio / Decimal("10"), Decimal("1")))
    if long_share > Decimal("0.6"):
        return LiquidationSweepSignal(
            action="BUY",
            confidence_raw=confidence,
            spike_ratio=spike_ratio,
            recent_total=recent_total,
            baseline_median=baseline_median,
            long_share=long_share,
            reason=(
                f"liquidation cascade: {spike_ratio:.1f}x baseline ({baseline_median:.0f}); "
                f"long-share {long_share:.0%} → отскок BUY"
            ),
        )
    return LiquidationSweepSignal(
        action="SELL",
        confidence_raw=confidence,
        spike_ratio=spike_ratio,
        recent_total=recent_total,
        baseline_median=baseline_median,
        long_share=long_share,
        reason=(
            f"liquidation cascade: {spike_ratio:.1f}x baseline; "
            f"short-share {(Decimal('1') - long_share):.0%} → squeeze исчерпан SELL"
        ),
    )

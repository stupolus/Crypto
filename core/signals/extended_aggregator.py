"""Aggregator для extended Layer 2 signals.

Объединяет outputs трёх детекторов (funding_extreme, order_flow,
liquidation_sweep) в один ``SignalCandidate`` если хотя бы 2 из 3
сигналов согласны по направлению.

Логика:
- 0 или 1 signal не None → no consensus, ``None`` (одиночный сигнал
  слишком шумный для триггера)
- 2+ согласны по direction → SignalCandidate с composite confidence
  (среднее активных)
- 2+ противоречат друг другу → ``None`` (mixed signals = noise)

``SignalCandidate.indicators`` содержит детали каждого активного сигнала
для аудита и для Layer 3 промптов.

См. plan #17 §3.D — Layer 2 extended signals → Layer 3 evaluate.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from core.agents.signal import SignalAction, SignalCandidate
from core.signals.funding_extreme import FundingExtremeSignal
from core.signals.liquidation_sweep import LiquidationSweepSignal
from core.signals.order_flow import OrderFlowSignal

logger = logging.getLogger(__name__)

_MIN_AGREEMENT = 2  # минимум 2 из 3 сигналов


@dataclass(frozen=True)
class ExtendedSignalsResult:
    """Wrapper над SignalCandidate с диагностикой агрегации.

    ``candidate`` — None если консенсуса нет. ``votes`` показывает что
    голосовал каждый детектор (для аудита).
    """

    candidate: SignalCandidate | None
    votes: dict[str, str | None]  # detector_name → action ("BUY"/"SELL"/None)
    reason: str


def aggregate_extended_signals(
    *,
    symbol: str,
    timestamp_ms: int,
    funding_signal: FundingExtremeSignal | None,
    order_flow_signal: OrderFlowSignal | None,
    liquidation_signal: LiquidationSweepSignal | None,
) -> ExtendedSignalsResult:
    """Aggregating decision rule: 2-of-3 consensus.

    Если 2 (или 3) детектора показывают одно направление — выдаём
    SignalCandidate. Иначе None.

    Returns:
        ExtendedSignalsResult с candidate (либо None) и votes для audit.
    """
    votes: dict[str, str | None] = {
        "funding_extreme": funding_signal.action if funding_signal else None,
        "order_flow": order_flow_signal.action if order_flow_signal else None,
        "liquidation_sweep": liquidation_signal.action if liquidation_signal else None,
    }

    actions = [v for v in votes.values() if v is not None]
    if len(actions) < _MIN_AGREEMENT:
        return ExtendedSignalsResult(
            candidate=None,
            votes=votes,
            reason=f"только {len(actions)} активных сигналов (< {_MIN_AGREEMENT})",
        )

    buy_count = actions.count("BUY")
    sell_count = actions.count("SELL")
    if buy_count >= _MIN_AGREEMENT:
        consensus_action: SignalAction = "BUY"
    elif sell_count >= _MIN_AGREEMENT:
        consensus_action = "SELL"
    else:
        return ExtendedSignalsResult(
            candidate=None,
            votes=votes,
            reason=f"smешанные сигналы: {buy_count} BUY, {sell_count} SELL",
        )

    confidences: list[float] = []
    indicators: dict[str, Any] = {}
    if funding_signal and funding_signal.action == consensus_action:
        confidences.append(funding_signal.confidence_raw)
        indicators["funding_rate"] = str(funding_signal.funding_rate)
        indicators["funding_percentile"] = str(funding_signal.percentile)
    if order_flow_signal and order_flow_signal.action == consensus_action:
        confidences.append(order_flow_signal.confidence_raw)
        indicators["orderbook_imbalance"] = str(order_flow_signal.imbalance)
    if liquidation_signal and liquidation_signal.action == consensus_action:
        confidences.append(liquidation_signal.confidence_raw)
        indicators["liquidation_spike_ratio"] = str(liquidation_signal.spike_ratio)
        indicators["liquidation_long_share"] = str(liquidation_signal.long_share)

    composite_confidence = sum(confidences) / len(confidences) if confidences else 0.5

    candidate = SignalCandidate(
        symbol=symbol,
        action=consensus_action,
        timestamp_ms=timestamp_ms,
        strategy_name="extended_aggregator",
        confidence_raw=composite_confidence,
        indicators=indicators,
        proposed_entry=None,  # aggregator не знает цены — caller заполняет
        proposed_sl=None,
        proposed_tp=(),
    )
    reason = (
        f"consensus {consensus_action} ({len(confidences)}/3 detectors agree, "
        f"composite confidence={composite_confidence:.2f})"
    )
    logger.info("aggregate_extended_signals: %s on %s | %s", consensus_action, symbol, reason)
    return ExtendedSignalsResult(candidate=candidate, votes=votes, reason=reason)


__all__ = ["ExtendedSignalsResult", "aggregate_extended_signals"]

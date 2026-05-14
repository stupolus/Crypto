"""SignalCandidateBuilder — bridge OrderRequest (Layer 2 strategy) → SignalCandidate (Layer 3).

Существующие rule-based стратегии (btc_breakout / us_session_breakout /
trend_ema_4h) возвращают ``OrderRequest | None`` из ``on_candle_close()``.
Этот builder конвертирует OrderRequest в SignalCandidate чтобы передать
в AgentTeam через evaluate_with_team.

Использование::

    request = strategy.on_candle_close(ctx)
    if request is None:
        return  # стратегия не выдала сигнал

    signal = build_signal_candidate(
        request,
        strategy_name="btc_breakout",
        timestamp_ms=int(time.time() * 1000),
        indicators={"atr": "100.5", "donchian_high": "80929"},
        confidence_raw=0.7,
    )
    decision = await evaluate_with_team(team, signal, state, ...)
"""

from __future__ import annotations

from typing import Any

from adapters.bingx.private_models import OrderRequest
from core.agents.signal import SignalAction, SignalCandidate


def build_signal_candidate(
    order_request: OrderRequest,
    *,
    strategy_name: str,
    timestamp_ms: int,
    indicators: dict[str, Any] | None = None,
    confidence_raw: float = 0.5,
) -> SignalCandidate:
    """Конвертировать OrderRequest в SignalCandidate.

    Маппинг:
    - order_request.symbol → signal.symbol
    - order_request.side (BUY/SELL) → signal.action
    - order_request.price → proposed_entry (если LIMIT)
    - order_request.attached_stop_loss → proposed_sl
    - order_request.attached_take_profit → proposed_tp (одно значение)

    Args:
        order_request: запрос на ордер от Layer 2 стратегии
        strategy_name: имя стратегии для audit (btc_breakout, etc.)
        timestamp_ms: момент срабатывания сигнала
        indicators: словарь индикаторов на момент сигнала
        confidence_raw: оценка стратегии (0..1)

    Returns:
        SignalCandidate готовый к подаче в evaluate_with_team

    Raises:
        ValueError: если order_request.side не BUY/SELL (например reduce_only)
    """
    if order_request.side not in ("BUY", "SELL"):
        raise ValueError(
            f"build_signal_candidate: order side must be BUY/SELL, got {order_request.side!r}"
        )

    action: SignalAction = order_request.side

    proposed_tp: tuple[Any, ...] = ()
    if order_request.attached_take_profit is not None:
        proposed_tp = (order_request.attached_take_profit,)

    return SignalCandidate(
        symbol=order_request.symbol,
        action=action,
        timestamp_ms=timestamp_ms,
        strategy_name=strategy_name,
        confidence_raw=confidence_raw,
        indicators=indicators or {},
        proposed_entry=order_request.price,
        proposed_sl=order_request.attached_stop_loss,
        proposed_tp=proposed_tp,
    )

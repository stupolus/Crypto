"""Correlation gate — не открывать вторую позицию в одном asset class.

Runner'ы работают независимыми процессами (один symbol на runner). Без
координации можно одновременно открыть LONG по TSLA и LONG по NVDA — оба
``stock_perp``, оба risk-on → удвоенный риск на одном движении.

Политика (выбрана пользователем 2026-05-15): **разные группы — разные
позиции**. Max 1 открытая позиция на asset class
(crypto / commodity / energy / stock_perp).

Использование в runner перед ``place_order``::

    positions = await private_api.get_positions(symbol=None)
    decision = check_correlation(candidate_symbol, positions)
    if not decision.allowed:
        logger.info("correlation gate blocked: %s", decision.reason)
        return

Чистая функция (без I/O) — позиции передаются готовым списком.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from core.assets import DEFAULT_REGISTRY
from core.assets.registry import UnknownAssetError


class _PositionLike(Protocol):
    """Минимальный интерфейс позиции — symbol + position_amount."""

    @property
    def symbol(self) -> str: ...

    @property
    def position_amount(self) -> Decimal: ...


@dataclass(frozen=True)
class CorrelationDecision:
    allowed: bool
    reason: str


def _asset_class_of(symbol: str) -> str | None:
    """Asset class symbol'а через DEFAULT_REGISTRY; None если неизвестен."""
    try:
        return DEFAULT_REGISTRY.get(symbol).asset_class.value
    except UnknownAssetError:
        return None


def check_correlation(
    candidate_symbol: str,
    open_positions: Sequence[_PositionLike],
) -> CorrelationDecision:
    """Разрешить открытие позиции по ``candidate_symbol``?

    Блокируем если уже есть открытая позиция (position_amount != 0) на
    ДРУГОМ symbol того же asset class.

    Позиция по ТОМУ ЖЕ symbol не блокирует — это случай «уже в рынке»,
    его обрабатывает strategy state machine, не correlation gate.
    """
    candidate_class = _asset_class_of(candidate_symbol)
    if candidate_class is None:
        # Неизвестный asset class → не можем оценить корреляцию.
        # Безопаснее пропустить (strategy + RiskEngine всё равно проверят).
        return CorrelationDecision(allowed=True, reason="unknown_asset_class_skip")

    for pos in open_positions:
        if pos.position_amount == 0:
            continue
        if pos.symbol == candidate_symbol:
            continue
        pos_class = _asset_class_of(pos.symbol)
        if pos_class == candidate_class:
            return CorrelationDecision(
                allowed=False,
                reason=(
                    f"correlation_block: open position {pos.symbol} "
                    f"({pos_class}) blocks {candidate_symbol} "
                    f"(same asset class — max 1 per class)"
                ),
            )
    return CorrelationDecision(allowed=True, reason="ok")

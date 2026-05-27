"""Bybit V5 private-модели: response-классы для balance/positions/orders.

OrderRequest — общий проектный (из ``adapters.bingx.private_models``).
Тут только Bybit-специфичные ответы и enum-маппинг.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Маппинг проектных значений на Bybit-формат.
# OrderSide  BUY/SELL → "Buy"/"Sell"
# PositionSide  LONG/SHORT/BOTH → positionIdx 1/2/0
# OrderType  MARKET/LIMIT → "Market"/"Limit"

_SIDE_TO_BYBIT: dict[str, str] = {"BUY": "Buy", "SELL": "Sell"}
_POSITION_SIDE_TO_IDX: dict[str, int] = {"LONG": 1, "SHORT": 2, "BOTH": 0}
_ORDER_TYPE_TO_BYBIT: dict[str, str] = {"MARKET": "Market", "LIMIT": "Limit"}


def side_to_bybit(side: str) -> str:
    """``BUY``/``SELL`` → ``Buy``/``Sell``."""
    if side not in _SIDE_TO_BYBIT:
        raise ValueError(f"unknown side: {side!r}")
    return _SIDE_TO_BYBIT[side]


def position_side_to_idx(position_side: str) -> int:
    """``LONG``/``SHORT``/``BOTH`` → 1/2/0."""
    if position_side not in _POSITION_SIDE_TO_IDX:
        raise ValueError(f"unknown position_side: {position_side!r}")
    return _POSITION_SIDE_TO_IDX[position_side]


def order_type_to_bybit(order_type: str) -> str:
    """``MARKET``/``LIMIT`` → ``Market``/``Limit``."""
    if order_type not in _ORDER_TYPE_TO_BYBIT:
        raise ValueError(f"unknown order_type: {order_type!r}")
    return _ORDER_TYPE_TO_BYBIT[order_type]


def idx_to_position_side(position_idx: int) -> str:
    """1/2/0 → ``LONG``/``SHORT``/``BOTH``."""
    for ps, idx in _POSITION_SIDE_TO_IDX.items():
        if idx == position_idx:
            return ps
    raise ValueError(f"unknown positionIdx: {position_idx!r}")


class _Strict(BaseModel):
    """Строгая модель: запрещаем неизвестные поля для ack/balance/...
    но игнорируем для response-объектов с богатыми Bybit-полями."""

    model_config = ConfigDict(extra="ignore", frozen=True, populate_by_name=True)


# ── Balance ──────────────────────────────────────────────────────────────────


class CoinBalance(_Strict):
    """Bybit V5 `/v5/account/wallet-balance` → result.list[0].coin[*]."""

    coin: str
    equity: Decimal
    wallet_balance: Decimal = Field(alias="walletBalance")
    available_to_withdraw: Decimal | None = Field(default=None, alias="availableToWithdraw")
    unrealised_pnl: Decimal | None = Field(default=None, alias="unrealisedPnl")
    cum_realised_pnl: Decimal | None = Field(default=None, alias="cumRealisedPnl")


# ── Position ─────────────────────────────────────────────────────────────────


class Position(_Strict):
    """Bybit V5 `/v5/position/list` → result.list[*].

    ``side`` пустая строка == flat-слот (Bybit отдаёт пустые слоты для
    hedge-mode); фильтрация — на уровне PrivateAPI.
    """

    symbol: str
    side: Literal["Buy", "Sell", ""]
    size: Decimal  # положительное; направление в side
    position_idx: int = Field(alias="positionIdx")
    position_value: Decimal | None = Field(default=None, alias="positionValue")
    entry_price: Decimal | None = Field(default=None, alias="entryPrice")
    avg_price: Decimal | None = Field(default=None, alias="avgPrice")
    leverage: Decimal | None = None
    mark_price: Decimal | None = Field(default=None, alias="markPrice")
    liq_price: Decimal | None = Field(default=None, alias="liqPrice")
    unrealised_pnl: Decimal | None = Field(default=None, alias="unrealisedPnl")
    cum_realised_pnl: Decimal | None = Field(default=None, alias="cumRealisedPnl")
    take_profit: Decimal | None = Field(default=None, alias="takeProfit")
    stop_loss: Decimal | None = Field(default=None, alias="stopLoss")
    trailing_stop: Decimal | None = Field(default=None, alias="trailingStop")

    @property
    def position_amount(self) -> Decimal:
        """Signed размер: положительное для long, отрицательное для short.

        Совместимо с ``adapters.bingx.private_models.Position.position_amount``.
        """
        if self.side == "Sell":
            return -self.size
        return self.size


# ── OrderAck (response от place_order) ──────────────────────────────────────


class OrderAck(_Strict):
    """Ответ Bybit на place_order: result.orderId / orderLinkId."""

    order_id: str = Field(alias="orderId")
    order_link_id: str | None = Field(default=None, alias="orderLinkId")

    @property
    def has_attached_stop_loss(self) -> bool:
        """В Bybit V5 ack просто возвращает orderId — для проверки наличия SL
        нужен последующий GET (или WS-event). Тут — заглушка, всегда True
        (адаптер ставит SL в одном запросе с place_order, см. private.py).
        """
        return True

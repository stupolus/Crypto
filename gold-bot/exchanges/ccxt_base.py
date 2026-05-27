"""Общая реализация адаптера поверх ccxt (async).

Market data (1C) + account (1D) + trading (1E). ccxt-ответы конвертируются
в наши pydantic-модели; все числа через Decimal. Конкретные биржи
(bingx.py, bybit.py) — тонкие подклассы, задающие клиента и квирки.

Инварианты (CLAUDE.md §6):
- set_margin_mode отклоняет cross (только isolated);
- place_order принимает OrderRequest, который сам по себе невозможно создать
  без stop_price — то есть голый вход без стопа недостижим по построению.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from exchanges.base import PriceLevel
from exchanges.errors import InvalidOrder, MarginModeError
from exchanges.models import (
    OHLCV,
    Balance,
    MarginMode,
    OrderRequest,
    OrderResult,
    OrderSide,
    OrderStatus,
    Position,
    PositionSide,
    Ticker,
)
from exchanges.normalize import to_canonical


def _dec(value: Any) -> Decimal:
    """Decimal из ccxt-значения (float/str). None — ошибка (поле обязано быть)."""
    if value is None:
        raise ValueError("ожидалось число, получено None")
    return Decimal(str(value))


def _dec0(value: Any) -> Decimal:
    """Decimal из необязательного значения: None → 0."""
    return Decimal("0") if value is None else Decimal(str(value))


def _map_order(raw: dict[str, Any]) -> OrderResult:
    status_raw = str(raw.get("status") or "open")
    try:
        status = OrderStatus(status_raw)
    except ValueError:
        status = OrderStatus.OPEN
    average = raw.get("average")
    coid = raw.get("clientOrderId")
    return OrderResult(
        order_id=str(raw["id"]),
        symbol=str(raw["symbol"]),
        status=status,
        filled_quantity=_dec0(raw.get("filled")),
        average_price=_dec(average) if average is not None else None,
        client_order_id=str(coid) if coid else None,
    )


class CcxtAdapter:
    """База для биржевых адаптеров на ccxt. Хранит async-клиента ccxt."""

    name: str = "ccxt"

    def __init__(self, client: Any) -> None:
        self._client = client

    @property
    def client(self) -> Any:
        return self._client

    async def close(self) -> None:
        await self._client.close()

    # ── Market data ──
    async def fetch_markets(self) -> list[str]:
        markets: dict[str, Any] = await self._client.load_markets()
        return sorted(markets.keys())

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        since: int | None = None,
        limit: int | None = None,
    ) -> list[OHLCV]:
        raw: list[list[Any]] = await self._client.fetch_ohlcv(
            to_canonical(symbol), timeframe, since, limit
        )
        return [
            OHLCV(
                timestamp=int(row[0]),
                open=_dec(row[1]),
                high=_dec(row[2]),
                low=_dec(row[3]),
                close=_dec(row[4]),
                volume=_dec(row[5]),
            )
            for row in raw
        ]

    async def fetch_ticker(self, symbol: str) -> Ticker:
        canonical = to_canonical(symbol)
        t: dict[str, Any] = await self._client.fetch_ticker(canonical)
        return Ticker(
            symbol=canonical,
            last=_dec(t["last"]),
            bid=_dec(t["bid"]),
            ask=_dec(t["ask"]),
            quote_volume_24h=_dec0(t.get("quoteVolume")),
            timestamp=int(t.get("timestamp") or 0),
        )

    async def fetch_order_book(
        self, symbol: str, depth: int = 20
    ) -> tuple[list[PriceLevel], list[PriceLevel]]:
        ob: dict[str, Any] = await self._client.fetch_order_book(to_canonical(symbol), depth)
        bids: list[PriceLevel] = [(_dec(p), _dec(s)) for p, s in ob["bids"]]
        asks: list[PriceLevel] = [(_dec(p), _dec(s)) for p, s in ob["asks"]]
        return bids, asks

    async def fetch_funding_rate(self, symbol: str) -> tuple[Decimal, int]:
        fr: dict[str, Any] = await self._client.fetch_funding_rate(to_canonical(symbol))
        rate = _dec0(fr.get("fundingRate"))
        next_ts = int(fr.get("fundingTimestamp") or fr.get("nextFundingTime") or 0)
        return rate, next_ts

    async def fetch_funding_rate_history(
        self,
        symbol: str,
        since: int | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Историческая funding-rate-серия. Сырые dict'ы ccxt — нормализация
        в `FundingRate` идёт в marketdata/funding.py."""
        raw: list[dict[str, Any]] = await self._client.fetch_funding_rate_history(
            to_canonical(symbol), since, limit
        )
        return raw

    # ── Account ──
    async def fetch_balance(self) -> Balance:
        raw: dict[str, Any] = await self._client.fetch_balance()
        usdt: dict[str, Any] = raw.get("USDT") or {}
        return Balance(
            asset="USDT",
            free=_dec0(usdt.get("free")),
            used=_dec0(usdt.get("used")),
            total=_dec0(usdt.get("total")),
        )

    async def fetch_positions(self, symbols: list[str] | None = None) -> list[Position]:
        canon = [to_canonical(s) for s in symbols] if symbols else None
        raw_list: list[dict[str, Any]] = await self._client.fetch_positions(canon)
        positions: list[Position] = []
        for p in raw_list:
            size = _dec0(p.get("contracts"))
            if size == 0:
                continue
            side = PositionSide.LONG if str(p.get("side")) == "long" else PositionSide.SHORT
            liq = p.get("liquidationPrice")
            positions.append(
                Position(
                    symbol=str(p["symbol"]),
                    side=side,
                    size=size,
                    entry_price=_dec0(p.get("entryPrice")),
                    mark_price=_dec0(p.get("markPrice")),
                    leverage=_dec0(p.get("leverage")),
                    margin_mode=MarginMode(str(p.get("marginMode") or "isolated")),
                    unrealized_pnl=_dec0(p.get("unrealizedPnl")),
                    liquidation_price=_dec(liq) if liq is not None else None,
                )
            )
        return positions

    async def set_leverage(self, symbol: str, leverage: int) -> None:
        await self._client.set_leverage(leverage, to_canonical(symbol))

    async def set_margin_mode(self, symbol: str, mode: MarginMode = MarginMode.ISOLATED) -> None:
        if mode is not MarginMode.ISOLATED:
            raise MarginModeError("cross-маржа запрещена (CLAUDE.md §6): только isolated")
        await self._client.set_margin_mode(mode.value, to_canonical(symbol))

    # ── Trading ──
    async def place_order(self, request: OrderRequest) -> OrderResult:
        """Поставить ордер с attached stop-loss.

        Маржинальный режим (isolated) выставляется заранее через
        set_margin_mode на уровне runner'а — здесь не трогаем, чтобы не
        ловить «not modified» от биржи на каждом ордере.
        """
        canonical = to_canonical(request.symbol)
        params: dict[str, Any] = {"stopLossPrice": float(request.stop_price)}
        if request.reduce_only:
            params["reduceOnly"] = True
        if request.client_order_id:
            params["clientOrderId"] = request.client_order_id
        price = float(request.price) if request.price is not None else None
        raw: dict[str, Any] = await self._client.create_order(
            canonical,
            request.order_type.value,
            request.side.value,
            float(request.quantity),
            price,
            params,
        )
        return _map_order(raw)

    async def cancel_order(self, order_id: str, symbol: str) -> None:
        await self._client.cancel_order(order_id, to_canonical(symbol))

    async def cancel_all_orders(self, symbol: str) -> None:
        await self._client.cancel_all_orders(to_canonical(symbol))

    async def close_position(self, symbol: str) -> OrderResult:
        canonical = to_canonical(symbol)
        positions = await self.fetch_positions([canonical])
        pos = next((p for p in positions if p.symbol == canonical), None)
        if pos is None:
            raise InvalidOrder(f"нет открытой позиции по {canonical}")
        close_side = OrderSide.SELL if pos.side is PositionSide.LONG else OrderSide.BUY
        raw: dict[str, Any] = await self._client.create_order(
            canonical,
            "market",
            close_side.value,
            float(pos.size),
            None,
            {"reduceOnly": True},
        )
        return _map_order(raw)

    async def fetch_order(self, order_id: str, symbol: str) -> OrderResult:
        raw: dict[str, Any] = await self._client.fetch_order(order_id, to_canonical(symbol))
        return _map_order(raw)

    async def fetch_open_orders(self, symbol: str | None = None) -> list[OrderResult]:
        arg = to_canonical(symbol) if symbol else None
        raw_list: list[dict[str, Any]] = await self._client.fetch_open_orders(arg)
        return [_map_order(o) for o in raw_list]

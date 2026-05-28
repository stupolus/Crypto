"""Тесты CompetitionRunner: broadcast одного потока в N движков, изоляция state."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from backtest.costs import CostModel
from backtest.strategy import Signal, Strategy
from exchanges.models import OHLCV, OrderSide
from paper.competition import (
    CompetitionRunner,
    ParticipantSpec,
    build_participant,
)
from paper.feed import PaperFeed
from risk.config import load_risk_config


def _c(ts: int, o: str, h: str, low: str, c: str) -> OHLCV:
    return OHLCV(
        timestamp=ts,
        open=Decimal(o),
        high=Decimal(h),
        low=Decimal(low),
        close=Decimal(c),
        volume=Decimal("1000"),
    )


class _AlwaysLong:
    def on_candle(self, history: Sequence[OHLCV]) -> Signal | None:
        if not history:
            return None
        last = history[-1]
        return Signal(
            side=OrderSide.BUY,
            stop=last.close * Decimal("0.98"),
            take_profit=last.close * Decimal("1.02"),
            risk_pct=Decimal("0.005"),
            asset_class="metals",
        )


class _Silent:
    def on_candle(self, history: Sequence[OHLCV]) -> Signal | None:
        return None


class FakeAdapter:
    def __init__(self, candles: list[OHLCV]) -> None:
        self._all = sorted(candles, key=lambda c: c.timestamp)

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        since: int | None = None,
        limit: int | None = None,
    ) -> list[OHLCV]:
        out = [c for c in self._all if since is None or c.timestamp >= since]
        if limit is not None:
            out = out[:limit]
        return out


def _strategy_factory(name: str) -> Strategy:
    return _AlwaysLong() if name == "long" else _Silent()


async def test_broadcast_to_two_participants() -> None:
    cfg = load_risk_config()
    costs = CostModel(taker_fee=Decimal("0.0005"), slippage_pct=Decimal("0.0005"))
    candles = [_c(i * 900_000, "100", "101", "99", "100") for i in range(5)]
    feed = PaperFeed(
        adapter=FakeAdapter(candles),
        symbol="X/USDT:USDT",
        timeframe="15m",
        close_grace_ms=0,
        clock=lambda: 10_000_000_000,
    )
    p_champ = build_participant(
        ParticipantSpec("champion", ":memory:", lambda _s: _strategy_factory("long")),
        symbol="X/USDT:USDT",
        cost_model=costs,
        risk_cfg=cfg,
        starting_equity=Decimal("10000"),
    )
    p_chall = build_participant(
        ParticipantSpec("silent", ":memory:", lambda _s: _strategy_factory("silent")),
        symbol="X/USDT:USDT",
        cost_model=costs,
        risk_cfg=cfg,
        starting_equity=Decimal("10000"),
    )
    runner = CompetitionRunner("X/USDT:USDT", feed, [p_champ, p_chall])
    result = await runner.step()
    assert set(result.keys()) == {"champion", "silent"}
    # champion видел все свечи и потенциально открыл позицию,
    # silent — ничего не открыл (стратегия безмолвная)
    silent_opens = sum(1 for s in result["silent"] if s.opened_position is not None)
    assert silent_opens == 0
    # участники независимы: silent.journal не знает про open_position champion'а
    assert p_chall.journal.get_open_position("X/USDT:USDT") is None
    runner.close()


def test_duplicate_strategy_id_rejected() -> None:
    cfg = load_risk_config()
    costs = CostModel(taker_fee=Decimal("0.0005"), slippage_pct=Decimal("0.0005"))
    candles = [_c(0, "100", "101", "99", "100")]
    feed = PaperFeed(
        adapter=FakeAdapter(candles),
        symbol="X/USDT:USDT",
        timeframe="15m",
        close_grace_ms=0,
        clock=lambda: 10_000_000,
    )
    p1 = build_participant(
        ParticipantSpec("dup", ":memory:", lambda _s: _strategy_factory("long")),
        "X/USDT:USDT",
        costs,
        cfg,
        Decimal("10000"),
    )
    p2 = build_participant(
        ParticipantSpec("dup", ":memory:", lambda _s: _strategy_factory("long")),
        "X/USDT:USDT",
        costs,
        cfg,
        Decimal("10000"),
    )
    try:
        CompetitionRunner("X/USDT:USDT", feed, [p1, p2])
    except ValueError as e:
        assert "strategy_id" in str(e)
    else:  # pragma: no cover
        raise AssertionError("ожидался ValueError на дубль strategy_id")
    p1.journal.close()
    p2.journal.close()


def test_empty_participants_rejected() -> None:
    cfg = load_risk_config()
    candles = [_c(0, "100", "101", "99", "100")]
    feed = PaperFeed(
        adapter=FakeAdapter(candles),
        symbol="X/USDT:USDT",
        timeframe="15m",
        close_grace_ms=0,
        clock=lambda: 10_000_000,
    )
    try:
        CompetitionRunner("X/USDT:USDT", feed, [])
    except ValueError as e:
        assert "participant" in str(e)
    else:  # pragma: no cover
        raise AssertionError("ожидался ValueError на пустой список")
    assert cfg is not None  # sanity

"""Тесты сводки daily_report (без сетевых вызовов)."""

from __future__ import annotations

from decimal import Decimal

from exchanges.models import OrderSide
from paper.journal import TradeRecord
from scripts.daily_report import _format, _summarize


def _t(net: str, gross: str = "0", costs: str = "0", equity: str = "10000") -> TradeRecord:
    return TradeRecord(
        symbol="X/USDT:USDT",
        side=OrderSide.BUY,
        entry_ts=0,
        exit_ts=900_000,
        entry_price=Decimal("100"),
        exit_price=Decimal("101"),
        quantity=Decimal("1"),
        gross_pnl=Decimal(gross),
        costs=Decimal(costs),
        net_pnl=Decimal(net),
        exit_reason="tp",
        equity_after=Decimal(equity),
    )


def test_summarize_empty_starts_with_zero() -> None:
    s = _summarize([], Decimal("10000"))
    assert s.trades == 0
    assert s.wins == 0
    assert s.winrate == Decimal(0)
    assert s.profit_factor is None
    assert s.equity_close == Decimal("10000")


def test_summarize_mixed_pf() -> None:
    trades = [
        _t(net="30", gross="32", costs="2", equity="10030"),
        _t(net="-10", gross="-8", costs="2", equity="10020"),
        _t(net="20", gross="22", costs="2", equity="10040"),
    ]
    s = _summarize(trades, Decimal("10000"))
    assert s.trades == 3
    assert s.wins == 2
    assert s.winrate == Decimal(2) / Decimal(3)
    # PF = (30+20)/10 = 5
    assert s.profit_factor == Decimal(5)
    assert s.net == Decimal(40)
    assert s.equity_close == Decimal(10040)


def test_summarize_all_winners_pf_none() -> None:
    s = _summarize([_t(net="10", equity="10010"), _t(net="5", equity="10015")], Decimal("10000"))
    assert s.profit_factor is None
    assert s.wins == 2


def test_format_zero_trades() -> None:
    s = _summarize([], Decimal("10000"))
    txt = _format("2026-05-22", s)
    assert "trades=0" in txt
    assert "equity=10000" in txt


def test_format_pf_inf_when_none() -> None:
    s = _summarize([_t(net="10")], Decimal("10000"))
    txt = _format("2026-05-22", s)
    assert "PF=inf" in txt

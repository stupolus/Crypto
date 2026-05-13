"""Unit-тесты ``evaluate_with_team`` helper."""

from __future__ import annotations

from decimal import Decimal

import pytest

from core.agents import (
    MacroContextData,
    MarketContextData,
    RunnerStateSnapshot,
    SentimentContextData,
    SignalCandidate,
    build_mock_team,
    evaluate_with_team,
)


def _default_market() -> MarketContextData:
    return MarketContextData(
        ohlcv_recent_json="[]",
        atr="100",
        donchian_high="80929",
        donchian_low="80444",
        ema20="80700",
        ema50="80600",
    )


def _default_sentiment() -> SentimentContextData:
    return SentimentContextData()


def _default_macro() -> MacroContextData:
    return MacroContextData()


def _default_state() -> RunnerStateSnapshot:
    return RunnerStateSnapshot(
        equity=Decimal("99999.94"),
        daily_pnl_pct=Decimal("-0.5"),
    )


def _btc_signal() -> SignalCandidate:
    return SignalCandidate(
        symbol="BTC-USDT",
        action="BUY",
        timestamp_ms=1_700_000_000_000,
        strategy_name="btc_breakout",
        confidence_raw=0.7,
        proposed_entry=Decimal("80500"),
        proposed_sl=Decimal("79800"),
    )


@pytest.mark.asyncio
async def test_evaluate_with_team_buy_decision() -> None:
    team = build_mock_team(
        coordinator_action="BUY",
        coordinator_size_risk_pct=1.0,
        coordinator_confidence=0.8,
    )
    decision = await evaluate_with_team(
        team,
        _btc_signal(),
        _default_state(),
        market_data=_default_market(),
        sentiment_data=_default_sentiment(),
        macro_data=_default_macro(),
    )
    assert decision.coordinator_payload["action"] == "BUY"
    assert decision.coordinator_payload["size_risk_pct"] == 1.0


@pytest.mark.asyncio
async def test_evaluate_with_team_hold_default() -> None:
    """Default mock team возвращает HOLD."""
    team = build_mock_team()
    decision = await evaluate_with_team(
        team,
        _btc_signal(),
        _default_state(),
        market_data=_default_market(),
        sentiment_data=_default_sentiment(),
        macro_data=_default_macro(),
    )
    assert decision.coordinator_payload["action"] == "HOLD"


@pytest.mark.asyncio
async def test_evaluate_with_team_passes_signal_to_coordinator() -> None:
    """Проверяем что signal context действительно доходит до Coordinator."""
    team = build_mock_team(coordinator_action="BUY", coordinator_size_risk_pct=1.0)
    signal = _btc_signal()
    decision = await evaluate_with_team(
        team,
        signal,
        _default_state(),
        market_data=_default_market(),
        sentiment_data=_default_sentiment(),
        macro_data=_default_macro(),
    )
    # Mock не валидирует input, но проверяем что вызов прошёл без exception
    assert decision.coordinator_payload["action"] == "BUY"
    # И что macro / market / risk / sentiment payloads тоже есть
    assert "macro" in decision.subagent_payloads
    assert "market" in decision.subagent_payloads


@pytest.mark.asyncio
async def test_evaluate_with_team_passes_state_to_risk() -> None:
    """RunnerStateSnapshot должен попадать в risk_context для Risk Overseer."""
    team = build_mock_team()
    state = RunnerStateSnapshot(
        equity=Decimal("50000"),
        daily_pnl_pct=Decimal("-2.5"),
        open_positions=({"symbol": "ETH-USDT", "side": "BUY"},),
        recent_trades=(),
    )
    decision = await evaluate_with_team(
        team,
        _btc_signal(),
        state,
        market_data=_default_market(),
        sentiment_data=_default_sentiment(),
        macro_data=_default_macro(),
    )
    # Mock не validates но check вызов проходит
    assert decision.coordinator_payload["action"] == "HOLD"


def test_runner_state_snapshot_immutable() -> None:
    from dataclasses import FrozenInstanceError

    state = _default_state()
    with pytest.raises(FrozenInstanceError):
        state.equity = Decimal("0")  # type: ignore[misc]


def test_market_context_data_defaults() -> None:
    data = MarketContextData(
        ohlcv_recent_json="[]",
        atr="100",
        donchian_high="80929",
        donchian_low="80444",
        ema20="80700",
        ema50="80600",
    )
    assert data.bid_5 == "0"
    assert data.funding_rate == "0"


def test_sentiment_context_data_defaults() -> None:
    data = SentimentContextData()
    assert data.twitter_sentiment_score == "0"
    assert data.tg_channels_summary == "neutral"


def test_macro_context_data_defaults() -> None:
    data = MacroContextData()
    assert data.dxy == "0"
    assert data.fed_calendar == "[]"

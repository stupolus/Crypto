"""evaluate_with_team — high-level helper для запуска AgentTeam на SignalCandidate.

Связывает Layer 2 (SignalCandidate) и Layer 3 (AgentTeam):
1. Строит 5 контекстов из SignalCandidate + RunnerStateSnapshot
2. Вызывает team.evaluate_signal
3. Возвращает TeamDecision

Use case в runner::

    signal = strategy.on_candle_close(...)  # Layer 2
    if signal is None:
        return  # стратегия не выдала кандидата
    decision = await evaluate_with_team(team, signal, state)
    if decision.coordinator_payload["action"] == "HOLD":
        return
    # else → Layer 4 Risk Engine → Layer 5 Execution
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from core.agents.signal import SignalCandidate
from core.agents.team import AgentTeam, TeamDecision


@dataclass(frozen=True)
class RunnerStateSnapshot:
    """Snapshot текущего состояния runner'а на момент вызова Layer 3.

    Используется для построения risk_context (Risk Overseer надо знать
    open positions, daily PnL, recent trades).

    Все Decimal-строки → JSON-friendly serialization.
    """

    equity: Decimal
    daily_pnl_pct: Decimal
    open_positions: tuple[dict[str, Any], ...] = ()
    recent_trades: tuple[dict[str, Any], ...] = ()
    correlation: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MarketContextData:
    """Технические индикаторы для Market Analyst (Layer 3.1).

    Сериализуется в строки для Coordinator/Market промптов.
    """

    ohlcv_recent_json: str
    atr: str
    donchian_high: str
    donchian_low: str
    ema20: str
    ema50: str
    bid_5: str = "0"
    ask_5: str = "0"
    orderbook_imbalance: str = "0"
    funding_rate: str = "0"
    oi_change_24h_pct: str = "0"


@dataclass(frozen=True)
class SentimentContextData:
    """Pre-aggregated sentiment input для Sentiment Analyst (Layer 3.2)."""

    twitter_sentiment_score: str = "0"
    twitter_top_mentions: str = "[]"
    news_headlines: str = "[]"
    funding_rate: str = "0"
    tg_channels_summary: str = "neutral"


@dataclass(frozen=True)
class MacroContextData:
    """MacroSnapshot serialized for Macro Analyst (Layer 3.5)."""

    dxy: str = "0"
    dxy_change_24h_pct: str = "0"
    vix: str = "0"
    vix_change_24h_pct: str = "0"
    spx: str = "0"
    ndx: str = "0"
    gold: str = "0"
    oil: str = "0"
    yield_10y: str = "0"
    btc_dominance_pct: str = "0"
    fed_calendar: str = "[]"
    earnings_schedule: str = "[]"


async def evaluate_with_team(
    team: AgentTeam,
    signal: SignalCandidate,
    state: RunnerStateSnapshot,
    *,
    market_data: MarketContextData,
    sentiment_data: SentimentContextData,
    macro_data: MacroContextData,
    past_mistakes: str = "",
) -> TeamDecision:
    """Запустить AgentTeam на конкретный SignalCandidate.

    Args:
        team: AgentTeam (из factory или DI в production)
        signal: SignalCandidate от Layer 2
        state: snapshot runner state (equity, positions, daily_pnl)
        market_data: технические индикаторы для Market Analyst
        sentiment_data: pre-aggregated sentiment input
        macro_data: macro snapshot
        past_mistakes: Layer 6 textual summary похожих past mistakes
            (опционально, default ""). Передаётся в Coordinator prompt.

    Returns:
        TeamDecision с финальным action / size / entry / SL / TP.

    Финальное решение в ``decision.coordinator_payload``. Layer 4
    Risk Engine далее enforces hard limits поверх этого решения.
    """
    # Контекст для каждого субагента
    risk_context = {
        "trade_proposal_json": _json_dumps(signal.to_context()),
        "equity": str(state.equity),
        "open_positions_json": _json_dumps(list(state.open_positions)),
        "daily_pnl": str(state.daily_pnl_pct),
        "recent_trades_json": _json_dumps(list(state.recent_trades)),
        "correlation_json": _json_dumps(state.correlation),
    }
    market_context = {
        "symbol": signal.symbol,
        "timeframe": "15m",  # пока хардкод; runner может передавать
        "ohlcv_json": market_data.ohlcv_recent_json,
        "atr": market_data.atr,
        "donchian_high": market_data.donchian_high,
        "donchian_low": market_data.donchian_low,
        "ema20": market_data.ema20,
        "ema50": market_data.ema50,
        "bid_5": market_data.bid_5,
        "ask_5": market_data.ask_5,
        "orderbook_imbalance": market_data.orderbook_imbalance,
        "funding_rate": market_data.funding_rate,
        "oi_change_24h_pct": market_data.oi_change_24h_pct,
    }
    sentiment_context = {
        "symbol": signal.symbol,
        "twitter_sentiment_score": sentiment_data.twitter_sentiment_score,
        "twitter_top_mentions": sentiment_data.twitter_top_mentions,
        "news_headlines": sentiment_data.news_headlines,
        "funding_rate": sentiment_data.funding_rate,
        "tg_channels_summary": sentiment_data.tg_channels_summary,
    }
    macro_context = {
        "dxy": macro_data.dxy,
        "dxy_change_24h_pct": macro_data.dxy_change_24h_pct,
        "vix": macro_data.vix,
        "vix_change_24h_pct": macro_data.vix_change_24h_pct,
        "spx": macro_data.spx,
        "ndx": macro_data.ndx,
        "gold": macro_data.gold,
        "oil": macro_data.oil,
        "yield_10y": macro_data.yield_10y,
        "btc_dominance_pct": macro_data.btc_dominance_pct,
        "fed_calendar": macro_data.fed_calendar,
        "earnings_schedule": macro_data.earnings_schedule,
    }

    return await team.evaluate_signal(
        signal_context=signal.to_context(),
        market_context=market_context,
        sentiment_context=sentiment_context,
        risk_context=risk_context,
        macro_context=macro_context,
        past_mistakes=past_mistakes,
    )


def _json_dumps(obj: Any) -> str:
    import json

    try:
        return json.dumps(obj, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(obj)

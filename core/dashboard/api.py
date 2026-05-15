"""FastAPI app для дашборда — JSON API.

CORS открыт для localhost и любых ws/wss т.к. frontend будет
serve'иться отдельно (Vite dev) или через nginx (prod). В production
URL нужно прописывать конкретно — этим займётся deploy PR.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from core.dashboard.candles import CandlesFetcher, candle_to_dict
from core.dashboard.news import NewsAggregator, news_item_to_dict
from core.dashboard.sse import status_event_stream
from core.dashboard.state import (
    DashboardState,
    agents_to_dicts,
    health_to_dict,
    summaries_to_dicts,
)

logger = logging.getLogger(__name__)


def create_app(
    *,
    outcomes_db: Path | str | list[Path | str] = "/var/lib/crypto/llm-outcomes.sqlite",
    halt_flag_file: Path | str | None = "/var/lib/crypto/halt",
    heartbeat_file: Path | str | None = "/var/lib/crypto/llm-runner.heartbeat",
    cors_origins: list[str] | None = None,
    news_aggregator: NewsAggregator | None = None,
    candles_fetcher: CandlesFetcher | None = None,
) -> FastAPI:
    """Собрать FastAPI app с одним DashboardState.

    Production: `crypto-dashboard.service` запускает этот app через uvicorn
    с переменными окружения CRYPTO_OUTCOMES_DB / CRYPTO_HALT_FLAG_FILE / etc.
    """
    app = FastAPI(
        title="Crypto Dashboard API",
        version="0.1.0",
        description=(
            "Read-only JSON API для веб-дашборда. "
            "Не модифицирует state runner'а — только читает SQLite + файлы."
        ),
    )

    state = DashboardState(
        outcomes_db=outcomes_db,
        halt_flag_file=halt_flag_file,
        heartbeat_file=heartbeat_file,
    )
    news = news_aggregator or NewsAggregator()
    candles = candles_fetcher or CandlesFetcher()

    # CORS: dev server (vite на :5173) + prod (через nginx — same origin).
    origins = cors_origins or [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def get_health() -> dict[str, Any]:
        return health_to_dict(state.health())

    @app.get("/api/status")
    def get_status() -> dict[str, Any]:
        """Краткая сводка для главного экрана UI."""
        health = state.health()
        all_trades = state.trades(limit=200)
        open_trades = [t for t in all_trades if not t.is_closed]
        closed = [t for t in all_trades if t.is_closed]
        wins = [t for t in closed if t.is_win]
        losses = [t for t in closed if t.is_loss]
        return {
            "health": health_to_dict(health),
            "trades": {
                "total": len(all_trades),
                "open": len(open_trades),
                "closed": len(closed),
                "wins": len(wins),
                "losses": len(losses),
                "win_rate_pct": (round(100.0 * len(wins) / len(closed), 1) if closed else 0.0),
            },
            "open_trades": summaries_to_dicts(open_trades),
        }

    @app.get("/api/agents")
    def get_agents() -> dict[str, Any]:
        return {"agents": agents_to_dicts(state.agent_snapshots())}

    @app.get("/api/agents/{agent_name}/history")
    def get_agent_history(agent_name: str, limit: int = 30) -> dict[str, Any]:
        allowed = {
            "market_analyst",
            "sentiment_analyst",
            "risk_overseer",
            "macro_analyst",
            "coordinator",
        }
        if agent_name not in allowed:
            raise HTTPException(
                status_code=404,
                detail=f"unknown agent {agent_name!r}, expected one of {sorted(allowed)}",
            )
        if limit < 1 or limit > 100:
            raise HTTPException(status_code=400, detail="limit must be in [1, 100]")
        return {
            "agent": agent_name,
            "points": state.agent_confidence_history(agent_name, limit=limit),
        }

    @app.get("/api/trades")
    def get_trades(
        only_open: bool = False,
        only_closed: bool = False,
        symbol: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        if limit < 1 or limit > 500:
            raise HTTPException(status_code=400, detail="limit must be in [1, 500]")
        items = state.trades(
            only_open=only_open,
            only_closed=only_closed,
            symbol=symbol,
            limit=limit,
        )
        return {"trades": summaries_to_dicts(items)}

    @app.get("/api/symbols")
    def get_symbols() -> dict[str, Any]:
        """Список уникальных symbol'ов из всех outcomes — для UI dropdown."""
        return {"symbols": state.symbols()}

    @app.get("/api/trades/{trade_id}")
    def get_trade(trade_id: str) -> dict[str, Any]:
        detail = state.trade_detail(trade_id)
        if detail is None:
            raise HTTPException(status_code=404, detail=f"trade {trade_id} not found")
        return detail

    @app.get("/api/strategy_stats")
    def get_strategy_stats() -> dict[str, Any]:
        """Per-strategy агрегация для UI «strategy leaderboard»."""
        return {"strategies": state.strategy_stats()}

    @app.get("/api/equity")
    def get_equity(limit: int = 100) -> dict[str, Any]:
        if limit < 1 or limit > 1000:
            raise HTTPException(status_code=400, detail="limit must be in [1, 1000]")
        return {"points": state.equity_curve(limit=limit)}

    @app.get("/api/news")
    def get_news(limit: int = 30) -> dict[str, Any]:
        if limit < 1 or limit > 100:
            raise HTTPException(status_code=400, detail="limit must be in [1, 100]")
        items = news.get(limit=limit)
        return {"items": [news_item_to_dict(i) for i in items]}

    @app.get("/api/candles")
    def get_candles(
        symbol: str = "BTC-USDT",
        interval: str = "15m",
        limit: int = 100,
    ) -> dict[str, Any]:
        try:
            cs = candles.get(symbol, interval, limit)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {
            "symbol": symbol,
            "interval": interval,
            "candles": [candle_to_dict(c) for c in cs],
        }

    @app.get("/stream/events")
    async def event_stream() -> StreamingResponse:
        """SSE поток — каждые 5s emit'ит ``event: status`` + JSON.

        Frontend подключается через EventSource("/stream/events") и
        hot-обновляет state без polling. Caddy/nginx proxy buffer'ы
        отключены (X-Accel-Buffering: no).
        """
        return StreamingResponse(
            status_event_stream(state),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    return app

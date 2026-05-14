"""Server-Sent Events stream для realtime updates на дашборде.

EventSource в браузере подключается к /stream/events и получает события
каждые 5 секунд: ``event: status`` + JSON data. Frontend hot-обновляет
React state без polling.

Простая реализация: text/event-stream + async generator. Без external
deps (без sse-starlette) — FastAPI достаточно.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

from core.dashboard.state import (
    DashboardState,
    health_to_dict,
    summaries_to_dicts,
)

logger = logging.getLogger(__name__)

_DEFAULT_INTERVAL_S = 5.0


async def status_event_stream(
    state: DashboardState,
    *,
    interval_s: float = _DEFAULT_INTERVAL_S,
) -> AsyncGenerator[str, None]:
    """Async generator yielding SSE-formatted строки.

    Каждые ``interval_s`` секунд эмитим:
        event: status
        data: <json status payload>

    + retry: 5000 на старте чтобы EventSource auto-reconnect через 5s
    при разрыве.

    + keepalive: ``: heartbeat`` каждые 30s — proxy (nginx/Caddy) не
    закрывает idle connection.
    """
    # Initial retry directive
    yield "retry: 5000\n\n"

    last_heartbeat = 0.0
    seq = 0
    while True:
        try:
            payload = _build_status_payload(state)
            yield f"event: status\ndata: {json.dumps(payload, default=str)}\n\n"
            seq += 1
        except Exception as exc:
            logger.warning("SSE status payload failed: %s", exc)
            yield (f"event: error\ndata: {json.dumps({'message': str(exc)})}\n\n")

        # Keepalive каждые 30s
        if seq * interval_s - last_heartbeat >= 30:
            yield ": heartbeat\n\n"
            last_heartbeat = seq * interval_s

        await asyncio.sleep(interval_s)


def _build_status_payload(state: DashboardState) -> dict[str, Any]:
    """Тот же shape что /api/status."""
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

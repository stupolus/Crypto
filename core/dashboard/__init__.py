"""Dashboard backend — FastAPI app для Wall Street vibe веб-UI.

JSON API endpoints:
- GET /api/health — uptime, version
- GET /api/status — текущий runner state (equity, open position, halt)
- GET /api/agents — последние decision'ы каждого из 5 LLM-агентов
- GET /api/trades — открытые + закрытые сделки
- GET /api/trades/{trade_id} — full DecisionContext + ExitData
- GET /api/equity — точки equity curve

Frontend (`web/`) — отдельный Vite+React+TS приложение, в отдельных
PR'ах. Backend полностью изолирован, тестируется через curl/pytest.

Запуск (development):
    .venv/bin/python -m core.dashboard.server

Production: systemd unit ``crypto-dashboard.service``.
"""

from core.dashboard.api import create_app
from core.dashboard.state import DashboardState

__all__ = ["DashboardState", "create_app"]

"""Production entry point — uvicorn launcher.

Запуск:
    .venv/bin/python -m core.dashboard.server

Переменные окружения:
    CRYPTO_OUTCOMES_DB          — путь к outcomes SQLite (default /var/lib/crypto/llm-outcomes.sqlite)
    CRYPTO_HALT_FLAG_FILE       — путь к halt-флагу (default /var/lib/crypto/halt)
    CRYPTO_HEARTBEAT_FILE       — путь к heartbeat (default /var/lib/crypto/llm-runner.heartbeat)
    CRYPTO_DASHBOARD_HOST       — bind host (default 127.0.0.1 — за nginx)
    CRYPTO_DASHBOARD_PORT       — port (default 8081)
    CRYPTO_DASHBOARD_CORS       — comma-separated origins (default http://localhost:5173)
"""

from __future__ import annotations

import logging
import os

import uvicorn

from core.dashboard.api import create_app


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    cors_env = os.getenv("CRYPTO_DASHBOARD_CORS", "")
    cors_origins = [o.strip() for o in cors_env.split(",") if o.strip()] if cors_env else None
    app = create_app(
        outcomes_db=os.getenv("CRYPTO_OUTCOMES_DB", "/var/lib/crypto/llm-outcomes.sqlite"),
        halt_flag_file=os.getenv("CRYPTO_HALT_FLAG_FILE", "/var/lib/crypto/halt"),
        heartbeat_file=os.getenv("CRYPTO_HEARTBEAT_FILE", "/var/lib/crypto/llm-runner.heartbeat"),
        cors_origins=cors_origins,
    )
    host = os.getenv("CRYPTO_DASHBOARD_HOST", "127.0.0.1")
    port = int(os.getenv("CRYPTO_DASHBOARD_PORT", "8081"))
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()

"""Production entry point — uvicorn launcher.

Запуск:
    .venv/bin/python -m core.dashboard.server

Переменные окружения:
    CRYPTO_OUTCOMES_DB          — путь к outcomes SQLite (default /var/lib/crypto/llm-outcomes.sqlite).
                                  Поддерживает glob: /var/lib/crypto/llm-*-outcomes.sqlite
                                  → дашборд агрегирует outcomes из всех найденных файлов
                                  (multi-runner setup).
    CRYPTO_EQUITY_SNAPSHOTS     — glob к equity jsonl (default /var/lib/crypto/llm-*-equity.jsonl).
                                  Настоящая equity-curve из runner snapshot loop.
    CRYPTO_HALT_FLAG_FILE       — путь к halt-флагу (default /var/lib/crypto/halt)
    CRYPTO_HEARTBEAT_FILE       — путь к heartbeat (default /var/lib/crypto/llm-runner.heartbeat)
    CRYPTO_DASHBOARD_HOST       — bind host (default 127.0.0.1 — за nginx)
    CRYPTO_DASHBOARD_PORT       — port (default 8081)
    CRYPTO_DASHBOARD_CORS       — comma-separated origins (default http://localhost:5173)
"""

from __future__ import annotations

import glob
import logging
import os
from pathlib import Path

import uvicorn

from core.dashboard.api import create_app


def _resolve_outcomes_dbs(spec: str) -> str | list[Path | str]:
    """Разрешить glob → список файлов; иначе вернуть spec как есть.

    Поддержка multi-runner setup: при CRYPTO_OUTCOMES_DB=/var/lib/crypto/llm-*-outcomes.sqlite
    дашборд найдёт все matching файлы и сольёт outcomes из каждого.
    """
    if any(c in spec for c in "*?["):
        matched_strs = sorted(glob.glob(spec))
        result: list[Path | str] = [Path(p) for p in matched_strs]
        if result:
            return result
        # No matches — fallback на буквальный путь
        return [Path(spec)]
    return spec


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    cors_env = os.getenv("CRYPTO_DASHBOARD_CORS", "")
    cors_origins = [o.strip() for o in cors_env.split(",") if o.strip()] if cors_env else None
    outcomes_spec = os.getenv("CRYPTO_OUTCOMES_DB", "/var/lib/crypto/llm-outcomes.sqlite")
    outcomes_resolved = _resolve_outcomes_dbs(outcomes_spec)
    if isinstance(outcomes_resolved, list):
        logging.getLogger(__name__).info(
            "outcomes_db glob resolved → %d files: %s", len(outcomes_resolved), outcomes_resolved
        )
    # CRYPTO_EQUITY_SNAPSHOTS поддерживает glob:
    #   /var/lib/crypto/llm-*-equity.jsonl
    equity_spec = os.getenv("CRYPTO_EQUITY_SNAPSHOTS", "/var/lib/crypto/llm-*-equity.jsonl")
    equity_files = (
        sorted(glob.glob(equity_spec)) if any(c in equity_spec for c in "*?[") else [equity_spec]
    )
    app = create_app(
        outcomes_db=outcomes_resolved,
        halt_flag_file=os.getenv("CRYPTO_HALT_FLAG_FILE", "/var/lib/crypto/halt"),
        heartbeat_file=os.getenv("CRYPTO_HEARTBEAT_FILE", "/var/lib/crypto/llm-runner.heartbeat"),
        equity_snapshot_files=list(equity_files),
        cors_origins=cors_origins,
    )
    host = os.getenv("CRYPTO_DASHBOARD_HOST", "127.0.0.1")
    port = int(os.getenv("CRYPTO_DASHBOARD_PORT", "8081"))
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()

"""``TradeOutcomeLogger`` — SQLite-backed запись TradeOutcome.

Hot path (runner):
  logger.record_entry(decision_ctx)   # при открытии сделки
  logger.record_exit(trade_id, ed)    # при закрытии (SL/TP/manual)

Offline (Mistake Library, Past-Mistakes Context Injector) читает через
``get_by_id`` / ``recent_losses`` / прямой SQL на той же базе.

Используем sqlite3 stdlib (без external deps). Connection per-call —
короткие транзакции, не держим long-lived connection.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from collections.abc import Iterable
from decimal import Decimal
from pathlib import Path
from typing import Any

from core.postmortem.models import DecisionContext, ExitData, TradeOutcome

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS trade_outcomes (
  trade_id              TEXT PRIMARY KEY,
  symbol                TEXT NOT NULL,
  side                  TEXT NOT NULL,
  entry_time_ms         INTEGER NOT NULL,
  exit_time_ms          INTEGER,
  entry_price           TEXT NOT NULL,
  exit_price            TEXT,
  size                  TEXT NOT NULL,
  pnl_usd               TEXT,
  pnl_pct               TEXT,
  exit_reason           TEXT,
  holding_time_min      INTEGER,
  signal_candidate_json TEXT NOT NULL,
  market_analyst_json   TEXT NOT NULL,
  sentiment_analyst_json TEXT NOT NULL,
  risk_overseer_json    TEXT NOT NULL,
  macro_analyst_json    TEXT NOT NULL,
  coordinator_json      TEXT NOT NULL,
  latency_decision_ms   INTEGER,
  latency_execution_ms  INTEGER,
  slippage_bps          TEXT
);
CREATE INDEX IF NOT EXISTS idx_outcomes_symbol ON trade_outcomes(symbol);
CREATE INDEX IF NOT EXISTS idx_outcomes_exit_reason ON trade_outcomes(exit_reason);
CREATE INDEX IF NOT EXISTS idx_outcomes_pnl ON trade_outcomes(pnl_pct);
"""


class TradeOutcomeLogger:
    """SQLite-журнал TradeOutcome.

    Использование::

        logger_inst = TradeOutcomeLogger("ops/llm-outcomes.sqlite")
        logger_inst.record_entry(decision_ctx)
        # ... сделка живёт ...
        logger_inst.record_exit(trade_id, exit_data)

        outcome = logger_inst.get_by_id(trade_id)  # для аудита
        losses = logger_inst.recent_losses(limit=10)  # для Mistake Library
    """

    def __init__(self, db_path: Path | str) -> None:
        self._db_path = str(db_path)
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def record_entry(self, ctx: DecisionContext) -> None:
        """Сохраняет всё что привело к открытию сделки.

        Идемпотент: повторный вызов с тем же trade_id перезаписывает запись
        (INSERT OR REPLACE) — для recovery после краша runner'а.
        """
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO trade_outcomes (
                    trade_id, symbol, side,
                    entry_time_ms, entry_price, size,
                    signal_candidate_json, market_analyst_json, sentiment_analyst_json,
                    risk_overseer_json, macro_analyst_json, coordinator_json,
                    latency_decision_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ctx.trade_id,
                    ctx.symbol,
                    ctx.side,
                    ctx.entry_time_ms,
                    str(ctx.entry_price),
                    str(ctx.size),
                    json.dumps(ctx.signal_candidate, ensure_ascii=False),
                    json.dumps(ctx.market_analyst, ensure_ascii=False),
                    json.dumps(ctx.sentiment_analyst, ensure_ascii=False),
                    json.dumps(ctx.risk_overseer, ensure_ascii=False),
                    json.dumps(ctx.macro_analyst, ensure_ascii=False),
                    json.dumps(ctx.coordinator, ensure_ascii=False),
                    ctx.latency_decision_ms,
                ),
            )
        logger.info(
            "trade_outcome.record_entry: %s %s %s @ %s",
            ctx.trade_id,
            ctx.side,
            ctx.symbol,
            ctx.entry_price,
        )

    def record_exit(self, trade_id: str, exit_data: ExitData) -> None:
        """Дополняет существующую запись exit-данными.

        Если trade_id нет в БД — KeyError (runner должен сначала вызвать
        record_entry). Логически runner владеет жизненным циклом сделки.
        """
        with self._connect() as conn:
            cur = conn.execute(
                """
                UPDATE trade_outcomes SET
                    exit_time_ms = ?,
                    exit_price = ?,
                    pnl_usd = ?,
                    pnl_pct = ?,
                    exit_reason = ?,
                    holding_time_min = ?,
                    slippage_bps = ?
                WHERE trade_id = ?
                """,
                (
                    exit_data.exit_time_ms,
                    str(exit_data.exit_price),
                    str(exit_data.pnl_usd),
                    str(exit_data.pnl_pct),
                    exit_data.exit_reason,
                    exit_data.holding_time_min,
                    str(exit_data.slippage_bps) if exit_data.slippage_bps is not None else None,
                    trade_id,
                ),
            )
            if cur.rowcount == 0:
                raise KeyError(f"trade_id {trade_id!r} не найден — нельзя record_exit")
        logger.info(
            "trade_outcome.record_exit: %s | %s @ %s | pnl=%s%%",
            trade_id,
            exit_data.exit_reason,
            exit_data.exit_price,
            exit_data.pnl_pct,
        )

    def get_by_id(self, trade_id: str) -> TradeOutcome | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM trade_outcomes WHERE trade_id = ?", (trade_id,)
            ).fetchone()
        if row is None:
            return None
        return _row_to_outcome(row)

    def recent_losses(self, limit: int = 10) -> list[TradeOutcome]:
        """N последних закрытых сделок с pnl_pct < 0 для Mistake Library."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM trade_outcomes
                WHERE pnl_pct IS NOT NULL AND CAST(pnl_pct AS REAL) < 0
                ORDER BY exit_time_ms DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [_row_to_outcome(r) for r in rows]

    def iter_all(self) -> Iterable[TradeOutcome]:
        """Итерация по всем записям. Для bulk-processing offline."""
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM trade_outcomes ORDER BY entry_time_ms").fetchall()
        return (_row_to_outcome(r) for r in rows)


def _parse_decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _row_to_outcome(row: sqlite3.Row) -> TradeOutcome:
    return TradeOutcome(
        trade_id=row["trade_id"],
        symbol=row["symbol"],
        side=row["side"],
        entry_time_ms=row["entry_time_ms"],
        entry_price=Decimal(row["entry_price"]),
        size=Decimal(row["size"]),
        exit_time_ms=row["exit_time_ms"],
        exit_price=_parse_decimal_or_none(row["exit_price"]),
        pnl_usd=_parse_decimal_or_none(row["pnl_usd"]),
        pnl_pct=_parse_decimal_or_none(row["pnl_pct"]),
        exit_reason=row["exit_reason"],
        holding_time_min=row["holding_time_min"],
        signal_candidate_json=row["signal_candidate_json"],
        market_analyst_json=row["market_analyst_json"],
        sentiment_analyst_json=row["sentiment_analyst_json"],
        risk_overseer_json=row["risk_overseer_json"],
        macro_analyst_json=row["macro_analyst_json"],
        coordinator_json=row["coordinator_json"],
        latency_decision_ms=row["latency_decision_ms"],
        latency_execution_ms=row["latency_execution_ms"],
        slippage_bps=_parse_decimal_or_none(row["slippage_bps"]),
    )

"""Журнал ордеров на SQLite (фаза 0.E).

Зачем: при рестарте процесса in-memory кэш `client_order_id → ack` теряется.
Если падение между ``place_order`` и push-событием — стратегия может задублить
ордер. Журнал даёт persistence: ``pending → acked → filled/canceled``.

Принципы:
- ``sqlite3`` (стандартная библиотека, без зависимостей).
- Sync-вызовы заворачиваются в ``asyncio.to_thread`` — не блокируем event loop.
- ``client_order_id`` — primary key. Унифицирует наш UUID и BingX-side
  идемпотентность.
- Запись pending **до** отправки запроса. Запись ack — после успешного ответа.
  Запись failure — на исключение (включая ``OrderRejected`` после
  compensating-close).
- Push-события ``ORDER_TRADE_UPDATE`` обновляют статус/avg_price/executed_qty.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from adapters.bingx.private_models import (
    OrderAck,
    OrderRequest,
    OrderUpdateEvent,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    client_order_id   TEXT PRIMARY KEY,
    exchange_order_id TEXT,
    symbol            TEXT NOT NULL,
    side              TEXT NOT NULL,
    type              TEXT NOT NULL,
    status            TEXT NOT NULL,
    quantity          TEXT NOT NULL,
    price             TEXT,
    attached_sl       TEXT,
    attached_tp       TEXT,
    ack_payload       TEXT,
    created_at_ms     INTEGER NOT NULL,
    updated_at_ms     INTEGER NOT NULL,
    last_event_type   TEXT,
    failure_reason    TEXT
);
CREATE INDEX IF NOT EXISTS idx_orders_symbol ON orders(symbol);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
"""


@dataclass(frozen=True)
class JournalEntry:
    client_order_id: str
    exchange_order_id: str | None
    symbol: str
    side: str
    type: str
    status: str
    quantity: Decimal
    price: Decimal | None
    attached_sl: Decimal | None
    attached_tp: Decimal | None
    ack_payload: dict[str, Any] | None
    created_at_ms: int
    updated_at_ms: int
    last_event_type: str | None
    failure_reason: str | None


def _decimal_str(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value.normalize(), "f")


def _parse_decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(value)


class OrderJournal:
    """SQLite-журнал ордеров. Все методы async для удобства интеграции."""

    def __init__(self, db_path: Path | str) -> None:
        self._db_path = str(db_path)
        # Открываем коннект синхронно — это быстро, схема создаётся идемпотентно.
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        # ``check_same_thread=False`` чтобы использовать из asyncio.to_thread.
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> JournalEntry:
        ack_payload = json.loads(row["ack_payload"]) if row["ack_payload"] else None
        return JournalEntry(
            client_order_id=row["client_order_id"],
            exchange_order_id=row["exchange_order_id"],
            symbol=row["symbol"],
            side=row["side"],
            type=row["type"],
            status=row["status"],
            quantity=Decimal(row["quantity"]),
            price=_parse_decimal(row["price"]),
            attached_sl=_parse_decimal(row["attached_sl"]),
            attached_tp=_parse_decimal(row["attached_tp"]),
            ack_payload=ack_payload,
            created_at_ms=row["created_at_ms"],
            updated_at_ms=row["updated_at_ms"],
            last_event_type=row["last_event_type"],
            failure_reason=row["failure_reason"],
        )

    # ── Sync internals ────────────────────────────────────────────────────

    def _insert_pending(self, req: OrderRequest, client_order_id: str) -> None:
        now = int(time.time() * 1000)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO orders (
                    client_order_id, exchange_order_id, symbol, side, type, status,
                    quantity, price, attached_sl, attached_tp, ack_payload,
                    created_at_ms, updated_at_ms, last_event_type, failure_reason
                ) VALUES (?, NULL, ?, ?, ?, 'pending', ?, ?, ?, ?, NULL, ?, ?, NULL, NULL)
                """,
                (
                    client_order_id,
                    req.symbol,
                    req.side,
                    req.order_type,
                    _decimal_str(req.quantity),
                    _decimal_str(req.price),
                    _decimal_str(req.attached_stop_loss),
                    _decimal_str(req.attached_take_profit),
                    now,
                    now,
                ),
            )

    def _apply_ack(self, client_order_id: str, ack: OrderAck) -> None:
        now = int(time.time() * 1000)
        payload = ack.model_dump(mode="json")
        status = (
            ack.status.lower()
            if ack.status not in {"NEW", "PARTIALLY_FILLED", "WORKING", "PENDING"}
            else "acked"
        )
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE orders SET
                    exchange_order_id = ?,
                    status = ?,
                    ack_payload = ?,
                    updated_at_ms = ?
                WHERE client_order_id = ?
                """,
                (
                    ack.order_id,
                    status,
                    json.dumps(payload),
                    now,
                    client_order_id,
                ),
            )

    def _apply_failure(self, client_order_id: str, reason: str) -> None:
        now = int(time.time() * 1000)
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE orders SET
                    status = 'failed',
                    failure_reason = ?,
                    updated_at_ms = ?
                WHERE client_order_id = ?
                """,
                (reason[:500], now, client_order_id),
            )

    def _apply_event(self, event: OrderUpdateEvent) -> None:
        if event.client_order_id is None:
            return
        now = int(time.time() * 1000)
        status_map = {
            "NEW": "acked",
            "PARTIALLY_FILLED": "partially_filled",
            "FILLED": "filled",
            "CANCELED": "canceled",
            "EXPIRED": "canceled",
            "REJECTED": "rejected",
        }
        status = status_map.get(event.status, event.status.lower())
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE orders SET
                    exchange_order_id = COALESCE(exchange_order_id, ?),
                    status = ?,
                    last_event_type = ?,
                    updated_at_ms = ?
                WHERE client_order_id = ?
                """,
                (
                    event.order_id,
                    status,
                    event.execution_type,
                    now,
                    event.client_order_id,
                ),
            )

    def _fetch_one(self, client_order_id: str) -> JournalEntry | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM orders WHERE client_order_id = ?",
                (client_order_id,),
            ).fetchone()
        return self._row_to_entry(row) if row else None

    def _fetch_pending(self, symbol: str | None) -> list[JournalEntry]:
        with self._connect() as conn:
            if symbol is None:
                rows = conn.execute(
                    "SELECT * FROM orders WHERE status IN ('pending', 'acked', "
                    "'partially_filled') ORDER BY created_at_ms"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM orders WHERE symbol = ? AND status IN "
                    "('pending', 'acked', 'partially_filled') ORDER BY created_at_ms",
                    (symbol,),
                ).fetchall()
        return [self._row_to_entry(r) for r in rows]

    # ── Async API ─────────────────────────────────────────────────────────

    async def record_pending(self, req: OrderRequest, client_order_id: str) -> None:
        await asyncio.to_thread(self._insert_pending, req, client_order_id)

    async def record_ack(self, client_order_id: str, ack: OrderAck) -> None:
        await asyncio.to_thread(self._apply_ack, client_order_id, ack)

    async def record_failure(self, client_order_id: str, reason: str) -> None:
        await asyncio.to_thread(self._apply_failure, client_order_id, reason)

    async def update_from_event(self, event: OrderUpdateEvent) -> None:
        await asyncio.to_thread(self._apply_event, event)

    async def get(self, client_order_id: str) -> JournalEntry | None:
        return await asyncio.to_thread(self._fetch_one, client_order_id)

    async def list_pending(self, symbol: str | None = None) -> list[JournalEntry]:
        return await asyncio.to_thread(self._fetch_pending, symbol)

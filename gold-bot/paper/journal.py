"""SQLite-журнал paper-runner'а: сделки, эквити, состояние, daily summary.

Один файл (путь из paper.yaml). На VPS лежит вне репозитория (например,
/var/lib/gold-bot/paper.sqlite), чтобы переживать обновления кода.

Все операции синхронные — на 15m таймфрейме это сотни записей в день,
SQLite справляется без проблем. Открытие соединения с WAL для надёжности
при крашах процесса между BEGIN и COMMIT.

Контракт надёжности (plan 06 §«10 причин» пункт 5):
- открытие позиции = одна транзакция: insert в runner_state.open_position.
- закрытие позиции = одна транзакция: delete из runner_state.open_position,
  insert в trades, update equity, append equity_points.
- на старте runner подтягивает runner_state.last_candle_ts / open_position.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date
from decimal import Decimal
from pathlib import Path
from typing import Any

from exchanges.models import OrderSide

_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        side TEXT NOT NULL,
        entry_ts INTEGER NOT NULL,
        exit_ts INTEGER NOT NULL,
        entry_price TEXT NOT NULL,
        exit_price TEXT NOT NULL,
        quantity TEXT NOT NULL,
        gross_pnl TEXT NOT NULL,
        costs TEXT NOT NULL,
        net_pnl TEXT NOT NULL,
        exit_reason TEXT NOT NULL,
        equity_after TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS equity_points (
        ts INTEGER PRIMARY KEY,
        equity TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS runner_state (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS daily_summary (
        day TEXT PRIMARY KEY,
        trades INTEGER NOT NULL,
        wins INTEGER NOT NULL,
        gross_pnl TEXT NOT NULL,
        costs TEXT NOT NULL,
        net_pnl TEXT NOT NULL,
        equity_close TEXT NOT NULL
    )
    """,
]


@dataclass(frozen=True)
class TradeRecord:
    symbol: str
    side: OrderSide
    entry_ts: int
    exit_ts: int
    entry_price: Decimal
    exit_price: Decimal
    quantity: Decimal
    gross_pnl: Decimal
    costs: Decimal
    net_pnl: Decimal
    exit_reason: str
    equity_after: Decimal


@dataclass(frozen=True)
class OpenPositionRecord:
    """Сериализуемое описание открытой позиции для restart-safety."""

    symbol: str
    side: OrderSide
    entry_ts: int
    entry_price: Decimal
    quantity: Decimal
    stop: Decimal
    take_profit: Decimal
    entry_cost: Decimal

    def to_json(self) -> str:
        return json.dumps(
            {
                "symbol": self.symbol,
                "side": self.side.value,
                "entry_ts": self.entry_ts,
                "entry_price": str(self.entry_price),
                "quantity": str(self.quantity),
                "stop": str(self.stop),
                "take_profit": str(self.take_profit),
                "entry_cost": str(self.entry_cost),
            }
        )

    @classmethod
    def from_json(cls, raw: str) -> OpenPositionRecord:
        d = json.loads(raw)
        return cls(
            symbol=str(d["symbol"]),
            side=OrderSide(d["side"]),
            entry_ts=int(d["entry_ts"]),
            entry_price=Decimal(d["entry_price"]),
            quantity=Decimal(d["quantity"]),
            stop=Decimal(d["stop"]),
            take_profit=Decimal(d["take_profit"]),
            entry_cost=Decimal(d["entry_cost"]),
        )


class PaperJournal:
    """Тонкая обёртка над sqlite3 с явными методами для типизации."""

    def __init__(self, path: Path | str) -> None:
        self._path = str(path)
        if self._path != ":memory:":
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._path, isolation_level=None)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        for ddl in _SCHEMA:
            self._conn.execute(ddl)

    def close(self) -> None:
        self._conn.close()

    @contextmanager
    def transaction(self) -> Any:
        self._conn.execute("BEGIN")
        try:
            yield self._conn
        except Exception:
            self._conn.execute("ROLLBACK")
            raise
        else:
            self._conn.execute("COMMIT")

    # ── runner_state KV ──
    def get_state(self, key: str) -> str | None:
        row = self._conn.execute("SELECT value FROM runner_state WHERE key = ?", (key,)).fetchone()
        return None if row is None else str(row[0])

    def set_state(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO runner_state (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    def delete_state(self, key: str) -> None:
        self._conn.execute("DELETE FROM runner_state WHERE key = ?", (key,))

    # ── удобные обёртки для часто используемых ключей ──
    def get_last_candle_ts(self, symbol: str) -> int | None:
        raw = self.get_state(f"last_candle_ts:{symbol}")
        return None if raw is None else int(raw)

    def set_last_candle_ts(self, symbol: str, ts: int) -> None:
        self.set_state(f"last_candle_ts:{symbol}", str(ts))

    def get_open_position(self, symbol: str) -> OpenPositionRecord | None:
        raw = self.get_state(f"open_position:{symbol}")
        return None if raw is None else OpenPositionRecord.from_json(raw)

    def set_open_position(self, pos: OpenPositionRecord) -> None:
        self.set_state(f"open_position:{pos.symbol}", pos.to_json())

    def delete_open_position(self, symbol: str) -> None:
        self.delete_state(f"open_position:{symbol}")

    def get_equity(self) -> Decimal | None:
        raw = self.get_state("equity")
        return None if raw is None else Decimal(raw)

    def set_equity(self, equity: Decimal) -> None:
        self.set_state("equity", str(equity))

    # ── trades / equity_points ──
    def append_trade(self, trade: TradeRecord) -> None:
        self._conn.execute(
            "INSERT INTO trades (symbol, side, entry_ts, exit_ts, entry_price, exit_price, "
            "quantity, gross_pnl, costs, net_pnl, exit_reason, equity_after) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                trade.symbol,
                trade.side.value,
                trade.entry_ts,
                trade.exit_ts,
                str(trade.entry_price),
                str(trade.exit_price),
                str(trade.quantity),
                str(trade.gross_pnl),
                str(trade.costs),
                str(trade.net_pnl),
                trade.exit_reason,
                str(trade.equity_after),
            ),
        )

    def append_equity_point(self, ts: int, equity: Decimal) -> None:
        self._conn.execute(
            "INSERT INTO equity_points (ts, equity) VALUES (?, ?) "
            "ON CONFLICT(ts) DO UPDATE SET equity = excluded.equity",
            (ts, str(equity)),
        )

    def list_trades(self, day: date | None = None) -> list[TradeRecord]:
        if day is None:
            rows: Iterable[Any] = self._conn.execute(
                "SELECT symbol, side, entry_ts, exit_ts, entry_price, exit_price, quantity, "
                "gross_pnl, costs, net_pnl, exit_reason, equity_after "
                "FROM trades ORDER BY exit_ts ASC"
            ).fetchall()
        else:
            day_start = _utc_day_start_ms(day)
            day_end = day_start + 86_400_000
            rows = self._conn.execute(
                "SELECT symbol, side, entry_ts, exit_ts, entry_price, exit_price, quantity, "
                "gross_pnl, costs, net_pnl, exit_reason, equity_after "
                "FROM trades WHERE exit_ts >= ? AND exit_ts < ? ORDER BY exit_ts ASC",
                (day_start, day_end),
            ).fetchall()
        return [
            TradeRecord(
                symbol=str(r[0]),
                side=OrderSide(r[1]),
                entry_ts=int(r[2]),
                exit_ts=int(r[3]),
                entry_price=Decimal(r[4]),
                exit_price=Decimal(r[5]),
                quantity=Decimal(r[6]),
                gross_pnl=Decimal(r[7]),
                costs=Decimal(r[8]),
                net_pnl=Decimal(r[9]),
                exit_reason=str(r[10]),
                equity_after=Decimal(r[11]),
            )
            for r in rows
        ]

    def upsert_daily_summary(
        self,
        day: date,
        trades: int,
        wins: int,
        gross: Decimal,
        costs: Decimal,
        net: Decimal,
        equity_close: Decimal,
    ) -> None:
        self._conn.execute(
            "INSERT INTO daily_summary (day, trades, wins, gross_pnl, costs, net_pnl, equity_close) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(day) DO UPDATE SET "
            "  trades = excluded.trades, wins = excluded.wins, "
            "  gross_pnl = excluded.gross_pnl, costs = excluded.costs, "
            "  net_pnl = excluded.net_pnl, equity_close = excluded.equity_close",
            (
                day.isoformat(),
                trades,
                wins,
                str(gross),
                str(costs),
                str(net),
                str(equity_close),
            ),
        )

    def heartbeat(self, ts: int) -> None:
        self.set_state("heartbeat_ts", str(ts))


def _utc_day_start_ms(day: date) -> int:
    """Полночь UTC указанного дня в ms epoch."""
    from datetime import datetime

    return int(datetime(day.year, day.month, day.day, tzinfo=UTC).timestamp() * 1000)

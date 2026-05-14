"""CSV экспорт TradeOutcomeLogger для анализа в Excel / pandas / notebook.

Один outcome → одна строка. JSON-payloads (LLM ответы) опускаются —
их слишком много для удобного CSV. Если нужны payloads, используй
прямой ``log.iter_all()`` в Python скрипте.

Запуск:
    .venv/bin/python -m scripts.journal_export
    .venv/bin/python -m scripts.journal_export --output trades.csv
    .venv/bin/python -m scripts.journal_export --only-closed
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from core.postmortem.logger import TradeOutcomeLogger
from core.postmortem.models import TradeOutcome

_COLUMNS = (
    "trade_id",
    "symbol",
    "side",
    "entry_time_ms",
    "entry_price",
    "exit_time_ms",
    "exit_price",
    "size",
    "pnl_usd",
    "pnl_pct",
    "exit_reason",
    "holding_time_min",
    "latency_decision_ms",
    "latency_execution_ms",
    "slippage_bps",
    "is_closed",
    "is_win",
    "is_loss",
)


def _row_from_outcome(outcome: TradeOutcome) -> dict[str, Any]:
    return {
        "trade_id": outcome.trade_id,
        "symbol": outcome.symbol,
        "side": outcome.side,
        "entry_time_ms": outcome.entry_time_ms,
        "entry_price": str(outcome.entry_price),
        "exit_time_ms": outcome.exit_time_ms or "",
        "exit_price": str(outcome.exit_price) if outcome.exit_price is not None else "",
        "size": str(outcome.size),
        "pnl_usd": str(outcome.pnl_usd) if outcome.pnl_usd is not None else "",
        "pnl_pct": str(outcome.pnl_pct) if outcome.pnl_pct is not None else "",
        "exit_reason": outcome.exit_reason or "",
        "holding_time_min": outcome.holding_time_min
        if outcome.holding_time_min is not None
        else "",
        "latency_decision_ms": (
            outcome.latency_decision_ms if outcome.latency_decision_ms is not None else ""
        ),
        "latency_execution_ms": (
            outcome.latency_execution_ms if outcome.latency_execution_ms is not None else ""
        ),
        "slippage_bps": str(outcome.slippage_bps) if outcome.slippage_bps is not None else "",
        "is_closed": outcome.is_closed,
        "is_win": outcome.is_win,
        "is_loss": outcome.is_loss,
    }


def write_csv(
    outcomes: Iterable[TradeOutcome],
    output_path: Path,
    *,
    only_closed: bool = False,
) -> int:
    """Записать TradeOutcome → CSV. Возвращает количество строк."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows = 0
    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_COLUMNS)
        writer.writeheader()
        for outcome in outcomes:
            if only_closed and not outcome.is_closed:
                continue
            writer.writerow(_row_from_outcome(outcome))
            rows += 1
    return rows


def run(db_path: Path, output_path: Path, *, only_closed: bool = False) -> int:
    """Точка входа. Returns exit code."""
    if not db_path.exists():
        print(f"DB не существует: {db_path}", file=sys.stderr)
        return 1
    log = TradeOutcomeLogger(db_path)
    count = write_csv(log.iter_all(), output_path, only_closed=only_closed)
    print(f"Экспортировано {count} строк → {output_path}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="CSV export TradeOutcomeLogger")
    parser.add_argument(
        "--db",
        default="ops/llm-outcomes.sqlite",
        help="Путь к SQLite БД",
    )
    parser.add_argument(
        "--output",
        default="ops/outcomes.csv",
        help="Куда писать CSV (default ops/outcomes.csv)",
    )
    parser.add_argument(
        "--only-closed",
        action="store_true",
        help="Пропустить open сделки (exit_time=None)",
    )
    args = parser.parse_args()
    sys.exit(run(Path(args.db), Path(args.output), only_closed=args.only_closed))


if __name__ == "__main__":
    main()

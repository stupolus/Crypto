"""Отчёт по Layer 6 outcomes journal.

Читает SQLite базу из ``TradeOutcomeLogger`` и печатает summary
(один за раз):
- сколько сделок всего / открытых / закрытых
- win/loss split + win rate
- avg PnL win / loss
- топ-N последних убыточных (для Mistake Library)

Запуск:
    .venv/bin/python -m scripts.postmortem_report
    .venv/bin/python -m scripts.postmortem_report --db ops/llm-outcomes.sqlite
    .venv/bin/python -m scripts.postmortem_report --losses 10

Только READ, не модифицирует БД.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from core.postmortem.logger import TradeOutcomeLogger
from core.postmortem.models import TradeOutcome


@dataclass(frozen=True)
class Summary:
    total: int
    open_trades: int
    closed: int
    wins: int
    losses: int
    flat: int
    win_rate_pct: Decimal
    avg_win_pct: Decimal
    avg_loss_pct: Decimal


def compute_summary(outcomes: list[TradeOutcome]) -> Summary:
    open_trades = sum(1 for o in outcomes if not o.is_closed)
    closed = [o for o in outcomes if o.is_closed]
    wins = [o for o in closed if o.is_win]
    losses = [o for o in closed if o.is_loss]
    flat = len(closed) - len(wins) - len(losses)

    win_rate_pct = Decimal("0")
    if closed:
        win_rate_pct = (Decimal(len(wins)) / Decimal(len(closed)) * Decimal("100")).quantize(
            Decimal("0.1")
        )

    avg_win_pct = _avg_pnl_pct(wins)
    avg_loss_pct = _avg_pnl_pct(losses)

    return Summary(
        total=len(outcomes),
        open_trades=open_trades,
        closed=len(closed),
        wins=len(wins),
        losses=len(losses),
        flat=flat,
        win_rate_pct=win_rate_pct,
        avg_win_pct=avg_win_pct,
        avg_loss_pct=avg_loss_pct,
    )


def _avg_pnl_pct(outcomes: list[TradeOutcome]) -> Decimal:
    if not outcomes:
        return Decimal("0")
    values = [o.pnl_pct for o in outcomes if o.pnl_pct is not None]
    if not values:
        return Decimal("0")
    total = sum(values, Decimal("0"))
    return (total / Decimal(len(values))).quantize(Decimal("0.01"))


def format_summary(summary: Summary) -> str:
    lines = [
        "=" * 50,
        "Layer 6 Outcomes Summary",
        "=" * 50,
        f"Total trades:    {summary.total}",
        f"  Open:          {summary.open_trades}",
        f"  Closed:        {summary.closed}",
        f"    Wins:        {summary.wins}",
        f"    Losses:      {summary.losses}",
        f"    Flat:        {summary.flat}",
        f"Win rate:        {summary.win_rate_pct}%",
        f"Avg win:         {summary.avg_win_pct}%",
        f"Avg loss:        {summary.avg_loss_pct}%",
    ]
    return "\n".join(lines)


def format_recent_losses(losses: list[TradeOutcome], limit: int) -> str:
    if not losses:
        return "\n(нет убыточных закрытых сделок в журнале)"
    lines = [
        "",
        "=" * 50,
        f"Recent losses (up to {limit}, newest first)",
        "=" * 50,
    ]
    for o in losses:
        lines.append(
            f"  {o.trade_id[:12]:<12} {o.symbol:<10} {o.side:<4} "
            f"{o.exit_reason or '-':<8} "
            f"PnL={o.pnl_pct}% holding={o.holding_time_min}min"
        )
    return "\n".join(lines)


def run(db_path: Path, losses_limit: int) -> int:
    if not db_path.exists():
        print(
            f"DB не существует: {db_path}\n"
            f"Hint: запусти llm_runner с --outcomes-db {db_path} чтобы создать её.",
            file=sys.stderr,
        )
        return 1

    log = TradeOutcomeLogger(db_path)
    all_outcomes = list(log.iter_all())
    summary = compute_summary(all_outcomes)
    print(format_summary(summary))

    if losses_limit > 0:
        losses = log.recent_losses(limit=losses_limit)
        print(format_recent_losses(losses, losses_limit))

    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Layer 6 outcomes report")
    parser.add_argument(
        "--db",
        default="ops/llm-outcomes.sqlite",
        help="Путь к SQLite БД TradeOutcomeLogger",
    )
    parser.add_argument(
        "--losses",
        type=int,
        default=5,
        help="Сколько последних убыточных сделок показать (0 = пропустить)",
    )
    args = parser.parse_args()
    sys.exit(run(Path(args.db), args.losses))


if __name__ == "__main__":
    main()

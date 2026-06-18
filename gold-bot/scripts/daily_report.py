"""Ежедневный отчёт paper-runner'а: сводка за прошедший UTC-день.

Запуск из cron / systemd timer @ 00:05 UTC. Печатает summary в stdout
и шлёт в Telegram, если env есть. Записывает строку в `daily_summary`.

Не торгует, не открывает ордера. Просто читает SQLite, считает метрики.
"""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from exchanges.logging_utils import configure_logging
from paper.config import load_paper_config
from paper.journal import PaperJournal, TradeRecord
from paper.reporter import build_reporter_from_env


@dataclass(frozen=True)
class DailySummary:
    trades: int
    wins: int
    winrate: Decimal
    profit_factor: Decimal | None
    gross: Decimal
    costs: Decimal
    net: Decimal
    equity_close: Decimal


def _summarize(trades: list[TradeRecord], starting_equity: Decimal) -> DailySummary:
    if not trades:
        return DailySummary(
            trades=0,
            wins=0,
            winrate=Decimal(0),
            profit_factor=None,
            gross=Decimal(0),
            costs=Decimal(0),
            net=Decimal(0),
            equity_close=starting_equity,
        )
    wins = sum(1 for t in trades if t.net_pnl > 0)
    losses_sum = sum((-t.net_pnl for t in trades if t.net_pnl < 0), Decimal(0))
    wins_sum = sum((t.net_pnl for t in trades if t.net_pnl > 0), Decimal(0))
    pf = None if losses_sum == 0 else wins_sum / losses_sum
    gross = sum((t.gross_pnl for t in trades), Decimal(0))
    costs = sum((t.costs for t in trades), Decimal(0))
    net = sum((t.net_pnl for t in trades), Decimal(0))
    return DailySummary(
        trades=len(trades),
        wins=wins,
        winrate=Decimal(wins) / Decimal(len(trades)),
        profit_factor=pf,
        gross=gross,
        costs=costs,
        net=net,
        equity_close=trades[-1].equity_after,
    )


def _format(report_date: str, s: DailySummary) -> str:
    pf = "inf" if s.profit_factor is None else f"{s.profit_factor:.2f}"
    return (
        f"[paper] daily {report_date}: "
        f"trades={s.trades} wins={s.wins} winrate={s.winrate:.2%} "
        f"PF={pf} gross={s.gross} costs={s.costs} "
        f"net={s.net} equity={s.equity_close}"
    )


def main() -> int:
    cfg = load_paper_config()
    secrets = [os.environ.get("GOLDBOT_TG_TOKEN", "")]
    configure_logging(level=logging.INFO, secrets=secrets)
    log = logging.getLogger("gold_bot")

    journal = PaperJournal(cfg.journal_path)
    reporter = build_reporter_from_env()

    # Отчёт за вчерашний день (UTC), т.к. запускаемся 00:05 UTC сегодняшнего.
    yesterday = (datetime.now(tz=UTC) - timedelta(days=1)).date()
    trades = journal.list_trades(day=yesterday)
    summary = _summarize(trades, cfg.starting_equity)
    text = _format(yesterday.isoformat(), summary)
    log.info("paper.daily_report %s", text)

    journal.upsert_daily_summary(
        day=yesterday,
        trades=summary.trades,
        wins=summary.wins,
        gross=summary.gross,
        costs=summary.costs,
        net=summary.net,
        equity_close=summary.equity_close,
    )
    reporter.send(text)
    journal.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

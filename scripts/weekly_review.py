"""Weekly review reporter — детальный отчёт по сделкам за период.

Что включает (см. plan #18 §6.4 Weekly Review):
- Win/loss split за неделю
- Топ-N убыточных по убыванию PnL%
- Распределение по exit_reason (SL/TP1/TP2/TIMEOUT/MANUAL/RISK_OFF)
- Avg holding time для win vs loss
- Top categories из mistake markdown'ов в журнал/mistakes/ (если есть)

Запуск:
    .venv/bin/python -m scripts.weekly_review
    .venv/bin/python -m scripts.weekly_review --days 30
    .venv/bin/python -m scripts.weekly_review --mistakes-dir журнал/mistakes/

Output: текст в stdout. Можно сохранить:
    .venv/bin/python -m scripts.weekly_review > журнал/reviews/2026-05-14.md
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from core.postmortem.logger import TradeOutcomeLogger
from core.postmortem.models import TradeOutcome

_MS_PER_DAY = 86_400_000


@dataclass(frozen=True)
class PeriodSummary:
    days: int
    total: int
    wins: int
    losses: int
    open_trades: int
    win_rate_pct: Decimal
    avg_win_pct: Decimal
    avg_loss_pct: Decimal
    avg_holding_win_min: int
    avg_holding_loss_min: int
    exit_reason_counts: Counter[str]
    top_losses: list[TradeOutcome]


def _avg(values: list[Decimal]) -> Decimal:
    if not values:
        return Decimal("0")
    return (sum(values, Decimal("0")) / Decimal(len(values))).quantize(Decimal("0.01"))


def _avg_int(values: list[int]) -> int:
    if not values:
        return 0
    return sum(values) // len(values)


def compute_period_summary(
    outcomes: list[TradeOutcome],
    *,
    cutoff_ms: int,
    days: int,
    top_losses_n: int = 5,
) -> PeriodSummary:
    """Аггрегация TradeOutcome'ов за период.

    ``cutoff_ms`` — отрезка по entry_time_ms (только сделки после этой
    отметки попадают в выборку).
    """
    in_period = [o for o in outcomes if o.entry_time_ms >= cutoff_ms]
    open_trades = sum(1 for o in in_period if not o.is_closed)
    closed = [o for o in in_period if o.is_closed]
    wins = [o for o in closed if o.is_win]
    losses = [o for o in closed if o.is_loss]

    win_rate = Decimal("0")
    if closed:
        win_rate = (Decimal(len(wins)) / Decimal(len(closed)) * Decimal("100")).quantize(
            Decimal("0.1")
        )

    avg_win = _avg([o.pnl_pct for o in wins if o.pnl_pct is not None])
    avg_loss = _avg([o.pnl_pct for o in losses if o.pnl_pct is not None])
    avg_hold_win = _avg_int([o.holding_time_min for o in wins if o.holding_time_min is not None])
    avg_hold_loss = _avg_int([o.holding_time_min for o in losses if o.holding_time_min is not None])
    exit_counts: Counter[str] = Counter(o.exit_reason for o in closed if o.exit_reason is not None)
    top_losses = sorted(
        losses,
        key=lambda o: o.pnl_pct if o.pnl_pct is not None else Decimal("0"),
    )[:top_losses_n]

    return PeriodSummary(
        days=days,
        total=len(in_period),
        wins=len(wins),
        losses=len(losses),
        open_trades=open_trades,
        win_rate_pct=win_rate,
        avg_win_pct=avg_win,
        avg_loss_pct=avg_loss,
        avg_holding_win_min=avg_hold_win,
        avg_holding_loss_min=avg_hold_loss,
        exit_reason_counts=exit_counts,
        top_losses=top_losses,
    )


def format_summary(summary: PeriodSummary) -> str:
    """Markdown-friendly текст отчёта."""
    lines = [
        f"# Weekly Review (last {summary.days} days)",
        "",
        f"- **Total trades:** {summary.total} ({summary.open_trades} still open)",
        f"- **Wins:** {summary.wins}  |  **Losses:** {summary.losses}",
        f"- **Win rate:** {summary.win_rate_pct}%",
        f"- **Avg win:** {summary.avg_win_pct}%  |  **Avg loss:** {summary.avg_loss_pct}%",
        f"- **Avg holding time:** wins {summary.avg_holding_win_min} min, "
        f"losses {summary.avg_holding_loss_min} min",
        "",
        "## Exit reasons",
    ]
    if summary.exit_reason_counts:
        for reason, count in summary.exit_reason_counts.most_common():
            lines.append(f"- {reason}: {count}")
    else:
        lines.append("- (no closed trades in period)")

    lines.append("")
    lines.append("## Top losses")
    if summary.top_losses:
        for o in summary.top_losses:
            lines.append(
                f"- `{o.trade_id[:12]}` {o.symbol} {o.side} | "
                f"{o.exit_reason}, PnL={o.pnl_pct}%, "
                f"hold={o.holding_time_min}min"
            )
    else:
        lines.append("- (no losses in period)")

    return "\n".join(lines)


def mistake_category_summary(mistakes_dir: Path) -> str:
    """Подсчёт mistake categories из markdown файлов.

    Парсим заголовок ``# Mistake: <category>`` из каждого .md.
    """
    if not mistakes_dir.exists():
        return ""
    pattern = re.compile(r"^# Mistake: (.+)$", re.MULTILINE)
    counts: Counter[str] = Counter()
    for path in mistakes_dir.glob("*.md"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        match = pattern.search(text)
        if match:
            counts[match.group(1).strip()] += 1

    if not counts:
        return ""
    lines = ["", "## Mistake categories (all-time)"]
    for category, count in counts.most_common():
        lines.append(f"- {category}: {count}")
    return "\n".join(lines)


def run(
    db_path: Path,
    days: int,
    mistakes_dir: Path | None,
    *,
    now_ms: int | None = None,
) -> str:
    """Точка входа. Возвращает текст отчёта."""
    import time

    if now_ms is None:
        now_ms = int(time.time() * 1000)

    log = TradeOutcomeLogger(db_path)
    all_outcomes = list(log.iter_all())
    cutoff_ms = now_ms - days * _MS_PER_DAY
    summary = compute_period_summary(all_outcomes, cutoff_ms=cutoff_ms, days=days)
    text = format_summary(summary)
    if mistakes_dir is not None:
        text += "\n" + mistake_category_summary(mistakes_dir)
    return text


def main() -> None:
    parser = argparse.ArgumentParser(description="Weekly review по outcomes journal")
    parser.add_argument("--db", default="ops/llm-outcomes.sqlite")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument(
        "--mistakes-dir",
        default="журнал/mistakes",
        help="Каталог mistake markdown файлов (пусто = пропустить раздел)",
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(
            f"DB не существует: {db_path}\nЗапусти llm_runner с --outcomes-db",
            file=sys.stderr,
        )
        sys.exit(1)

    mistakes_dir = Path(args.mistakes_dir) if args.mistakes_dir else None
    text = run(db_path, args.days, mistakes_dir)
    print(text)


if __name__ == "__main__":
    main()

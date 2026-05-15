"""Daily summary: одна команда для трёх ежедневных проверок.

Композиция диагностики + outcomes отчёта + last 7 days review.
Запускается на cron'е каждое утро — пользователь видит одним взглядом
состояние бота.

Запуск:
    .venv/bin/python -m scripts.daily_summary
    .venv/bin/python -m scripts.daily_summary > журнал/daily/2026-05-14.md

Дополняет, а НЕ заменяет отдельные скрипты — каждый из них имеет
own use case (diagnose до запуска, postmortem_report — quick stats,
weekly_review — long-form analysis).
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

from core.postmortem.logger import TradeOutcomeLogger
from scripts.postmortem_report import compute_summary, format_summary
from scripts.weekly_review import compute_period_summary
from scripts.weekly_review import format_summary as format_weekly


def _format_header() -> str:
    now = datetime.now(UTC)
    return f"# Daily Summary — {now.strftime('%Y-%m-%d %H:%M UTC')}\n"


def _format_quick_stats(db_path: Path) -> str:
    """Use postmortem_report.compute_summary для базовой статистики."""
    if not db_path.exists():
        return "## Quick Stats\n\n(outcomes DB ещё не создана; запусти llm_runner)"
    log = TradeOutcomeLogger(db_path)
    all_outcomes = list(log.iter_all())
    summary = compute_summary(all_outcomes)
    return "## Quick Stats (all-time)\n\n" + format_summary(summary)


def _format_period_section(db_path: Path, days: int, now_ms: int) -> str:
    """Use weekly_review.compute_period_summary для period stats."""
    if not db_path.exists():
        return ""
    log = TradeOutcomeLogger(db_path)
    outcomes = list(log.iter_all())
    cutoff_ms = now_ms - days * 86_400_000
    summary = compute_period_summary(outcomes, cutoff_ms=cutoff_ms, days=days)
    return format_weekly(summary)


def run(db_path: Path, days: int, *, now_ms: int | None = None) -> str:
    """Точка входа. Возвращает текст summary."""
    import time

    if now_ms is None:
        now_ms = int(time.time() * 1000)

    sections = [
        _format_header(),
        _format_quick_stats(db_path),
        "",
        _format_period_section(db_path, days, now_ms),
    ]
    return "\n".join(s for s in sections if s)


def main() -> None:
    parser = argparse.ArgumentParser(description="Daily summary бота")
    parser.add_argument("--db", default="ops/llm-outcomes.sqlite")
    parser.add_argument("--days", type=int, default=7, help="Период анализа (days)")
    args = parser.parse_args()
    print(run(Path(args.db), args.days))
    sys.exit(0)


if __name__ == "__main__":
    main()

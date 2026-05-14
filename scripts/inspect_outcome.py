"""Debug-утилита: pretty-print одной TradeOutcome со всеми LLM payloads.

Полезно когда хочешь понять "почему этот trade был открыт" — видишь
все 5 субагент-payloadов + coordinator decision.

Запуск:
    .venv/bin/python -m scripts.inspect_outcome <trade_id>
    .venv/bin/python -m scripts.inspect_outcome <prefix>  # partial match

Например:
    .venv/bin/python -m scripts.inspect_outcome 1234567  # prefix match
    .venv/bin/python -m scripts.inspect_outcome 12345678-bingx-order
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from core.postmortem.logger import TradeOutcomeLogger
from core.postmortem.models import TradeOutcome


def _format_outcome(outcome: TradeOutcome) -> str:
    """Pretty markdown-like printout TradeOutcome."""
    lines = [
        f"# Trade {outcome.trade_id}",
        "",
        f"**Symbol:** {outcome.symbol}",
        f"**Side:** {outcome.side}",
        f"**Size:** {outcome.size}",
        f"**Entry:** {outcome.entry_price} @ ts={outcome.entry_time_ms}",
    ]
    if outcome.is_closed:
        lines.extend(
            [
                f"**Exit:** {outcome.exit_price} @ ts={outcome.exit_time_ms}",
                f"**Exit reason:** {outcome.exit_reason}",
                f"**Holding:** {outcome.holding_time_min} min",
                f"**PnL:** {outcome.pnl_usd} USD ({outcome.pnl_pct}%)",
            ]
        )
    else:
        lines.append("**Status:** OPEN")
    if outcome.latency_decision_ms is not None:
        lines.append(f"**Decision latency:** {outcome.latency_decision_ms} ms")
    if outcome.slippage_bps is not None:
        lines.append(f"**Slippage:** {outcome.slippage_bps} bps")

    sections = [
        ("Signal Candidate", outcome.signal_candidate_json),
        ("Market Analyst", outcome.market_analyst_json),
        ("Sentiment Analyst", outcome.sentiment_analyst_json),
        ("Risk Overseer", outcome.risk_overseer_json),
        ("Macro Analyst", outcome.macro_analyst_json),
        ("Coordinator", outcome.coordinator_json),
    ]
    for title, raw in sections:
        lines.append("")
        lines.append(f"## {title}")
        lines.append("```json")
        lines.append(_pretty_json(raw))
        lines.append("```")
    return "\n".join(lines)


def _pretty_json(raw: str) -> str:
    """Re-format JSON-строку с indent=2; если не парсится — возвращаем как есть."""
    try:
        return json.dumps(json.loads(raw), indent=2, ensure_ascii=False)
    except (json.JSONDecodeError, ValueError):
        return raw


def find_outcome(log: TradeOutcomeLogger, query: str) -> TradeOutcome | None:
    """Найти TradeOutcome по точному trade_id или префиксу.

    Если точного match нет — ищем все outcomes и возвращаем первый
    у которого trade_id.startswith(query). При >1 match — возвращаем
    самый recent.
    """
    exact = log.get_by_id(query)
    if exact is not None:
        return exact

    matches = [o for o in log.iter_all() if o.trade_id.startswith(query)]
    if not matches:
        return None
    # Самый recent по entry_time_ms
    matches.sort(key=lambda o: o.entry_time_ms, reverse=True)
    return matches[0]


def run(db_path: Path, query: str) -> int:
    """Точка входа. Returns exit code."""
    if not db_path.exists():
        print(f"DB не существует: {db_path}", file=sys.stderr)
        return 1

    log = TradeOutcomeLogger(db_path)
    outcome = find_outcome(log, query)
    if outcome is None:
        print(f"Outcome '{query}' не найден в журнале", file=sys.stderr)
        return 2

    print(_format_outcome(outcome))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect одной TradeOutcome со всеми payloads")
    parser.add_argument("query", help="trade_id или его префикс")
    parser.add_argument("--db", default="ops/llm-outcomes.sqlite")
    args = parser.parse_args()
    sys.exit(run(Path(args.db), args.query))


if __name__ == "__main__":
    main()

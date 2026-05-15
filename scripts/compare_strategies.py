"""Кросс-стратегия comparator: прогоняет несколько стратегий и сводит
финальную таблицу для сравнения edge.

Запуск:
    .venv/bin/python -m scripts.compare_strategies \\
        --pairs btc_breakout:data/candles/btc-usdt-15m.jsonl \\
        --pairs gold_safety_haven:data/candles/xau-usdt-1h.jsonl \\
        --pairs oil_eia_avoid:data/candles/cl-usdt-15m.jsonl \\
        --pairs stock_earnings_avoid:data/candles/tsla-usdt-15m.jsonl \\
        --split-fraction 0.5 \\
        --output ops/comparison-2026-05-15.json

Каждый аргумент `--pairs` — это `<strategy>:<candles_path>`. Скрипт
запускает scripts.run_backtest для каждой пары через subprocess и собирает
сравнительную таблицу.

Чем отличается от run_batch_backtest: тот прогоняет ОДНУ стратегию по
многим symbol'ам. Этот — МНОГО стратегий по разным candles (потому что
для XAU/CL/TSLA нужны разные timeframe'ы).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from scripts.run_batch_backtest import parse_summary_lines


@dataclass
class StrategyRow:
    strategy: str
    candles: str
    tag: str
    trades: int
    win_rate: str
    profit_factor: str
    sharpe: str
    max_dd: str
    pnl: str


async def _run_one(strategy: str, candles: Path, split_fraction: float | None) -> str:
    cmd = [
        sys.executable,
        "-m",
        "scripts.run_backtest",
        "--strategy",
        strategy,
        "--candles",
        str(candles),
    ]
    if split_fraction is not None:
        cmd += ["--split-fraction", str(split_fraction)]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise SystemExit(f"run_backtest failed for {strategy}/{candles}:\n{stderr.decode()[:500]}")
    return stdout.decode()


def _print_table(rows: list[StrategyRow]) -> None:
    if not rows:
        return
    cols = [
        "strategy",
        "tag",
        "trades",
        "win_rate",
        "profit_factor",
        "sharpe",
        "max_dd",
        "pnl",
    ]
    widths = {c: max(len(c), *(len(str(getattr(r, c))) for r in rows)) for c in cols}
    header = " | ".join(c.ljust(widths[c]) for c in cols)
    sep = "-+-".join("-" * widths[c] for c in cols)
    print(header)
    print(sep)
    for r in rows:
        print(" | ".join(str(getattr(r, c)).ljust(widths[c]) for c in cols))


async def _main_async(args: argparse.Namespace) -> None:
    pairs: list[tuple[str, Path]] = []
    for raw in args.pairs:
        if ":" not in raw:
            raise SystemExit(f"--pairs ожидает 'strategy:candles_path', получил {raw!r}")
        strat, path_str = raw.split(":", 1)
        pairs.append((strat.strip(), Path(path_str.strip())))

    rows: list[StrategyRow] = []
    for strategy, candles in pairs:
        if not candles.exists():
            print(f"⚠ candles file missing: {candles} — skipping {strategy}")
            continue
        print(f"\n=== {strategy} on {candles} ===")
        out = await _run_one(strategy, candles, args.split_fraction)
        is_summary, oos_summary = parse_summary_lines(out)
        for tag, summary in (("is", is_summary), ("oos", oos_summary)):
            if summary is None:
                continue
            rows.append(
                StrategyRow(
                    strategy=strategy,
                    candles=str(candles),
                    tag=tag,
                    trades=int(summary.get("trades", 0)),
                    win_rate=summary.get("win_rate", "—"),
                    profit_factor=summary.get("profit_factor", "—"),
                    sharpe=summary.get("sharpe", "—"),
                    max_dd=summary.get("max_dd", "—"),
                    pnl=summary.get("pnl", "—"),
                )
            )

    print("\n" + "=" * 60 + "\nCROSS-STRATEGY COMPARISON\n" + "=" * 60)
    _print_table(rows)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "pairs": [{"strategy": s, "candles": str(c)} for s, c in pairs],
            "split_fraction": args.split_fraction,
            "timestamp": int(time.time()),
            "rows": [asdict(r) for r in rows],
        }
        with args.output.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        print(f"\nSaved comparison to {args.output}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Cross-strategy backtest comparator")
    parser.add_argument(
        "--pairs",
        action="append",
        required=True,
        help="<strategy>:<candles_path>, повторяй для каждой стратегии",
    )
    parser.add_argument(
        "--split-fraction",
        type=float,
        default=None,
        help="Если задан — каждый прогон делает IS/OOS split",
    )
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    asyncio.run(_main_async(args))


if __name__ == "__main__":
    main()

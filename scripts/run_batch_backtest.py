"""Батч-прогон стратегии на нескольких символах одной командой.

Запуск:
    .venv/bin/python -m scripts.run_batch_backtest \\
        --strategy btc_breakout \\
        --symbols BTC-USDT,ETH-USDT,SOL-USDT \\
        --interval 15m \\
        --split-fraction 0.5

Выводит сравнительную таблицу и сохраняет JSON всех прогонов.
Замена для bash-цикла ``for sym in BTC ETH SOL; do ...``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

_STRATEGY_CHOICES = [
    "btc_breakout",
    "us_session_breakout",
    "trend_ema_4h",
    "gold_safety_haven",
    "oil_eia_avoid",
    "stock_earnings_avoid",
]


@dataclass
class RunSummary:
    symbol: str
    tag: str
    trades: int
    win_rate: str
    profit_factor: str
    sharpe: str
    max_dd: str
    pnl: str


def parse_summary_lines(
    text: str,
) -> tuple[dict[str, str] | None, dict[str, str] | None]:
    """Вытаскивает IS+OOS summary из stdout run_backtest.py.

    Возвращает (is_dict, oos_dict). Если split не задан — OOS = None.
    """
    sections: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for line in text.splitlines():
        if line.startswith("IN-SAMPLE") or line.startswith("OUT-OF-SAMPLE"):
            tag = "is" if line.startswith("IN-SAMPLE") else "oos"
            current = {"tag": tag}
            sections.append(current)
            continue
        if current is None:
            continue
        for key, label in (
            ("Total trades:", "trades"),
            ("Win rate:", "win_rate"),
            ("Profit factor:", "profit_factor"),
            ("Sharpe (annualized):", "sharpe"),
            ("Max drawdown:", "max_dd"),
            ("Total P&L:", "pnl"),
        ):
            if key in line:
                current[label] = line.split(key, 1)[1].strip()
    return (
        sections[0] if sections else None,
        sections[1] if len(sections) > 1 else None,
    )


async def run_single(
    strategy: str,
    symbol: str,
    candles: Path,
    strategy_config: Path | None,
    split_fraction: float | None,
) -> str:
    """Запустить один прогон через subprocess."""
    cmd = [
        ".venv/bin/python",
        "-m",
        "scripts.run_backtest",
        "--strategy",
        strategy,
        "--symbol",
        symbol,
        "--candles",
        str(candles),
    ]
    if strategy_config is not None:
        cmd += ["--strategy-config", str(strategy_config)]
    if split_fraction is not None:
        cmd += ["--split-fraction", str(split_fraction)]
    # `.venv/bin/python` — относительно cwd; используем sys.executable
    # для портабельности.
    import sys

    cmd[0] = sys.executable
    result = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await result.communicate()
    if result.returncode != 0:
        raise SystemExit(f"run_backtest failed for {symbol}:\n{stderr.decode()[:500]}")
    return stdout.decode()


def print_table(rows: list[RunSummary]) -> None:
    if not rows:
        return
    cols = ["symbol", "tag", "trades", "win_rate", "profit_factor", "sharpe", "max_dd", "pnl"]
    widths = {c: max(len(c), *(len(str(getattr(r, c))) for r in rows)) for c in cols}
    header = " | ".join(c.ljust(widths[c]) for c in cols)
    sep = "-+-".join("-" * widths[c] for c in cols)
    print(header)
    print(sep)
    for r in rows:
        print(" | ".join(str(getattr(r, c)).ljust(widths[c]) for c in cols))


async def main_async(args: argparse.Namespace) -> None:
    symbols = [s.strip() for s in args.symbols.split(",")]
    rows: list[RunSummary] = []
    for sym in symbols:
        candles = args.candles_template or Path(f"data/candles/{sym.lower()}-{args.interval}.jsonl")
        print(f"\n=== Running {sym} ===")
        out = await run_single(
            args.strategy,
            sym,
            candles,
            args.strategy_config,
            args.split_fraction,
        )
        is_summary, oos_summary = parse_summary_lines(out)
        for tag, summary in (("is", is_summary), ("oos", oos_summary)):
            if summary is None:
                continue
            rows.append(
                RunSummary(
                    symbol=sym,
                    tag=tag,
                    trades=int(summary.get("trades", 0)),
                    win_rate=summary.get("win_rate", "—"),
                    profit_factor=summary.get("profit_factor", "—"),
                    sharpe=summary.get("sharpe", "—"),
                    max_dd=summary.get("max_dd", "—"),
                    pnl=summary.get("pnl", "—"),
                )
            )

    print("\n" + "=" * 50 + "\nCOMPARATIVE TABLE\n" + "=" * 50)
    print_table(rows)

    # JSON output для дальнейшего анализа.
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "strategy": args.strategy,
            "symbols": symbols,
            "interval": args.interval,
            "split_fraction": args.split_fraction,
            "timestamp": int(time.time()),
            "rows": [r.__dict__ for r in rows],
        }
        with args.output.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        print(f"\nSaved batch summary to {args.output}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch backtest runner")
    parser.add_argument("--strategy", choices=_STRATEGY_CHOICES, required=True)
    parser.add_argument(
        "--symbols",
        required=True,
        help='Comma-separated: "BTC-USDT,ETH-USDT,SOL-USDT"',
    )
    parser.add_argument(
        "--interval",
        default="15m",
        help="Used to build candles path: data/candles/<symbol>-<interval>.jsonl",
    )
    parser.add_argument(
        "--candles-template",
        type=Path,
        default=None,
        help="Override path template (default по symbol+interval)",
    )
    parser.add_argument(
        "--strategy-config",
        type=Path,
        default=None,
    )
    parser.add_argument("--split-fraction", type=float, default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    # Subprocess мы запускаем через asyncio.create_subprocess_exec; на
    # некоторых средах это требует event loop policy. Простой run хватит.
    if False:  # placeholder для clarity — subprocess в main_async.
        subprocess.run(["true"], check=True)
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()

"""Walk-forward backtest: скользящие IS+OOS окна.

Идея: вместо одного split 50/50 разбиваем данные на N последовательных
блоков. Для каждого блока:
- IS = блок (например, 2 мес).
- OOS = следующий блок (1 мес).

Результат: для каждой пары (IS_i, OOS_i) считаем метрики, агрегируем
средние и стабильность (std). Это даёт **гораздо более надёжное**
доказательство edge чем один split.

Запуск:
    .venv/bin/python -m scripts.walk_forward \\
        --candles data/candles/btc-usdt-15m.jsonl \\
        --strategy btc_breakout \\
        --is-days 60 --oos-days 30 --step-days 30
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean, stdev
from typing import Any

from adapters.bingx.models import Kline
from core.backtest import BacktestEngine, BacktestResult, load_config
from core.risk import RiskEngine
from strategies.btc_breakout import BtcBreakoutStrategy
from strategies.btc_breakout import get_default_config as btc_get_default_config
from strategies.trend_ema_4h import TrendEmaStrategy
from strategies.trend_ema_4h import get_default_config as trend_get_default_config
from strategies.us_session_breakout import UsSessionBreakoutStrategy
from strategies.us_session_breakout import get_default_config as us_get_default_config

logger = logging.getLogger(__name__)

_MS_PER_DAY = 86_400_000


@dataclass(frozen=True)
class WindowResult:
    """Результат одного walk-forward окна."""

    window_index: int
    is_start_ms: int
    is_end_ms: int
    oos_start_ms: int
    oos_end_ms: int
    is_trades: int
    is_profit_factor: str
    is_pnl_pct: str
    is_sharpe: str
    oos_trades: int
    oos_profit_factor: str
    oos_pnl_pct: str
    oos_sharpe: str


def _load_candles(path: Path) -> list[Kline]:
    candles: list[Kline] = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            candles.append(Kline.model_validate(json.loads(line)))
    candles.sort(key=lambda k: k.open_time_ms)
    return candles


def _slice_by_time(candles: Sequence[Kline], start_ms: int, end_ms: int) -> list[Kline]:
    return [c for c in candles if start_ms <= c.open_time_ms < end_ms]


def _build_strategy(name: str, risk: RiskEngine) -> Any:
    if name == "btc_breakout":
        return BtcBreakoutStrategy(config=btc_get_default_config(), risk_engine=risk)
    if name == "us_session_breakout":
        return UsSessionBreakoutStrategy(config=us_get_default_config(), risk_engine=risk)
    if name == "trend_ema_4h":
        return TrendEmaStrategy(config=trend_get_default_config(), risk_engine=risk)
    raise SystemExit(f"unknown strategy: {name}")


def _summary_to_dict(result: BacktestResult) -> dict[str, str]:
    s = result.summary
    return {
        "trades": str(s.total_trades),
        "profit_factor": str(s.profit_factor),
        "pnl_pct": str(s.total_pnl_pct),
        "sharpe": str(s.sharpe_ratio),
    }


def walk_forward(
    candles: list[Kline],
    strategy_name: str,
    is_ms: int,
    oos_ms: int,
    step_ms: int,
) -> list[WindowResult]:
    """Скользящие окна по timeline."""
    if not candles:
        return []
    start = candles[0].open_time_ms
    end = candles[-1].open_time_ms
    backtest_cfg = load_config()
    results: list[WindowResult] = []
    is_start = start
    window_idx = 0
    while is_start + is_ms + oos_ms <= end:
        is_end = is_start + is_ms
        oos_start = is_end
        oos_end = oos_start + oos_ms

        is_candles = _slice_by_time(candles, is_start, is_end)
        oos_candles = _slice_by_time(candles, oos_start, oos_end)
        if not is_candles or not oos_candles:
            break

        is_engine = BacktestEngine(backtest_cfg)
        is_strategy = _build_strategy(strategy_name, RiskEngine())
        is_result = is_engine.run(is_strategy, is_candles)

        oos_engine = BacktestEngine(backtest_cfg)
        oos_strategy = _build_strategy(strategy_name, RiskEngine())
        oos_result = oos_engine.run(oos_strategy, oos_candles)

        is_summary = _summary_to_dict(is_result)
        oos_summary = _summary_to_dict(oos_result)
        results.append(
            WindowResult(
                window_index=window_idx,
                is_start_ms=is_start,
                is_end_ms=is_end,
                oos_start_ms=oos_start,
                oos_end_ms=oos_end,
                is_trades=int(is_summary["trades"]),
                is_profit_factor=is_summary["profit_factor"],
                is_pnl_pct=is_summary["pnl_pct"],
                is_sharpe=is_summary["sharpe"],
                oos_trades=int(oos_summary["trades"]),
                oos_profit_factor=oos_summary["profit_factor"],
                oos_pnl_pct=oos_summary["pnl_pct"],
                oos_sharpe=oos_summary["sharpe"],
            )
        )
        window_idx += 1
        is_start += step_ms

    return results


def _aggregate(results: list[WindowResult]) -> dict[str, Any]:
    """Среднее + std по окнам."""
    if not results:
        return {"windows": 0}
    is_pf = [float(r.is_profit_factor) for r in results]
    oos_pf = [float(r.oos_profit_factor) for r in results]
    is_pnl = [float(r.is_pnl_pct) for r in results]
    oos_pnl = [float(r.oos_pnl_pct) for r in results]

    def stat(values: list[float]) -> dict[str, float]:
        if not values:
            return {"mean": 0.0, "std": 0.0, "min": 0.0, "max": 0.0}
        return {
            "mean": round(mean(values), 4),
            "std": round(stdev(values) if len(values) > 1 else 0.0, 4),
            "min": round(min(values), 4),
            "max": round(max(values), 4),
        }

    return {
        "windows": len(results),
        "is_profit_factor": stat(is_pf),
        "oos_profit_factor": stat(oos_pf),
        "is_pnl_pct": stat(is_pnl),
        "oos_pnl_pct": stat(oos_pnl),
        "oos_positive_windows": sum(1 for v in oos_pnl if v > 0),
        "total_oos_trades": sum(r.oos_trades for r in results),
    }


def print_table(results: list[WindowResult]) -> None:
    if not results:
        print("(no windows)")
        return
    header = "win | IS trades IS PF   IS PnL  | OOS trades OOS PF  OOS PnL"
    print(header)
    print("-" * len(header))
    for r in results:
        print(
            f"{r.window_index:3d} | {r.is_trades:9d} {r.is_profit_factor:7s} "
            f"{r.is_pnl_pct:7s}% | {r.oos_trades:10d} {r.oos_profit_factor:7s} "
            f"{r.oos_pnl_pct:7s}%"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Walk-forward backtest")
    parser.add_argument("--candles", type=Path, required=True)
    parser.add_argument(
        "--strategy",
        choices=["btc_breakout", "us_session_breakout", "trend_ema_4h"],
        required=True,
    )
    parser.add_argument("--is-days", type=int, default=60, help="IS window length")
    parser.add_argument("--oos-days", type=int, default=30, help="OOS window length")
    parser.add_argument("--step-days", type=int, default=30, help="Шаг между IS-окнами")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="JSON output (default: ops/walk-forward-<ts>.json)",
    )
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    candles = _load_candles(args.candles)
    print(f"Loaded {len(candles)} candles")

    results = walk_forward(
        candles,
        args.strategy,
        is_ms=args.is_days * _MS_PER_DAY,
        oos_ms=args.oos_days * _MS_PER_DAY,
        step_ms=args.step_days * _MS_PER_DAY,
    )

    print(f"\nWalk-forward windows: {len(results)}")
    print(f"  IS = {args.is_days}d, OOS = {args.oos_days}d, step = {args.step_days}d\n")
    print_table(results)

    agg = _aggregate(results)
    print("\nAGGREGATED:")
    print(json.dumps(agg, indent=2))

    out = args.output or Path(f"ops/walk-forward-{int(time.time())}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "strategy": args.strategy,
        "candles_path": str(args.candles),
        "is_days": args.is_days,
        "oos_days": args.oos_days,
        "step_days": args.step_days,
        "windows": [asdict(r) for r in results],
        "aggregated": agg,
    }
    with out.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"\nSaved to {out}")


if __name__ == "__main__":
    # Не нужен event loop (нет async вызовов в backtest), но для
    # совместимости с другими scripts/* keep main = sync.
    main()


# Async-wrapper только если когда-то понадобится parallel windows.
async def _async_main_placeholder() -> None:
    await asyncio.sleep(0)

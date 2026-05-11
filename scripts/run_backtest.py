"""Прогон стратегии через BacktestEngine на скачанных свечах.

Запуск:
    .venv/bin/python -m scripts.run_backtest \\
        --candles data/candles/btc-usdt-15m.jsonl

Выводит summary в stdout и сохраняет JSON в ``ops/backtest-<timestamp>.json``.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

from adapters.bingx.models import Kline
from core.backtest import BacktestEngine, BacktestResult, load_config
from core.risk import RiskEngine
from strategies.btc_breakout import BtcBreakoutStrategy, get_default_config


def _decimal_to_json(obj: object) -> object:
    """JSON-safe рекурсивная конвертация Decimal → str."""
    if isinstance(obj, Decimal):
        return format(obj.normalize(), "f")
    if isinstance(obj, dict):
        return {k: _decimal_to_json(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [_decimal_to_json(v) for v in obj]
    return obj


def load_candles(path: Path) -> list[Kline]:
    candles: list[Kline] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            raw = json.loads(line)
            candles.append(Kline.model_validate(raw))
    candles.sort(key=lambda k: k.open_time_ms)
    return candles


def print_summary(result: BacktestResult) -> None:
    s = result.summary
    print()
    print("─" * 70)
    print(f"  Total trades:           {s.total_trades}")
    print(f"  Win rate:               {s.win_rate}%")
    print(f"  Avg win / loss:         {s.avg_win_pct}% / {s.avg_loss_pct}%")
    print(f"  Profit factor:          {s.profit_factor}")
    print(f"  Sharpe (annualized):    {s.sharpe_ratio}")
    print(f"  Max drawdown:           {s.max_drawdown_pct}%")
    print(f"  Total P&L:              {s.total_pnl_pct}%")
    print(f"  Final equity:           {s.final_equity}")
    print(f"  Avg trade duration:     {s.avg_trade_duration_minutes} min")
    print("─" * 70)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run BTC breakout backtest")
    parser.add_argument(
        "--candles",
        type=Path,
        default=Path("data/candles/btc-usdt-15m.jsonl"),
    )
    parser.add_argument(
        "--symbol",
        default=None,
        help=(
            "Переопределить symbol в config стратегии (по умолчанию — "
            "из strategies/btc_breakout/config.yaml = BTC-USDT)"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("ops"),
        help="Где сохранить JSON-результат",
    )
    args = parser.parse_args()

    if not args.candles.exists():
        raise SystemExit(
            f"candles not found: {args.candles}\n"
            "Run `python -m scripts.download_klines` first."
        )

    candles = load_candles(args.candles)
    print(f"Loaded {len(candles)} candles from {args.candles}")
    if candles:
        first = candles[0].open_time_ms
        last = candles[-1].open_time_ms
        span_days = (last - first) / 86_400_000
        print(f"  Range: {first} → {last} ({span_days:.1f} days)")

    strategy_cfg = get_default_config()
    if args.symbol is not None:
        strategy_cfg = strategy_cfg.model_copy(update={"symbol": args.symbol})
        print(f"  Symbol override: {strategy_cfg.symbol}")

    strategy = BtcBreakoutStrategy(
        config=strategy_cfg,
        risk_engine=RiskEngine(),
    )
    backtest_cfg = load_config()
    engine = BacktestEngine(backtest_cfg)
    print(
        f"Running backtest: initial_equity={backtest_cfg.initial_equity}, "
        f"fees.taker={backtest_cfg.fees.taker_pct}%, "
        f"slippage={backtest_cfg.slippage_bps}bps"
    )
    result = engine.run(strategy, candles)
    print_summary(result)

    # Сохраняем JSON-результат.
    args.output_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.output_dir / f"backtest-{int(time.time())}.json"
    payload = {
        "summary": _decimal_to_json(asdict(result.summary)),
        "trades": [_decimal_to_json(asdict(t)) for t in result.trades],
        "config": _decimal_to_json(backtest_cfg.model_dump()),
        "candles_path": str(args.candles),
        "candles_count": len(candles),
    }
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"\nSaved result to {out_path}")


if __name__ == "__main__":
    main()

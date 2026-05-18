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
from typing import Any

from adapters.bingx.models import Kline
from core.backtest import BacktestEngine, BacktestResult, Strategy, load_config
from core.risk import RiskEngine
from core.risk import load_config as risk_load_config
from strategies.btc_breakout import BtcBreakoutStrategy, get_default_config
from strategies.btc_breakout.config import load_config as load_strategy_config
from strategies.trend_ema_4h import (
    TrendEmaStrategy,
)
from strategies.trend_ema_4h import (
    get_default_config as trend_get_default_config,
)
from strategies.trend_ema_4h.config import (
    load_config as trend_load_config,
)
from strategies.us_session_breakout import (
    UsSessionBreakoutStrategy,
)
from strategies.us_session_breakout import (
    get_default_config as us_get_default_config,
)
from strategies.us_session_breakout.config import (
    load_config as us_load_config,
)


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
        "--strategy",
        choices=[
            "btc_breakout",
            "us_session_breakout",
            "trend_ema_4h",
            "gold_safety_haven",
            "oil_eia_avoid",
            "stock_earnings_avoid",
            "liquidation_reversal",
            "composite_signal",
        ],
        default="btc_breakout",
        help="Какую стратегию прогонять",
    )
    parser.add_argument(
        "--strategy-config",
        type=Path,
        default=None,
        help=(
            "Путь к альтернативному config стратегии "
            "(например strategies/btc_breakout/config-1h.yaml)"
        ),
    )
    parser.add_argument(
        "--split-fraction",
        type=float,
        default=None,
        help=(
            "Запустить in-sample/out-of-sample split: 0.5 = первая половина "
            "свечей IS, вторая OOS. Без флага — один прогон на всех свечах."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("ops"),
        help="Где сохранить JSON-результат",
    )
    parser.add_argument(
        "--risk-config",
        type=Path,
        default=None,
        help=(
            "Альтернативный risk-config (например с scalp.enabled=true для "
            "скальп-бэктеста). Без флага — дефолтный core/risk/config.yaml."
        ),
    )
    args = parser.parse_args()

    risk_engine = RiskEngine(
        risk_load_config(args.risk_config) if args.risk_config is not None else None
    )
    if args.risk_config is not None:
        print(f"  Risk config override: {args.risk_config}")

    if not args.candles.exists():
        raise SystemExit(
            f"candles not found: {args.candles}\nRun `python -m scripts.download_klines` first."
        )

    candles = load_candles(args.candles)
    print(f"Loaded {len(candles)} candles from {args.candles}")
    if candles:
        first = candles[0].open_time_ms
        last = candles[-1].open_time_ms
        span_days = (last - first) / 86_400_000
        print(f"  Range: {first} → {last} ({span_days:.1f} days)")

    # Загружаем нужный config + factory стратегии.
    strategy_cfg: Any
    strategy_factory: Any
    if args.strategy == "us_session_breakout":
        strategy_cfg = (
            us_load_config(args.strategy_config)
            if args.strategy_config is not None
            else us_get_default_config()
        )

        def _us_factory(cfg: Any) -> Strategy:
            return UsSessionBreakoutStrategy(config=cfg, risk_engine=risk_engine)

        strategy_factory = _us_factory
    elif args.strategy == "trend_ema_4h":
        strategy_cfg = (
            trend_load_config(args.strategy_config)
            if args.strategy_config is not None
            else trend_get_default_config()
        )

        def _trend_factory(cfg: Any) -> Strategy:
            return TrendEmaStrategy(config=cfg, risk_engine=risk_engine)

        strategy_factory = _trend_factory
    elif args.strategy == "gold_safety_haven":
        from strategies.gold_safety_haven import (
            get_default_config as gold_get_default_config,
        )
        from strategies.gold_safety_haven.config import (
            load_config as gold_load_config,
        )

        strategy_cfg = (
            gold_load_config(args.strategy_config)
            if args.strategy_config is not None
            else gold_get_default_config()
        )

        def _gold_factory(cfg: Any) -> Strategy:
            return BtcBreakoutStrategy(config=cfg, risk_engine=risk_engine)

        strategy_factory = _gold_factory
    elif args.strategy == "oil_eia_avoid":
        from strategies.oil_eia_avoid import (
            build_eia_news_calendar,
        )
        from strategies.oil_eia_avoid import (
            get_default_config as oil_get_default_config,
        )
        from strategies.oil_eia_avoid.config import (
            load_config as oil_load_config,
        )

        strategy_cfg = (
            oil_load_config(args.strategy_config)
            if args.strategy_config is not None
            else oil_get_default_config()
        )

        def _oil_factory(cfg: Any) -> Strategy:
            return BtcBreakoutStrategy(
                config=cfg,
                risk_engine=risk_engine,
                news_calendar=build_eia_news_calendar(),
            )

        strategy_factory = _oil_factory
    elif args.strategy == "stock_earnings_avoid":
        from strategies.stock_earnings_avoid import (
            build_earnings_blackout_calendar,
        )
        from strategies.stock_earnings_avoid import (
            get_default_config as stock_get_default_config,
        )
        from strategies.stock_earnings_avoid.config import (
            load_config as stock_load_config,
        )

        strategy_cfg = (
            stock_load_config(args.strategy_config)
            if args.strategy_config is not None
            else stock_get_default_config()
        )

        def _stock_factory(cfg: Any) -> Strategy:
            return BtcBreakoutStrategy(
                config=cfg,
                risk_engine=risk_engine,
                news_calendar=build_earnings_blackout_calendar(cfg.symbol),
            )

        strategy_factory = _stock_factory
    elif args.strategy == "liquidation_reversal":
        from strategies.liquidation_reversal import (
            LiquidationReversalStrategy,
        )
        from strategies.liquidation_reversal import (
            get_default_config as liqrev_default_config,
        )
        from strategies.liquidation_reversal.config import (
            load_config as liqrev_load_config,
        )

        strategy_cfg = (
            liqrev_load_config(args.strategy_config)
            if args.strategy_config is not None
            else liqrev_default_config()
        )
        # --symbol override применяем ДО backfill (иначе backfill качает
        # данные не того символа). Общий override ниже это повторит — ok.
        if args.symbol is not None:
            strategy_cfg = strategy_cfg.model_copy(update={"symbol": args.symbol})

        # Coinglass backfill: liquidation/OI/CVD за диапазон свечей.
        # Без активного плана → пустые провайдеры → no-op (честно 0 сделок).
        from parsers.coinglass.backfill import backfill_providers

        _liq_p, _oi_p, _delta_p = backfill_providers(
            strategy_cfg.symbol,
            strategy_cfg.timeframe,
            start_time_ms=candles[0].open_time_ms if candles else 0,
            end_time_ms=candles[-1].open_time_ms if candles else 0,
        )

        def _liqrev_factory(cfg: Any) -> Strategy:
            return LiquidationReversalStrategy(
                config=cfg,
                risk_engine=risk_engine,
                liquidation_provider=_liq_p,
                oi_provider=_oi_p,
                delta_provider=_delta_p,
            )

        strategy_factory = _liqrev_factory
    elif args.strategy == "composite_signal":
        from strategies.composite_signal import (
            get_default_config as comp_get_default_config,
        )
        from strategies.composite_signal.config import load_config as comp_load_config

        strategy_cfg = (
            comp_load_config(args.strategy_config)
            if args.strategy_config is not None
            else comp_get_default_config()
        )

        def _comp_factory(cfg: Any) -> Strategy:
            from strategies.composite_signal import CompositeSignalStrategy

            return CompositeSignalStrategy(config=cfg, risk_engine=risk_engine)

        strategy_factory = _comp_factory
    else:  # btc_breakout
        strategy_cfg = (
            load_strategy_config(args.strategy_config)
            if args.strategy_config is not None
            else get_default_config()
        )

        def _btc_factory(cfg: Any) -> Strategy:
            return BtcBreakoutStrategy(config=cfg, risk_engine=risk_engine)

        strategy_factory = _btc_factory
    if args.symbol is not None:
        strategy_cfg = strategy_cfg.model_copy(update={"symbol": args.symbol})
        print(f"  Symbol override: {strategy_cfg.symbol}")
    if args.strategy_config is not None:
        print(f"  Strategy config: {args.strategy_config}")
    print(f"  Strategy: {args.strategy}")

    backtest_cfg = load_config()
    print(
        f"Running backtest: initial_equity={backtest_cfg.initial_equity}, "
        f"fees.taker={backtest_cfg.fees.taker_pct}%, "
        f"slippage={backtest_cfg.slippage_bps}bps"
    )

    if args.split_fraction is None:
        _run_single(strategy_factory, strategy_cfg, backtest_cfg, candles, args)
    else:
        _run_split(strategy_factory, strategy_cfg, backtest_cfg, candles, args)


def _run_single(strategy_factory, strategy_cfg, backtest_cfg, candles, args) -> None:  # type: ignore[no-untyped-def]
    strategy = strategy_factory(strategy_cfg)
    engine = BacktestEngine(backtest_cfg)
    result = engine.run(strategy, candles)
    print_summary(result)
    _save_result(result, backtest_cfg, args.candles, len(candles), args.output_dir, "single")


def _run_split(strategy_factory, strategy_cfg, backtest_cfg, candles, args) -> None:  # type: ignore[no-untyped-def]
    fraction = args.split_fraction
    if not 0.1 <= fraction <= 0.9:
        raise SystemExit(f"--split-fraction must be in [0.1, 0.9], got {fraction}")
    split_idx = int(len(candles) * fraction)
    is_candles = candles[:split_idx]
    oos_candles = candles[split_idx:]
    print(f"\nIN-SAMPLE: {len(is_candles)} candles")
    is_engine = BacktestEngine(backtest_cfg)
    is_result = is_engine.run(strategy_factory(strategy_cfg), is_candles)
    print_summary(is_result)
    _save_result(is_result, backtest_cfg, args.candles, len(is_candles), args.output_dir, "is")

    print(f"\nOUT-OF-SAMPLE: {len(oos_candles)} candles")
    oos_engine = BacktestEngine(backtest_cfg)
    oos_result = oos_engine.run(strategy_factory(strategy_cfg), oos_candles)
    print_summary(oos_result)
    _save_result(oos_result, backtest_cfg, args.candles, len(oos_candles), args.output_dir, "oos")


def _save_result(result, backtest_cfg, candles_path, candles_count, output_dir, tag) -> None:  # type: ignore[no-untyped-def]
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"backtest-{tag}-{int(time.time())}.json"
    payload = {
        "summary": _decimal_to_json(asdict(result.summary)),
        "trades": [_decimal_to_json(asdict(t)) for t in result.trades],
        "config": _decimal_to_json(backtest_cfg.model_dump()),
        "candles_path": str(candles_path),
        "candles_count": candles_count,
        "tag": tag,
    }
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"Saved result to {out_path}")


if __name__ == "__main__":
    main()

"""composite_signal — бэктест на Coinglass-истории (план 32).

Turnkey: backfill liq/OI/CVD/funding (Coinglass) → провайдеры →
CompositeSignalStrategy → BacktestEngine + IS/OOS split.

⚠️ Требует ``COINGLASS_API_KEY`` в окружении (.env) И файл свечей.
Без ключа Coinglass отдаёт пусто → скрипт честно выходит, НЕ выдавая
фейковых чисел. Запуск в окружении с ключом:

    .venv/bin/python -m scripts.composite_backtest \\
        --symbol BTC-USDT --candles data/candles/btc-usdt-15m.jsonl \\
        --interval 15m --months 12 --split-fraction 0.6
"""

from __future__ import annotations

import argparse
from bisect import bisect_right
from decimal import Decimal
from pathlib import Path

from core.backtest import BacktestEngine, load_config
from core.risk import RiskEngine
from parsers.coinglass.backfill import backfill_providers, map_symbol
from parsers.coinglass.client import CoinglassClient
from scripts.run_backtest import load_candles, print_summary
from strategies.composite_signal import CompositeSignalStrategy, get_default_config

_DAY_MS = 86_400_000


class TsFundingProvider:
    """Funding по времени (anti-look-ahead): последняя запись с ts ≤ query."""

    def __init__(self, rows: list[tuple[int, Decimal]]) -> None:
        rows = sorted(rows, key=lambda r: r[0])
        self._ts = [r[0] for r in rows]
        self._rate = [r[1] for r in rows]

    def get_funding_rate(self, symbol: str, timestamp_ms: int) -> Decimal | None:
        i = bisect_right(self._ts, timestamp_ms)
        return self._rate[i - 1] if i > 0 else None


def build_providers(
    symbol: str,
    interval: str,
    *,
    start_ms: int,
    end_ms: int,
    client: CoinglassClient | None = None,
) -> tuple[TsFundingProvider, object, object, object]:
    """(funding, liquidation, oi, delta) из Coinglass-истории."""
    cg = client or CoinglassClient()
    liq, oi, delta = backfill_providers(
        symbol, interval, start_time_ms=start_ms, end_time_ms=end_ms, client=cg
    )
    mapping = map_symbol(symbol)
    funding_rows: list[tuple[int, Decimal]] = []
    if mapping is not None:
        exchange, cg_symbol, _coin = mapping
        funding_rows = cg.get_funding_history(
            exchange=exchange,
            symbol=cg_symbol,
            interval=interval,
            start_time_ms=start_ms,
            end_time_ms=end_ms,
        )
    return TsFundingProvider(funding_rows), liq, oi, delta


def _has_data(funding: TsFundingProvider) -> bool:
    """Coinglass-ключ гейтит все эндпоинты разом: пустой funding ⇒
    данных нет вообще (надёжный прокси, без доступа к private-атрибутам
    Static-провайдеров)."""
    return bool(funding._ts)


def main() -> None:
    p = argparse.ArgumentParser(description="composite_signal backtest on Coinglass history")
    p.add_argument("--symbol", default="BTC-USDT")
    p.add_argument("--candles", type=Path, required=True)
    p.add_argument("--interval", default="15m")
    p.add_argument("--months", type=int, default=12)
    p.add_argument("--split-fraction", type=float, default=None)
    args = p.parse_args()

    if not args.candles.exists():
        raise SystemExit(f"candles not found: {args.candles}")
    candles = load_candles(args.candles)
    if not candles:
        raise SystemExit("no candles")
    end_ms = candles[-1].open_time_ms
    start_ms = end_ms - args.months * 30 * _DAY_MS
    # Бэктест ТОЛЬКО на окне, где есть провайдер-данные — иначе свечи
    # вне Coinglass-истории дают 0 сделок и вырожденный sample.
    candles = [c for c in candles if start_ms <= c.open_time_ms <= end_ms]
    if not candles:
        raise SystemExit("no candles within provider window")
    print(f"composite_backtest {args.symbol} {args.interval}: {len(candles)} candles in window")

    funding, liq, oi, delta = build_providers(
        args.symbol, args.interval, start_ms=start_ms, end_ms=end_ms
    )
    if not _has_data(funding):
        raise SystemExit(
            "Coinglass вернул пусто (нет COINGLASS_API_KEY / план не активен). "
            "Валидировать нечем — выходим без фейковых чисел. "
            "Запустите в окружении с ключом."
        )

    cfg = get_default_config().model_copy(update={"symbol": args.symbol})
    bt_cfg = load_config()

    def _make() -> CompositeSignalStrategy:
        return CompositeSignalStrategy(
            cfg,
            RiskEngine(),
            funding_provider=funding,
            liquidation_provider=liq,  # type: ignore[arg-type]
            oi_provider=oi,  # type: ignore[arg-type]
            delta_provider=delta,  # type: ignore[arg-type]
        )

    if args.split_fraction is None:
        res = BacktestEngine(bt_cfg).run(_make(), candles)
        print_summary(res)
        return
    idx = int(len(candles) * args.split_fraction)
    print(f"IN-SAMPLE: {idx} candles")
    print_summary(BacktestEngine(bt_cfg).run(_make(), candles[:idx]))
    print(f"OUT-OF-SAMPLE: {len(candles) - idx} candles")
    print_summary(BacktestEngine(bt_cfg).run(_make(), candles[idx:]))


if __name__ == "__main__":
    main()

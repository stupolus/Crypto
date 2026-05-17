"""Забор CoinGlass-данных (план 33.2 DOLF / Щукин #007).

HOBBYIST жёстко лимитирует (429 на пагинации). Поэтому ОДИН
вызов на серию: limit=1000 точек. 1d → ~2.7г, 4h → ~166д —
этого достаточно для DOLF-фильтра старшего ТФ (Принцип №1,
вход-фильтр, не триггер). OI-эндпоинт на HOBBYIST отдаёт 0 —
честно фиксируем и пропускаем. Пишет data/coinglass/*.jsonl.
Большие паузы между вызовами — бережём rate-limit.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import TypeVar

from parsers.coinglass.backfill import map_symbol
from parsers.coinglass.client import CoinglassClient
from parsers.coinglass.models import CoinglassLiquidationBucket

_COINS = [
    "BTC-USDT", "ETH-USDT", "SOL-USDT", "DOGE-USDT", "XRP-USDT", "BNB-USDT",
]  # fmt: skip
_OUT = Path("data/coinglass")
_DAY = 86_400_000
# (interval, окно_дней) — один вызов, ≤1000 точек.
_SPECS = [("1d", 1000), ("4h", 160)]
_PAUSE = 4.0  # сек между вызовами — HOBBYIST rate-limit

T = TypeVar("T")
_Point = tuple[int, Decimal]


def _span(rows: list[T], ts_of: Callable[[T], int]) -> str:
    if not rows:
        return "ПУСТО"
    lo, hi = ts_of(rows[0]), ts_of(rows[-1])
    d0 = datetime.fromtimestamp(lo / 1000, tz=UTC).date()
    d1 = datetime.fromtimestamp(hi / 1000, tz=UTC).date()
    return f"{len(rows)}т {d0}→{d1} (~{(hi - lo) // _DAY}д)"


def main() -> None:
    cg = CoinglassClient()
    if not cg.configured:
        print("CoinGlass: ключ не настроен (.env COINGLASS_API_KEY) — стоп")
        return
    _OUT.mkdir(parents=True, exist_ok=True)
    now = int(time.time() * 1000)
    print("CoinGlass забор (план 33.2): liq/funding/cvd, 1d+4h, 6 мажоров")
    print("=" * 66)

    def liq_ts(r: CoinglassLiquidationBucket) -> int:
        return r.timestamp_ms

    def pt_ts(r: _Point) -> int:
        return r[0]

    try:
        for sym in _COINS:
            m = map_symbol(sym)
            if m is None:
                print(f"{sym}: нет в _SYMBOL_MAP — пропуск")
                continue
            exch, cgs, _ = m
            base = sym.lower()
            for interval, days in _SPECS:
                start = now - days * _DAY
                liq = cg.get_liquidation_history(
                    exchange=exch, symbol=cgs, interval=interval,
                    start_time_ms=start, end_time_ms=now,
                )  # fmt: skip
                time.sleep(_PAUSE)
                fund: list[_Point] = cg.get_funding_history(
                    exchange=exch, symbol=cgs, interval=interval,
                    start_time_ms=start, end_time_ms=now,
                )  # fmt: skip
                time.sleep(_PAUSE)
                cvd: list[_Point] = cg.get_cvd_history(
                    exchange=exch, symbol=cgs, interval=interval,
                    start_time_ms=start, end_time_ms=now,
                )  # fmt: skip
                time.sleep(_PAUSE)
                with open(_OUT / f"{base}-liq-{interval}.jsonl", "w") as fh:
                    for b in liq:
                        fh.write(
                            json.dumps({
                                "ts": b.timestamp_ms,
                                "long_usd": str(b.long_liquidation_usd),
                                "short_usd": str(b.short_liquidation_usd),
                            })
                            + "\n"
                        )  # fmt: skip
                for nm, series in (("funding", fund), ("cvd", cvd)):
                    with open(_OUT / f"{base}-{nm}-{interval}.jsonl", "w") as fh:
                        for ts, val in series:
                            fh.write(json.dumps({"ts": ts, "v": str(val)}) + "\n")
                print(
                    f"{sym} {interval}: liq {_span(liq, liq_ts)} | "
                    f"fund {_span(fund, pt_ts)} | cvd {_span(cvd, pt_ts)}"
                )
    finally:
        cg.close()
    print("=" * 66)
    print("OI пропущен: HOBBYIST/клиент отдаёт 0 (честно зафиксировано).")
    print("Вход DOLF-фильтра (Принцип №1), НЕ триггер. Интрадей CoinGlass")
    print("так же ограничен, как клайны — это часть честного вывода.")


if __name__ == "__main__":
    main()

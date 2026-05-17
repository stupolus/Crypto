"""Забор CoinGlass-данных (план 33.2 DOLF / Щукин #007).

Тянет liquidation / funding / CVD по 6 мажорам на 1d (глубоко)
и 4h (интрадей, ограниченно HOBBYIST). OI-эндпоинт на HOBBYIST
через текущий клиент отдаёт 0 — фиксируем честно, пропускаем.
Пишет JSONL в data/coinglass/ и печатает фактическое покрытие.
Без подгонки: это вход для DOLF-фильтра, не триггер (Принцип №1).
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
# (interval, сколько дней назад тянуть) — 1d глубоко, 4h интрадей.
_SPECS = [("1d", 1100), ("4h", 220)]

T = TypeVar("T")
_FundPoint = tuple[int, Decimal]


def _paginate(
    fn: Callable[[int, int], list[T]],
    *,
    start_ms: int,
    end_ms: int,
    step_ms: int,
    ts_of: Callable[[T], int],
) -> list[T]:
    out: list[T] = []
    seen: set[int] = set()
    cur = start_ms
    while cur < end_ms:
        win_end = min(cur + 900 * step_ms, end_ms)
        rows = fn(cur, win_end)
        if not rows:
            cur = win_end + step_ms
            continue
        for r in rows:
            ts = ts_of(r)
            if ts not in seen:
                seen.add(ts)
                out.append(r)
        cur = max(ts_of(rows[-1]) + step_ms, cur + step_ms)
        time.sleep(0.4)  # бережём HOBBYIST rate-limit
    out.sort(key=ts_of)
    return out


def _span(rows: list[T], ts_of: Callable[[T], int]) -> str:
    if not rows:
        return "ПУСТО"
    lo = ts_of(rows[0])
    hi = ts_of(rows[-1])
    d0 = datetime.fromtimestamp(lo / 1000, tz=UTC).date()
    d1 = datetime.fromtimestamp(hi / 1000, tz=UTC).date()
    return f"{len(rows)} точек {d0}→{d1} (~{(hi - lo) // _DAY}д)"


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

    def pt_ts(r: _FundPoint) -> int:
        return r[0]

    try:
        for sym in _COINS:
            m = map_symbol(sym)
            if m is None:
                print(f"{sym}: нет в _SYMBOL_MAP — пропуск")
                continue
            exch, cgs, _ = m
            for interval, days in _SPECS:
                start = now - days * _DAY
                step = _DAY if interval == "1d" else _DAY // 6

                def _liq(
                    s: int, e: int, _x: str = exch, _y: str = cgs, _i: str = interval
                ) -> list[CoinglassLiquidationBucket]:
                    return cg.get_liquidation_history(
                        exchange=_x, symbol=_y, interval=_i,
                        start_time_ms=s, end_time_ms=e,
                    )  # fmt: skip

                def _fund(
                    s: int, e: int, _x: str = exch, _y: str = cgs, _i: str = interval
                ) -> list[_FundPoint]:
                    return cg.get_funding_history(
                        exchange=_x, symbol=_y, interval=_i,
                        start_time_ms=s, end_time_ms=e,
                    )  # fmt: skip

                def _cvd(
                    s: int, e: int, _x: str = exch, _y: str = cgs, _i: str = interval
                ) -> list[_FundPoint]:
                    return cg.get_cvd_history(
                        exchange=_x, symbol=_y, interval=_i,
                        start_time_ms=s, end_time_ms=e,
                    )  # fmt: skip

                liq = _paginate(_liq, start_ms=start, end_ms=now, step_ms=step, ts_of=liq_ts)
                fund = _paginate(_fund, start_ms=start, end_ms=now, step_ms=step, ts_of=pt_ts)
                cvd = _paginate(_cvd, start_ms=start, end_ms=now, step_ms=step, ts_of=pt_ts)
                base = sym.lower()
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
    print("Это вход DOLF-фильтра (Принцип №1), НЕ триггер. 1d/4h — глубина")
    print("по факту; интрадей CoinGlass так же ограничен, как клайны.")


if __name__ == "__main__":
    main()

"""Два следующих info-edge probe (план 48):

A. Cross-crypto lead-lag BTC ↔ ETH (12 тестов, Bonferroni α/12).
B. Day-of-week BTC (7 тестов, Bonferroni α/7).

Pre-registered, permutation-based, без сети в тестах. Источник BTC/ETH —
Yahoo (free), без ключей.

Запуск:
    .venv/bin/python -m scripts.extra_edge_probes
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from scripts.download_equity import fetch_yahoo_daily
from scripts.macro_edge_probe import (
    align_by_date,
    conditional_mean_test,
    pct_returns,
    permutation_pvalue_lag,
    permutation_two_sample_mean_diff,
)

_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def _fetch_closes(symbol: str, start_year: int) -> list[tuple[int, float]]:
    rows = fetch_yahoo_daily(symbol, start_year)
    return [(int(r["time"]), float(r["close"])) for r in rows]


def _f(name: str, k: int, obs: float, p: float, th: float) -> str:
    return f"  {name:<22} k={k}  obs={obs:+.4f}  p={p:.4f}  {'★ значимо' if p < th else '—'}"


def _f_dow(day: str, obs: float, p: float, th: float) -> str:
    return f"  {day:<5}  mean_diff={obs:+.5f}  p={p:.4f}  {'★ значимо' if p < th else '—'}"


def probe_cross_crypto(rb: list[float], re_: list[float], n_shuffles: int) -> list[str]:
    th = 0.05 / 12
    lines = [f"Probe A: Cross-crypto (BTC↔ETH), Bonferroni α={th:.5f}", ""]
    lines.append("  Lag-correlation:")
    for k in (1, 2, 3):
        obs, p = permutation_pvalue_lag(rb, re_, k, n_shuffles=n_shuffles, seed=42)
        lines.append(_f("BTC→ETH lag-corr", k, obs, p, th))
        obs, p = permutation_pvalue_lag(re_, rb, k, n_shuffles=n_shuffles, seed=42)
        lines.append(_f("ETH→BTC lag-corr", k, obs, p, th))
    lines.append("")
    lines.append("  Conditional mean (top vs bottom decile):")
    for k in (1, 2, 3):
        obs, p = conditional_mean_test(rb[:-k], re_[k:], q=0.1, n_shuffles=n_shuffles, seed=42)
        lines.append(_f("BTC→ETH cond-mean", k, obs, p, th))
        obs, p = conditional_mean_test(re_[:-k], rb[k:], q=0.1, n_shuffles=n_shuffles, seed=42)
        lines.append(_f("ETH→BTC cond-mean", k, obs, p, th))
    return lines


def probe_day_of_week(btc_ts_ms: list[int], rb: list[float], n_shuffles: int) -> list[str]:
    th = 0.05 / 7
    lines = ["", f"Probe B: Day-of-week BTC, Bonferroni α={th:.5f}", ""]
    # Сопоставление возврата дня T с weekday дня T (rb имеет длину n-1).
    weekdays = [datetime.fromtimestamp(ts / 1000, UTC).weekday() for ts in btc_ts_ms[1:]]
    for w in range(7):
        group = [r for r, wd in zip(rb, weekdays, strict=False) if wd == w]
        other = [r for r, wd in zip(rb, weekdays, strict=False) if wd != w]
        if not group or not other:
            continue
        obs, p = permutation_two_sample_mean_diff(group, other, n_shuffles=n_shuffles, seed=42)
        lines.append(_f_dow(_WEEKDAYS[w], obs, p, th))
    return lines


def main() -> None:
    ap = argparse.ArgumentParser(description="cross-crypto + day-of-week edge probes (план 48)")
    ap.add_argument("--start-year", type=int, default=2018)
    ap.add_argument("--n-shuffles", type=int, default=2000)
    ap.add_argument("--out", type=Path, default=Path("ops/extra-edge-probes.txt"))
    args = ap.parse_args()

    print(f"Fetching BTC-USD + ETH-USD daily (Yahoo) since {args.start_year}…")
    btc = _fetch_closes("BTC-USD", args.start_year)
    eth = _fetch_closes("ETH-USD", args.start_year)
    print(f"  BTC={len(btc)} ETH={len(eth)} bars")
    b, e = align_by_date(btc, eth)
    rb = pct_returns(b)
    re_ = pct_returns(e)
    n = min(len(rb), len(re_))
    rb, re_ = rb[-n:], re_[-n:]
    print(f"  aligned returns: {n}")

    lines: list[str] = [f"extra-edge-probes (start {args.start_year}, n={n})", ""]
    lines += probe_cross_crypto(rb, re_, args.n_shuffles)

    # Для DoW: timestamps выровненных дней (intersection).
    dates_btc = {datetime.fromtimestamp(t / 1000, UTC).date() for t, _ in btc}
    dates_eth = {datetime.fromtimestamp(t / 1000, UTC).date() for t, _ in eth}
    common = sorted(dates_btc & dates_eth)
    common_ts = [
        int(datetime(d.year, d.month, d.day, tzinfo=UTC).timestamp() * 1000) for d in common
    ]
    lines += probe_day_of_week(common_ts[-(n + 1) :], rb, args.n_shuffles)

    report = "\n".join(lines)
    print()
    print(report)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report + "\n", encoding="utf-8")
    print(f"\nsaved to {args.out}")


if __name__ == "__main__":
    main()

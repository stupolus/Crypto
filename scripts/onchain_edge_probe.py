"""On-chain lead-lag edge-probe: stablecoin supply → BTC (план 47).

Pre-registered: H0 = дневная Δ совокупного USD-stablecoin-supply
(DefiLlama, free) НЕ опережает дневной ΔBTC на лагах 1..3. Та же
методика, что macro-probe (план 46): permutation lag-corr +
conditional-mean, Bonferroni α/12.

Запуск:
    .venv/bin/python -m scripts.onchain_edge_probe
"""

from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path
from typing import Any

from scripts.download_equity import _year_to_epoch, fetch_yahoo_daily
from scripts.macro_edge_probe import (
    align_by_date,
    conditional_mean_test,
    pct_returns,
    permutation_pvalue_lag,
)

_LLAMA_URL = "https://stablecoins.llama.fi/stablecoincharts/all"
_UA = "Mozilla/5.0 (compatible; crypto-bot/1.0)"


# ── Чистая обработка ответа (тестируется без сети) ────────────────────


def parse_llama_stablecoin_chart(payload: list[dict[str, Any]]) -> list[tuple[int, float]]:
    """[(ts_ms, total_USD_supply)] из DefiLlama-ответа.

    Берём ``totalCirculatingUSD.peggedUSD`` (USD-pegged суммарно).
    """
    out: list[tuple[int, float]] = []
    for row in payload:
        ts = row.get("date")
        block = row.get("totalCirculatingUSD") or {}
        v = block.get("peggedUSD") if isinstance(block, dict) else None
        if ts is None or v is None:
            continue
        out.append((int(ts) * 1000, float(v)))
    out.sort(key=lambda r: r[0])
    return out


# ── Сеть (только в main) ──────────────────────────────────────────────


def fetch_llama_stablecoin_supply() -> list[tuple[int, float]]:
    req = urllib.request.Request(_LLAMA_URL, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        payload = json.loads(r.read().decode("utf-8"))
    return parse_llama_stablecoin_chart(payload)


def _fetch_btc_daily(start_year: int) -> list[tuple[int, float]]:
    rows = fetch_yahoo_daily("BTC-USD", start_year)
    return [(int(r["time"]), float(r["close"])) for r in rows]


def _format(name: str, k: int, obs: float, p: float, threshold: float) -> str:
    mark = "★ значимо" if p < threshold else "—"
    return f"  {name:<18} k={k}  obs={obs:+.4f}  p={p:.4f}  {mark}"


def main() -> None:
    ap = argparse.ArgumentParser(description="on-chain lead-lag probe (план 47)")
    ap.add_argument("--start-year", type=int, default=2018)
    ap.add_argument("--n-shuffles", type=int, default=2000)
    ap.add_argument("--out", type=Path, default=Path("ops/onchain-edge-probe.txt"))
    args = ap.parse_args()

    print(f"Fetching DefiLlama stablecoin chart + BTC-USD daily since {args.start_year}…")
    start_ms = _year_to_epoch(args.start_year) * 1000
    sup = [r for r in fetch_llama_stablecoin_supply() if r[0] >= start_ms]
    btc = _fetch_btc_daily(args.start_year)
    print(f"  stablecoin supply points: {len(sup)}, BTC points: {len(btc)}")

    s, b = align_by_date(sup, btc)
    print(f"  aligned days: {len(s)}")

    rs = pct_returns(s)
    rb = pct_returns(b)
    n = min(len(rs), len(rb))
    rs, rb = rs[-n:], rb[-n:]
    print(f"  aligned returns: {n}")

    threshold = 0.05 / 12  # Bonferroni
    lines: list[str] = [
        f"on-chain probe (start {args.start_year}, n={n}, Bonferroni α={threshold:.5f})",
        "",
        "Lag-correlation (perm test, ΔSupply → ΔBTC):",
    ]
    for k in (1, 2, 3):
        obs, pv = permutation_pvalue_lag(rs, rb, k, n_shuffles=args.n_shuffles, seed=42)
        lines.append(_format("Stablecoin→BTC", k, obs, pv, threshold))

    lines += ["", "Conditional mean (top vs bottom decile by ΔSupply, perm test):"]
    for k in (1, 2, 3):
        if k >= len(rs):
            continue
        obs, pv = conditional_mean_test(rs[:-k], rb[k:], q=0.1, n_shuffles=args.n_shuffles, seed=42)
        lines.append(_format("Stablecoin→BTC", k, obs, pv, threshold))

    report = "\n".join(lines)
    print()
    print(report)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report + "\n", encoding="utf-8")
    print(f"\nsaved to {args.out}")


if __name__ == "__main__":
    main()

"""Macro lead-lag edge-probe (план 46, шаг B-1).

Pre-registered: тестируем, опережают ли дневные ΔDXY/ΔVIX дневной
ΔBTC на лагах 1..3 дня. Чистые перестановочные тесты (без scipy).

Запуск (Yahoo, без ключей):
    .venv/bin/python -m scripts.macro_edge_probe

Вердикт по Bonferroni α/12 = 0.00417 (см. plans/46).
"""

from __future__ import annotations

import argparse
import math
import random
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from scripts.download_equity import fetch_yahoo_daily

# ── Чистые статистики (без сети) ──────────────────────────────────────


def pct_returns(closes: Sequence[float]) -> list[float]:
    return [closes[i] / closes[i - 1] - 1.0 for i in range(1, len(closes)) if closes[i - 1] > 0]


def pearson(x: Sequence[float], y: Sequence[float]) -> float:
    n = len(x)
    if n < 2 or n != len(y):
        return 0.0
    mx = sum(x) / n
    my = sum(y) / n
    num = sum((x[i] - mx) * (y[i] - my) for i in range(n))
    dx = math.sqrt(sum((v - mx) ** 2 for v in x))
    dy = math.sqrt(sum((v - my) ** 2 for v in y))
    return num / (dx * dy) if dx > 0 and dy > 0 else 0.0


def lag_corr(x: Sequence[float], y: Sequence[float], k: int) -> float:
    """Pearson(x_t, y_{t+k}) — опережает ли x доходность y на k шагов."""
    if k < 1 or len(x) <= k:
        return 0.0
    return pearson(list(x[:-k]), list(y[k:]))


def permutation_pvalue_lag(
    x: Sequence[float], y: Sequence[float], k: int, *, n_shuffles: int, seed: int = 0
) -> tuple[float, float]:
    """(observed_corr, two-sided p) для lag-corr под H0 шаффла y."""
    obs = lag_corr(x, y, k)
    rng = random.Random(seed)
    y_lagged = list(y[k:])
    x_trim = list(x[:-k])
    ge = 0
    for _ in range(n_shuffles):
        shuf = y_lagged[:]
        rng.shuffle(shuf)
        if abs(pearson(x_trim, shuf)) >= abs(obs):
            ge += 1
    return obs, (ge + 1) / (n_shuffles + 1)


def conditional_mean_test(
    x: Sequence[float], y_next: Sequence[float], *, q: float, n_shuffles: int, seed: int = 0
) -> tuple[float, float]:
    """Сравниваем mean(y_next | x в верхней дециле) - mean(y_next | x в нижней).
    Permutation p (двусторонний)."""
    n = min(len(x), len(y_next))
    pairs = sorted(zip(x[:n], y_next[:n], strict=False), key=lambda p: p[0])
    k = max(1, int(n * q))
    bot = [b for _, b in pairs[:k]]
    top = [b for _, b in pairs[-k:]]
    obs = (sum(top) / len(top)) - (sum(bot) / len(bot))
    pool = bot + top
    rng = random.Random(seed)
    ge = 0
    for _ in range(n_shuffles):
        rng.shuffle(pool)
        b2 = pool[: len(bot)]
        t2 = pool[len(bot) :]
        diff = (sum(t2) / len(t2)) - (sum(b2) / len(b2))
        if abs(diff) >= abs(obs):
            ge += 1
    return obs, (ge + 1) / (n_shuffles + 1)


def permutation_two_sample_mean_diff(
    a: Sequence[float], b: Sequence[float], *, n_shuffles: int, seed: int = 0
) -> tuple[float, float]:
    """mean(a) − mean(b) под H0 обменимости. (obs, two-sided p)."""
    if not a or not b:
        return 0.0, 1.0
    obs = sum(a) / len(a) - sum(b) / len(b)
    pool = list(a) + list(b)
    na = len(a)
    rng = random.Random(seed)
    ge = 0
    for _ in range(n_shuffles):
        rng.shuffle(pool)
        a2 = pool[:na]
        b2 = pool[na:]
        diff = sum(a2) / len(a2) - sum(b2) / len(b2)
        if abs(diff) >= abs(obs):
            ge += 1
    return obs, (ge + 1) / (n_shuffles + 1)


def align_by_date(*series: Sequence[tuple[int, float]]) -> list[list[float]]:
    """По общему UTC-дню (intersection). Каждая серия: list[(ts_ms, value)]."""
    dicts = [{datetime.fromtimestamp(t / 1000, UTC).date(): v for t, v in s} for s in series]
    common = sorted(set.intersection(*(set(d.keys()) for d in dicts)))
    return [[d[k] for k in common] for d in dicts]


# ── Сеть (только в main) ──────────────────────────────────────────────


def _fetch_closes(symbol: str, start_year: int) -> list[tuple[int, float]]:
    rows = fetch_yahoo_daily(symbol, start_year)
    return [(int(r["time"]), float(r["close"])) for r in rows]


def _format(name: str, k: int, obs: float, p: float, threshold: float) -> str:
    mark = "★ значимо" if p < threshold else "—"
    return f"  {name:<14} k={k}  obs={obs:+.4f}  p={p:.4f}  {mark}"


def main() -> None:
    p = argparse.ArgumentParser(description="macro lead-lag edge probe (плана 46)")
    p.add_argument("--start-year", type=int, default=2018)
    p.add_argument("--n-shuffles", type=int, default=2000)
    p.add_argument("--out", type=Path, default=Path("ops/macro-edge-probe.txt"))
    args = p.parse_args()

    print(f"Fetching daily (Yahoo, no key) since {args.start_year}…")
    btc = _fetch_closes("BTC-USD", args.start_year)
    vix = _fetch_closes("^VIX", args.start_year)
    dxy = _fetch_closes("DX-Y.NYB", args.start_year)
    print(f"  BTC={len(btc)} VIX={len(vix)} DXY={len(dxy)} bars")

    # Выровнять по общему UTC-дню (intersection).
    b, v, d = align_by_date(btc, vix, dxy)
    print(f"  aligned days: {len(b)}")

    rb = pct_returns(b)
    rv = pct_returns(v)
    rd = pct_returns(d)
    n = min(len(rb), len(rv), len(rd))
    rb, rv, rd = rb[-n:], rv[-n:], rd[-n:]
    print(f"  aligned returns: {n}")

    # Bonferroni: 3 lags × 2 тестов × 2 факторов = 12 → α/12 = 0.00417.
    threshold = 0.05 / 12
    lines: list[str] = [
        f"macro-edge probe (start {args.start_year}, n={n}, Bonferroni α={threshold:.5f})",
        "",
        "Lag-correlation (perm test):",
    ]
    for fname, x in (("VIX→BTC", rv), ("DXY→BTC", rd)):
        for k in (1, 2, 3):
            obs, pv = permutation_pvalue_lag(x, rb, k, n_shuffles=args.n_shuffles, seed=42)
            lines.append(_format(fname, k, obs, pv, threshold))

    lines += ["", "Conditional mean (top vs bottom decile, perm test):"]
    for fname, x in (("VIX→BTC", rv), ("DXY→BTC", rd)):
        for k in (1, 2, 3):
            if k >= len(x):
                continue
            obs, pv = conditional_mean_test(
                x[:-k], rb[k:], q=0.1, n_shuffles=args.n_shuffles, seed=42
            )
            lines.append(_format(fname, k, obs, pv, threshold))

    report = "\n".join(lines)
    print()
    print(report)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report + "\n", encoding="utf-8")
    print(f"\nsaved to {args.out}")


if __name__ == "__main__":
    main()

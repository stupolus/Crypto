"""Cross-sectional momentum — research-бэктест (план 29, вариант B).

⚠️ SURVIVORSHIP BIAS ВСТРОЕН. Вселенная — фиксированный список крупных
US-имён, существующих СЕГОДНЯ. Делистнутые проигравшие отсутствуют
(план 28). Любой плюс здесь — оптимистичный ПОТОЛОК, НЕ развёртываемый
edge. Не для live. Это research-инструмент: не трогает Strategy
protocol / раннеры / core.risk.

Параметры pre-registered в plans/29-equity-momentum-bounded-bias.

Запуск:
    .venv/bin/python -m scripts.momentum_backtest
"""

from __future__ import annotations

import argparse
import json
import math
import urllib.parse
import urllib.request
from typing import Any

# Pre-registered вселенная (зафиксирована ДО прогона). Источник
# survivorship-bias — она. Крупные ликвидные US-имена, листинг ≤ ~2012.
UNIVERSE: tuple[str, ...] = (
    "AAPL",
    "MSFT",
    "AMZN",
    "GOOGL",
    "NVDA",
    "META",
    "JPM",
    "JNJ",
    "XOM",
    "KO",
    "PEP",
    "WMT",
    "HD",
    "PG",
    "CVX",
    "MRK",
    "PFE",
    "CSCO",
    "INTC",
    "ORCL",
    "IBM",
    "DIS",
    "MCD",
    "NKE",
    "T",
    "VZ",
    "BA",
    "CAT",
    "GE",
    "MMM",
    "WFC",
    "BAC",
    "C",
    "AXP",
    "UNH",
    "ABT",
    "TXN",
    "QCOM",
    "AMGN",
    "COST",
    "GS",
    "MS",
    "ADBE",
    "CRM",
    "AMD",
)

_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{s}"
_UA = "Mozilla/5.0 (compatible; crypto-bot/1.0)"
_DAY_MS = 86_400_000


# ── Чистые функции (тестируются без сети) ────────────────────────────


def momentum_score(closes: list[float], lookback: int, skip: int) -> float | None:
    """12-1 momentum: доходность за `lookback` баров, исключая последние
    `skip` (Jegadeesh-Titman). None если истории не хватает."""
    need = lookback + skip + 1
    if len(closes) < need:
        return None
    recent = closes[-1 - skip]
    past = closes[-1 - skip - lookback]
    if past <= 0:
        return None
    return recent / past - 1.0


def select_top(scores: dict[str, float], k: int) -> list[str]:
    """Top-k символов по убыванию momentum (детерминированно)."""
    ordered = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    return [s for s, _ in ordered[:k]]


def _align(
    prices: dict[str, list[tuple[int, float]]],
) -> tuple[list[int], dict[str, dict[int, float]]]:
    """Общая ось дат (union) + быстрый доступ по ts."""
    axis: set[int] = set()
    by_ts: dict[str, dict[int, float]] = {}
    for sym, series in prices.items():
        d = {ts: px for ts, px in series}
        by_ts[sym] = d
        axis.update(d)
    return sorted(axis), by_ts


def simulate(
    prices: dict[str, list[tuple[int, float]]],
    *,
    k: int,
    lookback: int,
    skip: int,
    rebal: int,
    cost_pct: float,
) -> list[tuple[int, float]]:
    """Equal-weight long-only momentum. Возвращает дневную equity-кривую
    [(ts_ms, equity)], старт equity = 1.0."""
    axis, by_ts = _align(prices)
    equity = 1.0
    curve: list[tuple[int, float]] = []
    held: list[str] = []
    # история closes по символу до текущего индекса (для momentum).
    hist: dict[str, list[float]] = {s: [] for s in prices}
    prev_px: dict[str, float] = {}

    for i, ts in enumerate(axis):
        # дневная доходность портфеля по удерживаемым.
        rets: list[float] = []
        for s in held:
            p = by_ts[s].get(ts)
            pp = prev_px.get(s)
            if p is not None and pp is not None and pp > 0:
                rets.append(p / pp - 1.0)
        if rets:
            equity *= 1.0 + sum(rets) / len(rets)

        # обновляем историю/last-price.
        for s in prices:
            p = by_ts[s].get(ts)
            if p is not None:
                hist[s].append(p)
                prev_px[s] = p

        # ребаланс.
        if i % rebal == 0:
            scores: dict[str, float] = {}
            for s in prices:
                ms = momentum_score(hist[s], lookback, skip)
                if ms is not None:
                    scores[s] = ms
            if scores:
                new_held = select_top(scores, k)
                turnover = len(set(new_held) ^ set(held)) / max(len(new_held), 1)
                equity *= 1.0 - cost_pct / 100.0 * turnover
                held = new_held

        curve.append((ts, equity))
    return curve


def _window_metrics(curve: list[tuple[int, float]]) -> dict[str, float]:
    eqs = [e for _, e in curve]
    if len(eqs) < 2 or eqs[0] <= 0:
        return {"pnl_pct": 0.0, "pf": 0.0, "sharpe": 0.0, "max_dd_pct": 0.0}
    rets = [eqs[j] / eqs[j - 1] - 1.0 for j in range(1, len(eqs))]
    gains = sum(r for r in rets if r > 0)
    losses = -sum(r for r in rets if r < 0)
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / len(rets)
    sd = math.sqrt(var)
    peak = eqs[0]
    max_dd = 0.0
    for e in eqs:
        peak = max(peak, e)
        max_dd = max(max_dd, (peak - e) / peak)
    return {
        "pnl_pct": (eqs[-1] / eqs[0] - 1.0) * 100.0,
        "pf": gains / losses if losses > 0 else (gains if gains > 0 else 0.0),
        "sharpe": (mean / sd * math.sqrt(252)) if sd > 0 else 0.0,
        "max_dd_pct": max_dd * 100.0,
    }


def walk_forward_split(
    curve: list[tuple[int, float]], *, is_days: int, oos_days: int, step_days: int
) -> list[dict[str, float]]:
    """Календарные OOS-окна по equity-кривой."""
    if not curve:
        return []
    start = curve[0][0]
    end = curve[-1][0]
    out: list[dict[str, float]] = []
    is_ms, oos_ms, step_ms = is_days * _DAY_MS, oos_days * _DAY_MS, step_days * _DAY_MS
    cursor = start
    while cursor + is_ms + oos_ms <= end:
        o0 = cursor + is_ms
        o1 = o0 + oos_ms
        seg = [(t, e) for t, e in curve if o0 <= t < o1]
        if len(seg) >= 2:
            out.append(_window_metrics(seg))
        cursor += step_ms
    return out


# ── Сеть (вне тестов) ────────────────────────────────────────────────


def _parse_adjclose(payload: dict[str, Any]) -> list[tuple[int, float]]:
    res = payload["chart"]["result"]
    if not res:
        return []
    b = res[0]
    ts = b["timestamp"]
    adj = b["indicators"]["adjclose"][0]["adjclose"]
    rows = [(int(t) * 1000, float(a)) for t, a in zip(ts, adj, strict=False) if a is not None]
    rows.sort(key=lambda r: r[0])
    return rows


def fetch_adjclose(symbol: str, start_epoch: int) -> list[tuple[int, float]]:
    qs = urllib.parse.urlencode(
        {"period1": start_epoch, "period2": 9_999_999_999, "interval": "1d", "events": "split"}
    )
    url = f"{_CHART.format(s=urllib.parse.quote(symbol))}?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return _parse_adjclose(json.loads(r.read().decode("utf-8")))


def main() -> None:
    p = argparse.ArgumentParser(description="Cross-sectional momentum research backtest")
    p.add_argument("--k", type=int, default=10)
    p.add_argument("--lookback", type=int, default=252)
    p.add_argument("--skip", type=int, default=21)
    p.add_argument("--rebal", type=int, default=21)
    p.add_argument("--cost-pct", type=float, default=0.05)
    p.add_argument("--is-days", type=int, default=504)
    p.add_argument("--oos-days", type=int, default=252)
    p.add_argument("--step-days", type=int, default=252)
    p.add_argument("--start-epoch", type=int, default=1104537600)  # 2005-01-01
    args = p.parse_args()

    print("⚠️ SURVIVORSHIP-BIASED research backtest — оптимистичный потолок, НЕ для live.")
    prices: dict[str, list[tuple[int, float]]] = {}
    for s in UNIVERSE:
        try:
            series = fetch_adjclose(s, args.start_epoch)
        except Exception as e:
            print(f"  skip {s}: {e}")
            continue
        if len(series) > args.lookback + args.skip + 5:
            prices[s] = series
    print(f"universe loaded: {len(prices)}/{len(UNIVERSE)} symbols")

    curve = simulate(
        prices,
        k=args.k,
        lookback=args.lookback,
        skip=args.skip,
        rebal=args.rebal,
        cost_pct=args.cost_pct,
    )
    wins = walk_forward_split(
        curve, is_days=args.is_days, oos_days=args.oos_days, step_days=args.step_days
    )
    n = len(wins)
    if n:

        def mean(key: str) -> float:
            return sum(w[key] for w in wins) / n

        pos = sum(1 for w in wins if w["pnl_pct"] > 0)
        print(f"windows={n}")
        print(f"OOS PF mean   = {mean('pf'):.2f}")
        print(f"OOS PnL% mean = {mean('pnl_pct'):+.2f}")
        print(f"OOS Sharpe    = {mean('sharpe'):.2f}")
        print(f"OOS maxDD%    = {mean('max_dd_pct'):.2f}")
        print(f"OOS+ windows  = {pos}/{n}")
    else:
        print("no OOS windows (insufficient history)")


if __name__ == "__main__":
    main()

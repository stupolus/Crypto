"""Проверка гипотезы «снизить Sharpe» — честно, с цифрами (план 26).

Снижение порога Sharpe НЕ создаёт edge — оно снижает уверенность,
что edge вообще есть. Считаем для лучших кандидатов TSMOM:
- annualized Sharpe;
- t-стат и p-value среднемесячной доходности (значим ли edge);
- Sharpe ПОСЛЕ издержек на смену позиции (флипы сигнала) —
  реалистичная стоимость перпа BingX, не чистый индекс.

Вывод печатается по каждому порогу: что реально проходит и
остаётся ли статзначимым/прибыльным после costs.
"""

from __future__ import annotations

import math

from core.signals.external_signal import _PERP_TO_UNDERLYING
from parsers.macro.seasonality import _fetch_monthly_closes

_LOOKBACK = 12
# Реалистичная round-trip стоимость смены позиции на тонком
# BingX-перпе (комиссия+проскальзывание+funding-дрейф), доля.
_FLIP_COST = 0.003


def _tsmom(closes: list[float]) -> list[tuple[float, int]]:
    """[(ret_t+1·sign, flip)] — flip=1 если знак сменился."""
    out: list[tuple[float, int]] = []
    prev_sig = 0.0
    for t in range(_LOOKBACK, len(closes) - 1):
        if closes[t - _LOOKBACK] <= 0 or closes[t] <= 0:
            continue
        sig = 1.0 if closes[t] / closes[t - _LOOKBACK] - 1.0 > 0 else -1.0
        nxt = closes[t + 1] / closes[t] - 1.0
        flip = 1 if sig != prev_sig and prev_sig != 0.0 else 0
        out.append((sig * nxt, flip))
        prev_sig = sig
    return out


def _stats(rows: list[tuple[float, int]]) -> dict[str, float]:
    rets = [r for r, _ in rows]
    n = len(rets)
    if n < 4:
        return {}
    mean = sum(rets) / n
    var = sum((x - mean) ** 2 for x in rets) / (n - 1)
    std = math.sqrt(var)
    sharpe = mean / std * math.sqrt(12) if std > 0 else 0.0
    # t-стат среднего (мес), df=n-1; p двусторонний через нормальную аппр.
    t = mean / (std / math.sqrt(n)) if std > 0 else 0.0
    p = math.erfc(abs(t) / math.sqrt(2))
    # после издержек: вычесть _FLIP_COST на каждом флипе.
    net = [r - (_FLIP_COST if f else 0.0) for r, f in rows]
    nmean = sum(net) / n
    nstd = math.sqrt(sum((x - nmean) ** 2 for x in net) / (n - 1))
    nsharpe = nmean / nstd * math.sqrt(12) if nstd > 0 else 0.0
    eq = 1.0
    for x in net:
        eq *= 1 + x
    return {
        "n": float(n),
        "sharpe": sharpe,
        "t": t,
        "p": p,
        "net_sharpe": nsharpe,
        "net_ret_pct": (eq - 1) * 100,
        "flips": float(sum(f for _, f in rows)),
    }


def main() -> None:
    unders = sorted(set(_PERP_TO_UNDERLYING.values()))
    print("Гипотеза «снизить Sharpe»: OOS-метрики TSMOM по базовым активам")
    print("(t>1.96 ≈ значим p<0.05; net — после 0.3% за флип, как на перпе)")
    print("-" * 80)
    print(f"{'актив':8s} | n | Sharpe |   t   |  p    | netSharpe | netRet% | flips")
    print("-" * 80)
    rows_pass: dict[float, list[str]] = {0.8: [], 0.5: [], 0.3: [], 0.0: []}
    for u in unders:
        series = _fetch_monthly_closes(u, years=20)
        closes = [c for _, c in series]
        if len(closes) < _LOOKBACK + 8:
            continue
        rows = _tsmom(closes)
        oos = rows[len(rows) // 2 :]
        s = _stats(oos)
        if not s:
            continue
        print(
            f"{u:8s} | {int(s['n']):3d} | {s['sharpe']:+5.2f} | "
            f"{s['t']:+5.2f} | {s['p']:.3f} | {s['net_sharpe']:+8.2f} | "
            f"{s['net_ret_pct']:+7.1f} | {int(s['flips'])}"
        )
        for thr in rows_pass:
            if s["sharpe"] > thr and s["net_sharpe"] > 0 and int(s["n"]) >= 30:
                rows_pass[thr].append(u)
    print("-" * 80)
    for thr in sorted(rows_pass, reverse=True):
        names = rows_pass[thr] or ["—"]
        print(f"Порог Sharpe>{thr}: проходят (и net>0) → {', '.join(names)}")
    print(
        "\nЧестно: снижение порога НЕ добавляет edge. Оно лишь принимает\n"
        "стратегии, чей сигнал статистически неотличим от нуля (t<1.96)\n"
        "и/или убыточен после издержек перпа (net). Это рост риска\n"
        "разорения, а не прибыль."
    )


if __name__ == "__main__":
    main()

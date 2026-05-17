"""Vol-scaled диверсифицированный TSMOM-портфель (Moskowitz 2012).

Законный путь поднять Sharpe (НЕ снижение порога): слабые
отдельные активы (Sharpe 0.3–0.5) комбинируются в диверсиф.
портфель с обратным масштабированием по ex-ante волатильности.
Именно так оригинал получает Sharpe>1 из слабых слотов.

Дисциплина:
- БЕЗ cherry-pick активов: весь сопоставленный юниверс
  (external_signal карта), включая убыточные standalone
  (нефть) — диверсификация обязана это переваривать.
- target_vol = константа нормализации (НЕ подгон: масштабирует
  кривую, Sharpe не меняет).
- vol = trailing 12-мес реализованная (look-ahead-safe).
- equal-weight по активам после vol-scaling (нет пер-актив
  оптимизации → нет дреджа).
- Гейт: OOS PF>1.3 И Sharpe>0.8 И ≥30 + t-стат + walk-forward.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

from core.signals.external_signal import _PERP_TO_UNDERLYING
from parsers.macro.seasonality import _fetch_monthly_closes

_LOOKBACK = 12  # мес сигнала (Moskowitz)
_VOL_WIN = 12  # мес окна ex-ante волатильности
_TARGET_VOL = 0.10  # годовая, константа нормализации (не подгон)
_FLIP_COST = 0.003  # round-trip на перпе (доля)


def _ym(ts: int) -> tuple[int, int]:
    d = datetime.fromtimestamp(ts, tz=UTC)
    return d.year, d.month


def _asset_positions(
    closes: list[float], ym: list[tuple[int, int]]
) -> dict[tuple[int, int], tuple[float, float]]:
    """{ (год,мес) : (vol-scaled позиция, реализованная доходность t+1) }.

    Позиция в конце месяца t применяется к доходности t→t+1.
    """
    out: dict[tuple[int, int], tuple[float, float]] = {}
    rets = [
        (closes[i] / closes[i - 1] - 1.0) if closes[i - 1] > 0 else 0.0
        for i in range(1, len(closes))
    ]
    # rets[i] соответствует переходу closes[i]→closes[i+1]; индексация:
    # на конец месяца t (closes index t) знаем доходности rets[:t].
    for t in range(_LOOKBACK, len(closes) - 1):
        if closes[t - _LOOKBACK] <= 0 or closes[t] <= 0:
            continue
        sig = 1.0 if closes[t] / closes[t - _LOOKBACK] - 1.0 > 0 else -1.0
        window = rets[max(0, t - _VOL_WIN) : t]  # только прошлое
        if len(window) < _VOL_WIN // 2:
            continue
        mean = sum(window) / len(window)
        var = sum((x - mean) ** 2 for x in window) / (len(window) - 1)
        vol_m = math.sqrt(var)
        vol_a = vol_m * math.sqrt(12)
        if vol_a <= 0:
            continue
        pos = sig * (_TARGET_VOL / vol_a)
        fwd = closes[t + 1] / closes[t] - 1.0
        out[ym[t]] = (pos, fwd)
    return out


def _metrics(rets: list[float], tag: str) -> str:
    if len(rets) < 4:
        return f"{tag}: n={len(rets)} (мало)"
    n = len(rets)
    mean = sum(rets) / n
    var = sum((x - mean) ** 2 for x in rets) / (n - 1)
    std = math.sqrt(var)
    sharpe = mean / std * math.sqrt(12) if std > 0 else 0.0
    t = mean / (std / math.sqrt(n)) if std > 0 else 0.0
    p = math.erfc(abs(t) / math.sqrt(2))
    wins = sum(r for r in rets if r > 0)
    losses = -sum(r for r in rets if r < 0)
    pf = float("inf") if losses == 0 else wins / losses
    eq = 1.0
    peak = 1.0
    mdd = 0.0
    for r in rets:
        eq *= 1 + r
        peak = max(peak, eq)
        mdd = max(mdd, (peak - eq) / peak)
    pf_s = "inf" if pf == float("inf") else f"{pf:.2f}"
    gate = "✓" if (pf > 1.3 and sharpe > 0.8 and n >= 30) else "✗"
    return (
        f"{tag}: n={n:3d} PF={pf_s:>4s} Sharpe={sharpe:+4.2f} "
        f"t={t:+4.2f} p={p:.3f} maxDD={mdd * 100:4.1f}% "
        f"ret={(eq - 1) * 100:+7.1f}% {gate}"
    )


def main() -> None:
    unders = sorted(set(_PERP_TO_UNDERLYING.values()))
    # (год,мес) → список (pos, fwd) по всем активам, имеющим данные.
    bucket: dict[tuple[int, int], list[tuple[float, float]]] = {}
    used = 0
    for u in unders:
        series = _fetch_monthly_closes(u, years=20)
        if len(series) < _LOOKBACK + _VOL_WIN + 4:
            continue
        used += 1
        closes = [c for _, c in series]
        ym = [_ym(ts) for ts, _ in series]
        for key, val in _asset_positions(closes, ym).items():
            bucket.setdefault(key, []).append(val)
    if not bucket:
        print("Yahoo недоступен — портфель не построен (no-op)")
        return
    months = sorted(bucket)
    port: list[float] = []
    for mi, key in enumerate(months):
        rows = bucket[key]
        # equal-weight среднее vol-scaled позиций; доходность портфеля.
        r = sum(pos * fwd for pos, fwd in rows) / len(rows)
        # издержки: грубо — стоимость пропорц. среднему |Δpos|.
        avg_abs_pos = sum(abs(pos) for pos, _ in rows) / len(rows)
        cost = _FLIP_COST * avg_abs_pos if mi > 0 else 0.0
        port.append(r - cost)
    half = len(port) // 2
    print(f"Vol-scaled диверсиф. TSMOM-портфель: {used} активов, {len(port)} мес")
    print(f"target_vol={_TARGET_VOL:.0%} (константа), vol-окно {_VOL_WIN}м, costs вкл.")
    print("-" * 78)
    print(_metrics(port[:half], "IS "))
    print(_metrics(port[half:], "OOS"))
    print(_metrics(port, "ALL"))
    # Walk-forward: непересекающиеся окна по 24 мес.
    print("-" * 78)
    print("Walk-forward (окна 24 мес):")
    win = 24
    pos_sh = 0
    tot = 0
    for s in range(0, len(port) - win + 1, win):
        seg = port[s : s + win]
        m = sum(seg) / len(seg)
        sd = math.sqrt(sum((x - m) ** 2 for x in seg) / (len(seg) - 1))
        sh = m / sd * math.sqrt(12) if sd > 0 else 0.0
        tot += 1
        if sh > 0:
            pos_sh += 1
        print(f"  окно {s // win}: Sharpe={sh:+4.2f}")
    if tot:
        print(f"Окон Sharpe>0: {pos_sh}/{tot} ({pos_sh / tot * 100:.0f}%)")
    print("\nГейт: OOS PF>1.3 И Sharpe>0.8 И ≥30. Базовый актив ≠ перп BingX.")


if __name__ == "__main__":
    main()

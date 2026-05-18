"""Трейлинг-стоп как выход: меняет ли он вердикт (план 22).

Тезис (честно): трейлинг — механика ВЫХОДА, не вход. На входе без
edge перераспределяет ту же кривую, край из ничего не создаёт; на
вилистой крипте часто пилит. Проверяем ЭМПИРИЧЕСКИ: берём входы
trend_ema (LONG и SHORT) по 13 монетам, заменяем фикс-выход на
ATR-трейлинг, идём по реальному пути свечей, портфельно, гейт.

Параметры не подгоняются: trail = 2·ATR(14) (типовое), жёсткий
изначальный стоп = исходный стоп сделки. Сравнение с baseline.
"""

from __future__ import annotations

import glob
import json
import math
import os
import subprocess
import sys
from decimal import Decimal

_COINS = [
    "BTC-USDT", "ETH-USDT", "SOL-USDT", "BNB-USDT", "XRP-USDT",
    "DOGE-USDT", "ADA-USDT", "AVAX-USDT", "LINK-USDT", "LTC-USDT",
    "TRX-USDT", "DOT-USDT", "SUI-USDT",
]  # fmt: skip
_OPS = "ops"
_ATR_N = 14
_TRAIL_K = 2.0  # trail = K·ATR (типовое, не подгон)
_COST = 0.0020  # консерв. round-trip: taker 0.10% + проскальзывание альтов


def _candles(sym: str) -> list[tuple[int, float, float, float]]:
    """[(open_ms, high, low, close)] ASC."""
    p = f"data/candles/{sym.lower()}-4h.jsonl"
    out: list[tuple[int, float, float, float]] = []
    if not os.path.exists(p):
        return out
    with open(p) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            out.append(
                (
                    int(d.get("open_time_ms") or d.get("openTime") or d["time"]),
                    float(d["high"]),
                    float(d["low"]),
                    float(d["close"]),
                )
            )
    out.sort(key=lambda r: r[0])
    return out


def _atr(c: list[tuple[int, float, float, float]], i: int) -> float:
    if i < _ATR_N:
        return 0.0
    s = 0.0
    for j in range(i - _ATR_N + 1, i + 1):
        h, low, pc = c[j][1], c[j][2], c[j - 1][3]
        s += max(h - low, abs(h - pc), abs(low - pc))
    return s / _ATR_N


def _trailing_exit_return(
    c: list[tuple[int, float, float, float]],
    entry_idx: int,
    side: str,
    entry: float,
    hard_stop: float,
) -> tuple[float, int]:
    """Идём вперёд по свечам: жёсткий стоп + ATR-трейлинг от пика.

    Возврат: (доходность, число удержанных баров)."""
    long = side == "BUY"
    atr0 = _atr(c, entry_idx) or entry * 0.01
    trail = _TRAIL_K * atr0
    peak = entry
    stop = hard_stop
    for k in range(entry_idx + 1, len(c)):
        hi, lo = c[k][1], c[k][2]
        held = k - entry_idx
        if long:
            if lo <= stop:
                return stop / entry - 1.0, held
            if hi > peak:
                peak = hi
                stop = max(stop, peak - trail)
        else:
            if hi >= stop:
                return 1.0 - stop / entry, held
            if lo < peak:
                peak = lo
                stop = min(stop, peak + trail)
    last = c[-1][3]
    ret = (last / entry - 1.0) if long else (1.0 - last / entry)
    return ret, len(c) - 1 - entry_idx


def _stats(rows: list[tuple[float, int]], tag: str) -> str:
    """rows = [(ret, bars_held)]. Честные метрики, без мисленейминга."""
    if len(rows) < 4:
        return f"{tag}: n={len(rows)}"
    rets = [r for r, _ in rows]
    n = len(rets)
    m = sum(rets) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in rets) / (n - 1))
    t = m / (sd / math.sqrt(n)) if sd > 0 else 0.0  # значимость
    p = math.erfc(abs(t) / math.sqrt(2))
    # Годовой Sharpe: per-trade нормируем на среднюю длительность.
    # 4h-бары: баров в год = 365*24/4 = 2190.
    avg_bars = sum(b for _, b in rows) / n
    trades_per_year = 2190.0 / avg_bars if avg_bars > 0 else 0.0
    ann_sharpe = m / sd * math.sqrt(trades_per_year) if sd > 0 else 0.0
    w = sum(r for r in rets if r > 0)
    loss = -sum(r for r in rets if r < 0)
    pf = float("inf") if loss == 0 else w / loss
    pf_s = "inf" if pf == float("inf") else f"{pf:.2f}"
    gate = "✓" if (pf > 1.3 and ann_sharpe > 0.8 and n >= 30) else "✗"
    return (
        f"{tag}: n={n:3d} PF={pf_s:>4s} annSharpe={ann_sharpe:+5.2f} "
        f"t={t:+4.2f} p={p:.3f} avgBars={avg_bars:5.0f} {gate}"
    )


def main() -> None:
    base_is: list[tuple[float, int]] = []
    base_oos: list[tuple[float, int]] = []
    tr_is: list[tuple[float, int]] = []
    tr_oos: list[tuple[float, int]] = []
    tr_timed: list[tuple[int, float]] = []  # (entry_ms, net ret) для WF
    _BAR_MS = 4 * 3600 * 1000
    for sym in _COINS:
        candle = f"data/candles/{sym.lower()}-4h.jsonl"
        if not os.path.exists(candle):
            continue
        t0 = max(
            (os.path.getmtime(f) for f in glob.glob(f"{_OPS}/backtest-*.json")),
            default=0.0,
        )
        subprocess.run(
            [sys.executable, "-m", "scripts.run_backtest", "--strategy",
             "trend_ema_4h", "--symbol", sym, "--candles", candle,
             "--split-fraction", "0.5"],
            check=True, capture_output=True,
        )  # fmt: skip
        c = _candles(sym)
        idx = {row[0]: i for i, row in enumerate(c)}
        for tag in ("is", "oos"):
            fs = [f for f in glob.glob(f"{_OPS}/backtest-{tag}-*.json") if os.path.getmtime(f) > t0]
            if not fs:
                continue
            with open(max(fs, key=os.path.getmtime)) as fh:
                trades = json.load(fh)["trades"]
            for tr in trades:
                e = tr["entry"]
                ems = int(e["timestamp_ms"])
                if ems not in idx:
                    continue
                ei = idx[ems]
                side = e["side"]
                entry = float(e["price"])
                hard = float(tr["exits"][0]["price"]) if tr["exits"] else entry
                # baseline = реализованный pnl_pct из движка + длит. в барах
                base = float(Decimal(str(tr["pnl_pct"]))) / 100.0
                base_bars = max(1, int(tr.get("duration_ms", 0)) // _BAR_MS)
                if entry > 0:
                    trr, trbars = _trailing_exit_return(c, ei, side, entry, hard)
                else:
                    trr, trbars = 0.0, 1
                trr_net = trr - _COST  # издержки round-trip
                tr_timed.append((ems, trr_net))
                if tag == "is":
                    base_is.append((base, base_bars))
                    tr_is.append((trr_net, trbars))
                else:
                    base_oos.append((base, base_bars))
                    tr_oos.append((trr_net, trbars))
    print("Трейлинг-стоп (2·ATR) на входах trend_ema, 13 монет, портфельно:")
    print("-" * 70)
    print(f"BASELINE  {_stats(base_is, 'IS ')}")
    print(f"BASELINE  {_stats(base_oos, 'OOS')}")
    print(f"TRAILING  {_stats(tr_is, 'IS ')} (с издержками {_COST:.2%})")
    print(f"TRAILING  {_stats(tr_oos, 'OOS')} (с издержками {_COST:.2%})")
    # Walk-forward: 5 равных по времени окон по entry_ms.
    print("-" * 70)
    print("Walk-forward TRAILING (5 окон по времени, net издержек):")
    tr_timed.sort(key=lambda r: r[0])
    if tr_timed:
        t0, t1 = tr_timed[0][0], tr_timed[-1][0]
        span = max(1, t1 - t0)
        wins = 0
        tot = 0
        for wnd in range(5):
            lo_ms = t0 + span * wnd // 5
            hi_ms = t0 + span * (wnd + 1) // 5
            seg = [r for ms, r in tr_timed if lo_ms <= ms < hi_ms]
            if len(seg) < 4:
                print(f"  окно {wnd}: n={len(seg)} (мало)")
                continue
            mm = sum(seg) / len(seg)
            ss = math.sqrt(sum((x - mm) ** 2 for x in seg) / (len(seg) - 1))
            tt = mm / (ss / math.sqrt(len(seg))) if ss > 0 else 0.0
            pos = sum(1 for x in seg if x > 0)
            tot += 1
            if mm > 0:
                wins += 1
            print(
                f"  окно {wnd}: n={len(seg):3d} mean={mm * 100:+.3f}% "
                f"t={tt:+4.2f} win={pos}/{len(seg)}"
            )
        if tot:
            print(f"Окон mean>0: {wins}/{tot}")
    print("\nГейт: OOS PF>1.3 И annSharpe>0.8 И ≥30 + WF-устойчивость.")


if __name__ == "__main__":
    main()

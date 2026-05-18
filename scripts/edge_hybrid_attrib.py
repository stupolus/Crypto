"""Атрибуция edge по веткам edge_hybrid (план 33.10).

Прогоняет КАЖДУЮ ветку (A/B/C) изолированно на 6 мажорах,
тот же cost-sweep + недельная агрегация, что в валидаторе.
Цель: оставить только компонент с честным положительным OOS-edge
(дисциплина «отбрасываем доказанно мёртвое», НЕ подгонка).
ТФ из argv (деф. 30m — самые глубокие данные).
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

from core.backtest import BacktestEngine
from core.backtest import get_default_config as bt_cfg
from core.risk import RiskEngine
from scripts.run_backtest import load_candles
from strategies.edge_hybrid import EdgeHybridStrategy, get_default_config

_COINS = ["BTC-USDT", "ETH-USDT", "SOL-USDT", "DOGE-USDT", "XRP-USDT", "BNB-USDT"]
_COSTS = [0.0010, 0.0015, 0.0020]
_TF = sys.argv[1] if len(sys.argv) > 1 else "30m"
# argv[2]: MARKET (taker) | LIMIT (maker, как фонды). Деф. MARKET.
_OT = sys.argv[2] if len(sys.argv) > 2 else "MARKET"


def _weekly(tr: list[tuple[int, float]]) -> list[float]:
    import datetime

    by: dict[tuple[int, int], list[float]] = {}
    for ms, r in tr:
        d = datetime.datetime.fromtimestamp(ms / 1000, datetime.UTC).isocalendar()
        by.setdefault((d[0], d[1]), []).append(r)
    return [sum(v) / len(v) for _, v in sorted(by.items())]


def _stat(series: list[float]) -> str:
    if len(series) < 8:
        return f"нед={len(series)} (<8 нет статбазы)"
    n = len(series)
    m = sum(series) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in series) / (n - 1))
    sh = m / sd * math.sqrt(52) if sd > 0 else 0.0
    t = m / (sd / math.sqrt(n)) if sd > 0 else 0.0
    pos = sum(x for x in series if x > 0)
    neg = -sum(x for x in series if x < 0)
    pf = float("inf") if neg == 0 else pos / neg
    return f"нед={n:3d} PF={pf:4.2f} Sh={sh:+6.2f} t={t:+6.2f}"


def _run_leg(tag: str, ea: bool, eb: bool, ec: bool) -> None:
    base = get_default_config()
    raw: list[tuple[int, float]] = []
    twin = tloss = 0
    gw = gl = 0.0
    for sym in _COINS:
        cf = Path(f"data/candles/{sym.lower()}-{_TF}.jsonl")
        if not cf.exists():
            continue
        cfg = base.model_copy(
            update={
                "symbol": sym,
                "enable_a": ea,
                "enable_b": eb,
                "enable_c": ec,
                "entry_order_type": _OT,
            }
        )
        cands = load_candles(cf)
        res = BacktestEngine(bt_cfg()).run(
            EdgeHybridStrategy(config=cfg, risk_engine=RiskEngine()), cands
        )
        for tr in res.trades:
            ems = int(tr.entry.timestamp_ms)
            pnl_frac = float(tr.pnl) / float(bt_cfg().initial_equity_decimal)
            raw.append((ems, pnl_frac))
            p = float(tr.pnl)
            if p > 0:
                twin += 1
                gw += p
            elif p < 0:
                tloss += 1
                gl += p
    if not raw:
        print(f"  {tag}: нет сделок")
        return
    raw.sort()
    split = raw[len(raw) // 2][0]
    n = twin + tloss
    wr = twin / n * 100 if n else 0.0
    pf_t = gw / -gl if gl else float("inf")
    print(f"  {tag}: сделок={n} winrate={wr:4.1f}% trade-PF={pf_t:4.2f} итог={(gw + gl):+.0f}")
    for c in _COSTS:
        oos = [(ms, r - c) for ms, r in raw if ms >= split]
        print(f"    cost {c:.2%} OOS n={len(oos):4d} {_stat(_weekly(oos))}")


def main() -> None:
    print(f"edge_hybrid атрибуция ({_TF}, вход={_OT}, план 33.11)")
    print("Гейт честный: положительный OOS-edge ≥8 корзин + cost-sweep")
    print("=" * 64)
    _run_leg("ТОЛЬКО A (mean-rev)", True, False, False)
    _run_leg("ТОЛЬКО B (sweep)   ", False, True, False)
    _run_leg("ТОЛЬКО C (breakout)", False, False, True)
    print("=" * 64)
    print("Если все ветки PF<1/Sh<0 → edge нет, вердикт окончателен.")
    print("Если ветка честно положительна OOS+cost — строим стратегию")
    print("ТОЛЬКО из неё (не подгонка, а отбрасывание мёртвого).")


if __name__ == "__main__":
    main()

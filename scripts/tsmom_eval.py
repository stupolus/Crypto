"""TSMOM (Moskowitz/Ooi/Pedersen 2012) на золоте/нефти/индексах.

Канон из открытых источников для commodity/index futures:
сигнал = знак 12-мес доходности базового актива → лонг/шорт на
следующий месяц. Тест на БАЗОВОМ активе (десятилетия Yahoo),
не на тонком перпе BingX (план 26, структурная стена).

Запуск: .venv/bin/python -m scripts.tsmom_eval

Оффлайн-аналитика. Гейт: PF>1.3 И Sharpe>0.8 И ≥30.
"""

from __future__ import annotations

import math

from core.signals.external_signal import _PERP_TO_UNDERLYING
from parsers.macro.seasonality import _fetch_monthly_closes

# Единый источник истины — карта перп→базовый из external_signal.
# Здесь: уникальные базовые активы (дедуп: AAPL/NVDA/META маппятся
# из нескольких перпов). Покрывает весь RWA/stock/index/FX-юниверс
# BingX, у которого есть глубокий внешний прокси.
_ASSETS: dict[str, str] = {u: u for u in sorted(set(_PERP_TO_UNDERLYING.values()))}
_LOOKBACK = 12  # мес, как в статье


def _tsmom_returns(closes: list[float]) -> list[float]:
    """Доходности стратегии 12-1: s·r(t+1), s=sign(12-мес ret)."""
    out: list[float] = []
    for t in range(_LOOKBACK, len(closes) - 1):
        if closes[t - _LOOKBACK] <= 0 or closes[t] <= 0:
            continue
        sig = 1.0 if closes[t] / closes[t - _LOOKBACK] - 1.0 > 0 else -1.0
        nxt = closes[t + 1] / closes[t] - 1.0
        out.append(sig * nxt)
    return out


def _metrics(rets: list[float]) -> str:
    if not rets:
        return "n=0"
    wins = sum(r for r in rets if r > 0)
    losses = -sum(r for r in rets if r < 0)
    pf = float("inf") if losses == 0 else wins / losses
    mean = sum(rets) / len(rets)
    var = sum((x - mean) ** 2 for x in rets) / len(rets) if len(rets) > 1 else 0.0
    std = math.sqrt(var)
    sharpe = mean / std * math.sqrt(12) if std > 0 else 0.0  # помесячно→год
    eq = 1.0
    peak = 1.0
    mdd = 0.0
    for r in rets:
        eq *= 1 + r
        peak = max(peak, eq)
        mdd = max(mdd, (peak - eq) / peak)
    wr = sum(1 for r in rets if r > 0) / len(rets) * 100
    pf_s = "inf" if pf == float("inf") else f"{pf:.2f}"
    gate = "✓" if (pf > 1.3 and sharpe > 0.8 and len(rets) >= 30) else "✗"
    return (
        f"n={len(rets):3d} PF={pf_s:>4s} wr={wr:3.0f}% "
        f"Sharpe={sharpe:+4.2f} maxDD={mdd * 100:4.1f}% ret={(eq - 1) * 100:+7.1f}% {gate}"
    )


def main() -> None:
    print("TSMOM 12-1 (Moskowitz et al. 2012) на базовых активах:")
    print("-" * 78)
    port_is: list[float] = []
    port_oos: list[float] = []
    for name, sym in _ASSETS.items():
        series = _fetch_monthly_closes(sym, years=20)
        closes = [c for _, c in series]
        if len(closes) < _LOOKBACK + 4:
            print(f"{name:8s} | Yahoo недоступен/мало данных ({len(closes)})")
            continue
        rets = _tsmom_returns(closes)
        half = len(rets) // 2
        is_r, oos_r = rets[:half], rets[half:]
        port_is.extend(is_r)
        port_oos.extend(oos_r)
        print(f"{name:8s} IS  | {_metrics(is_r)}")
        print(f"{name:8s} OOS | {_metrics(oos_r)}")
    print("-" * 78)
    print(f"ПОРТФЕЛЬ IS  | {_metrics(port_is)}")
    print(f"ПОРТФЕЛЬ OOS | {_metrics(port_oos)}")
    print("Гейт: PF>1.3 И Sharpe>0.8 И ≥30 (✓/✗). Базовый актив ≠ перп BingX.")


if __name__ == "__main__":
    main()

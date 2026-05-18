"""Funding-rate edge: экстремальный funding → контр-сигнал (план 22).

Структурный крипто-специфичный край (НЕ ценовой паттерн):
перегруженная сторона платит funding; экстремальный положительный
funding = перекос в лонги → forward-просадка, и наоборот.
Документировано (funding как сигнал позиционирования).

Данные: data/funding/<sym>.jsonl (fundingRate, fundingTime,
markPrice — каждые 8ч). Forward-доходность считаем по markPrice
из того же файла. Одна предзаданная контр-стратегия, без подгона
порога под PnL. Гейт: PF>1.3 И Sharpe>0.8 И ≥30 + t-стат.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

_FUNDING_DIR = Path("data/funding")
_SYMS = ["btc-usdt", "eth-usdt", "sol-usdt"]
_HORIZON = 3  # периодов funding (≈1 сутки) держим
# Экстремум структурно = верхний квартиль |funding| самой монеты
# (предзадано, НЕ подгон под PnL). На мажорах фикс-порог 0.05%
# почти не срабатывает — funding ручной (рынок эффективен).
_EXTREME_Q = 0.75


def _load(sym: str) -> list[tuple[int, float, float]]:
    p = _FUNDING_DIR / f"{sym}.jsonl"
    if not p.exists():
        return []
    rows: list[tuple[int, float, float]] = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        try:
            rows.append(
                (
                    int(d["fundingTime"]),
                    float(d["fundingRate"]),
                    float(d["markPrice"]),
                )
            )
        except (KeyError, ValueError, TypeError):
            continue
    rows.sort(key=lambda r: r[0])
    return rows


def _strategy_returns(rows: list[tuple[int, float, float]]) -> list[float]:
    """Контр-сигнал на экстремуме |funding| (верхний квартиль монеты).

    Порог |funding| = квартиль 0.75 по всей истории актива (структурное
    определение «перекос», не оптимизация по доходности)."""
    out: list[float] = []
    _MIN_HIST = 60  # минимум истории для оценки квартиля
    for i in range(len(rows) - _HORIZON):
        if i < _MIN_HIST:
            continue
        # Порог = квартиль |funding| ТОЛЬКО по прошлому (анти-look-ahead).
        past = sorted(abs(fr) for _, fr, _ in rows[:i])
        thr = past[int(len(past) * _EXTREME_Q)]
        fr = rows[i][1]
        if abs(fr) < thr:
            continue
        sig = -1.0 if fr > 0 else 1.0  # контр перегруженной стороне
        p0 = rows[i][2]
        p1 = rows[i + _HORIZON][2]
        if p0 <= 0:
            continue
        out.append(sig * (p1 / p0 - 1.0))
    return out


def _metrics(rets: list[float], tag: str) -> str:
    if len(rets) < 4:
        return f"{tag}: n={len(rets)} (мало)"
    n = len(rets)
    mean = sum(rets) / n
    var = sum((x - mean) ** 2 for x in rets) / (n - 1)
    std = math.sqrt(var)
    # ≈3 сделки/сутки → годовых периодов ≈ 365*8h/24h... берём n как есть,
    # annualize консервативно через √(периодов в год ≈ 365).
    sharpe = mean / std * math.sqrt(365) if std > 0 else 0.0
    t = mean / (std / math.sqrt(n)) if std > 0 else 0.0
    p = math.erfc(abs(t) / math.sqrt(2))
    wins = sum(r for r in rets if r > 0)
    losses = -sum(r for r in rets if r < 0)
    pf = float("inf") if losses == 0 else wins / losses
    eq = 1.0
    for r in rets:
        eq *= 1 + r
    pf_s = "inf" if pf == float("inf") else f"{pf:.2f}"
    gate = "✓" if (pf > 1.3 and sharpe > 0.8 and n >= 30) else "✗"
    return (
        f"{tag}: n={n:3d} PF={pf_s:>4s} Sharpe={sharpe:+5.2f} "
        f"t={t:+4.2f} p={p:.3f} ret={(eq - 1) * 100:+6.1f}% {gate}"
    )


def main() -> None:
    print("Funding-edge (контр-экстремум, |f|>0.05%/8ч, держим ~1 сут):")
    print("-" * 74)
    all_is: list[float] = []
    all_oos: list[float] = []
    for sym in _SYMS:
        rows = _load(sym)
        if len(rows) < 40:
            print(f"{sym}: данных мало ({len(rows)})")
            continue
        rets = _strategy_returns(rows)
        half = len(rets) // 2
        all_is.extend(rets[:half])
        all_oos.extend(rets[half:])
        print(f"{sym:9s} {_metrics(rets[:half], 'IS ')}")
        print(f"{sym:9s} {_metrics(rets[half:], 'OOS')}")
    print("-" * 74)
    print(f"ПОРТФЕЛЬ {_metrics(all_is, 'IS ')}")
    print(f"ПОРТФЕЛЬ {_metrics(all_oos, 'OOS')}")
    print("\nГейт: OOS PF>1.3 И Sharpe>0.8 И ≥30. ~1 год данных (3 монеты).")


if __name__ == "__main__":
    main()

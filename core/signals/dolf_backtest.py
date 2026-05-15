"""Изолированный бэктест-харнес DOLF-детекторов (план 23 фаза 23.2).

Для КАЖДОГО детектора отдельно: идём по свечам, на срабатывании
фиксируем форвардную доходность на горизонте N баров в сторону
сетапа. Считаем n / win-rate / PF / Sharpe / avg. Это проверка
качества сигнала (предсказывает ли сетап движение), без подбора
параметров — фиксированный горизонт, пороги из статьи.

Критерий приёмки (план 20/23): PF>1.3 И Sharpe>0.8 И ≥30 сделок
OOS. Только прошедшие изолированно → кандидаты в композит.

Чистая функция (тестируется синтетикой). Реальный прогон —
после апгрейда тарифа Coinglass (провайдеры наполнены).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal

from core.signals.composite import (
    DeltaProvider,
    FundingProvider,
    LiquidationProvider,
    OpenInterestProvider,
)
from core.signals.dolf_setups import (
    DolfContext,
    DolfThresholds,
    SetupResult,
    SetupSide,
)

Detector = Callable[[DolfContext], SetupResult]


@dataclass(frozen=True)
class Candle:
    open_time_ms: int
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


@dataclass(frozen=True)
class DetectorStats:
    name: str
    trades: int
    win_rate: float
    profit_factor: float
    sharpe: float
    avg_return_pct: float

    @property
    def passes(self) -> bool:
        """Критерий приёмки плана 20/23."""
        return self.profit_factor > 1.3 and self.sharpe > 0.8 and self.trades >= 30


def _stats(name: str, rets: list[float]) -> DetectorStats:
    if not rets:
        return DetectorStats(name, 0, 0.0, 0.0, 0.0, 0.0)
    wins = sum(r for r in rets if r > 0)
    losses = -sum(r for r in rets if r < 0)
    pf = float("inf") if losses == 0 else wins / losses
    mean = sum(rets) / len(rets)
    var = sum((x - mean) ** 2 for x in rets) / len(rets) if len(rets) > 1 else 0.0
    std = math.sqrt(var)
    sharpe = mean / std * math.sqrt(len(rets)) if std > 0 else 0.0
    wr = sum(1 for r in rets if r > 0) / len(rets) * 100.0
    return DetectorStats(name, len(rets), wr, pf, sharpe, mean * 100.0)


def evaluate_detector(
    detector: Detector,
    candles: Sequence[Candle],
    *,
    liq: LiquidationProvider,
    oi: OpenInterestProvider,
    delta: DeltaProvider,
    funding: FundingProvider,
    symbol: str,
    horizon_bars: int = 6,
    min_history: int = 30,
    thresholds: DolfThresholds | None = None,
) -> DetectorStats:
    """Форвардная доходность сетапа на горизонте horizon_bars.

    Анти-look-ahead: контекст строится из свечей [0..i], сделка
    оценивается по close[i] → close[i+horizon]. Один вход на бар.
    """
    th = thresholds or DolfThresholds()
    rets: list[float] = []
    last = len(candles) - horizon_bars
    for i in range(min_history, last):
        ctx = DolfContext(
            symbol=symbol,
            timestamp_ms=candles[i].open_time_ms,
            closes=[c.close for c in candles[: i + 1]],
            highs=[c.high for c in candles[: i + 1]],
            lows=[c.low for c in candles[: i + 1]],
            volumes=[c.volume for c in candles[: i + 1]],
            liq=liq,
            oi=oi,
            delta=delta,
            funding=funding,
            thresholds=th,
        )
        res = detector(ctx)
        if not res.triggered or res.side is None:
            continue
        entry = candles[i].close
        exit_ = candles[i + horizon_bars].close
        if entry <= 0:
            continue
        move = float(exit_ / entry - 1)
        rets.append(move if res.side is SetupSide.LONG else -move)
    return _stats(res_name(detector), rets)


def res_name(detector: Detector) -> str:
    """Имя сетапа из «холостого» вызова (детектор возвращает .name всегда)."""
    return getattr(detector, "__name__", "detector")

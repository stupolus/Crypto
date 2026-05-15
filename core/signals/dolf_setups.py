"""Изолированные DOLF-детекторы (план 23 фаза 23.1).

Каждый детектор — чистая функция над уже готовыми провайдерами
(Liquidation/OpenInterest/Delta/Funding). Возвращает SetupResult.
Назначение: гонять каждый сетап ИЗОЛИРОВАННО на 2-летней истории
после апгрейда тарифа Coinglass (план 23 матрица бэктеста). Только
прошедшие критерий (PF>1.3, Sharpe>0.8, ≥30 OOS) → в композит.

Пороги — из статьи DOLF Щукина (plans/23), вынесены в
``DolfThresholds`` (не хардкод, не подгонка). ⚠️ funding-порог
зависит от интервала источника (план 23 причина №9) — параметр.

Этот модуль НЕ торгует и НЕ триггерит входы сам по себе — он
поставляет булевы сигналы для изолированного бэктеста (принцип №1).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from core.signals.composite import (
    DeltaProvider,
    FundingProvider,
    LiquidationProvider,
    OpenInterestProvider,
)


class SetupSide(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"


@dataclass(frozen=True)
class SetupResult:
    triggered: bool
    name: str
    side: SetupSide | None = None
    reason: str = ""


@dataclass(frozen=True)
class DolfThresholds:
    """Пороги из статьи DOLF (plans/23-dolf-формализация.md).

    Источник — teletype Щукина 2024-10-13, НЕ перебор по бэктесту.
    """

    liq_spike_mult: float = 3.0  # ликвидация ≥ Nx медианы базлайна
    liq_baseline_n: int = 30
    funding_long_max: Decimal = Decimal("-0.01")  # «золотой» сетап ≤ −1%
    oi_lookback: int = 6
    oi_div_min_pct: float = 3.0  # значимое расхождение цена/OI
    price_lookback: int = 20  # окно локального экстремума


@dataclass
class DolfContext:
    """Контекст на момент закрытия свечи. Цены — ASC, последняя текущая."""

    symbol: str
    timestamp_ms: int
    closes: list[Decimal]
    highs: list[Decimal]
    lows: list[Decimal]
    liq: LiquidationProvider
    oi: OpenInterestProvider
    delta: DeltaProvider
    funding: FundingProvider
    thresholds: DolfThresholds = field(default_factory=DolfThresholds)


def _median(xs: list[Decimal]) -> Decimal:
    if not xs:
        return Decimal("0")
    s = sorted(xs)
    m = len(s) // 2
    return s[m] if len(s) % 2 else (s[m - 1] + s[m]) / 2


def _liq_spike(
    ctx: DolfContext,
) -> tuple[bool, Decimal, Decimal]:
    """(есть_всплеск, long_usd, short_usd) текущего бакета vs базлайн."""
    t = ctx.thresholds
    bucket = ctx.liq.get_bucket(ctx.symbol, ctx.timestamp_ms)
    if bucket is None:
        return False, Decimal("0"), Decimal("0")
    base = ctx.liq.get_baseline(ctx.symbol, ctx.timestamp_ms, t.liq_baseline_n)
    if len(base) < max(5, t.liq_baseline_n // 2):
        return False, bucket.long_volume, bucket.short_volume
    med_total = _median([b.total for b in base])
    if med_total <= 0:
        return False, bucket.long_volume, bucket.short_volume
    spike = bucket.total >= med_total * Decimal(str(t.liq_spike_mult))
    return spike, bucket.long_volume, bucket.short_volume


def detect_l6_long_from_long_liq(ctx: DolfContext) -> SetupResult:
    """L6: крупная LONG-ликвидация + снятие локального минимума → LONG."""
    t = ctx.thresholds
    spike, long_usd, short_usd = _liq_spike(ctx)
    name = "L6_long_from_long_liq"
    if not spike or long_usd <= short_usd:
        return SetupResult(False, name)
    if len(ctx.lows) < t.price_lookback + 1:
        return SetupResult(False, name)
    prior_low = min(ctx.lows[-t.price_lookback - 1 : -1])
    if ctx.lows[-1] < prior_low:  # снятие минимума на ликвидации
        return SetupResult(
            True, name, SetupSide.LONG, "крупная long-ликвидация + новый локальный low"
        )
    return SetupResult(False, name)


def detect_s5_short_from_short_liq(ctx: DolfContext) -> SetupResult:
    """S5: крупная SHORT-ликвидация у локального хая + OI↓ → SHORT."""
    t = ctx.thresholds
    spike, long_usd, short_usd = _liq_spike(ctx)
    name = "S5_short_from_short_liq"
    if not spike or short_usd <= long_usd:
        return SetupResult(False, name)
    if len(ctx.highs) < t.price_lookback + 1:
        return SetupResult(False, name)
    prior_high = max(ctx.highs[-t.price_lookback - 1 : -1])
    oi = ctx.oi.get_series(ctx.symbol, ctx.timestamp_ms, t.oi_lookback)
    oi_falling = len(oi) >= 2 and oi[-1] < oi[0]
    if ctx.highs[-1] > prior_high and oi_falling:
        return SetupResult(
            True,
            name,
            SetupSide.SHORT,
            "крупная short-ликвидация + новый хай + падающий OI",
        )
    return SetupResult(False, name)


def detect_l2_golden_funding(ctx: DolfContext) -> SetupResult:
    """L2 «Золотой сетап»: цена↑ + OI↑ + funding ≤ порога → LONG."""
    t = ctx.thresholds
    name = "L2_golden_funding"
    if len(ctx.closes) < 2:
        return SetupResult(False, name)
    fr = ctx.funding.get_funding_rate(ctx.symbol, ctx.timestamp_ms)
    if fr is None or fr > t.funding_long_max:
        return SetupResult(False, name)
    oi = ctx.oi.get_series(ctx.symbol, ctx.timestamp_ms, t.oi_lookback)
    oi_rising = len(oi) >= 2 and oi[-1] > oi[0]
    price_rising = ctx.closes[-1] > ctx.closes[0]
    if oi_rising and price_rising:
        return SetupResult(
            True, name, SetupSide.LONG, f"funding {fr} ≤ {t.funding_long_max}, OI↑, price↑"
        )
    return SetupResult(False, name)


def detect_s3_nedogora(ctx: DolfContext) -> SetupResult:
    """S3 «Недогора»: новый ценовой хай, но OI < прошлого пика → SHORT."""
    t = ctx.thresholds
    name = "S3_nedogora"
    if len(ctx.closes) < t.oi_lookback + 1:
        return SetupResult(False, name)
    oi = ctx.oi.get_series(ctx.symbol, ctx.timestamp_ms, t.oi_lookback + 1)
    if len(oi) < t.oi_lookback + 1:
        return SetupResult(False, name)
    price_new_high = ctx.closes[-1] >= max(ctx.closes[-t.oi_lookback - 1 : -1])
    oi_div = oi[-1] < max(oi[:-1]) * (1 - Decimal(str(t.oi_div_min_pct)) / 100)
    if price_new_high and oi_div:
        return SetupResult(True, name, SetupSide.SHORT, "перехай цены при OI ниже прошлого пика")
    return SetupResult(False, name)


# Реестр для изолированного бэктеста (план 23 фаза 23.2+).
ALL_DETECTORS = [
    detect_l6_long_from_long_liq,
    detect_s5_short_from_short_liq,
    detect_l2_golden_funding,
    detect_s3_nedogora,
]

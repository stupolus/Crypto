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
    volumes: list[Decimal]
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


def _pct(a: Decimal, b: Decimal) -> Decimal:
    """Изменение b относительно a в %. 0 при a<=0."""
    if a <= 0:
        return Decimal("0")
    return (b / a - 1) * 100


def detect_l1_trend_start(ctx: DolfContext) -> SetupResult:
    """L1 «Начало тренда»: из низковолат. базы vol↑&OI↑&price↑,
    причём ΔOI% и Δvol% > Δprice% (рост обеспечен деньгами)."""
    t = ctx.thresholds
    name = "L1_trend_start"
    if len(ctx.closes) < t.oi_lookback + 1 or len(ctx.volumes) < t.oi_lookback + 1:
        return SetupResult(False, name)
    oi = ctx.oi.get_series(ctx.symbol, ctx.timestamp_ms, t.oi_lookback + 1)
    if len(oi) < 2:
        return SetupResult(False, name)
    d_price = _pct(ctx.closes[-t.oi_lookback - 1], ctx.closes[-1])
    d_oi = _pct(oi[0], oi[-1])
    d_vol = _pct(ctx.volumes[-t.oi_lookback - 1], ctx.volumes[-1])
    if d_price > 0 and d_oi > d_price and d_vol > d_price and d_oi > 0:
        return SetupResult(
            True,
            name,
            SetupSide.LONG,
            f"ΔOI {d_oi:.1f}% & Δvol {d_vol:.1f}% > Δprice {d_price:.1f}%",
        )
    return SetupResult(False, name)


def detect_l3_oi_drop_flat_price(ctx: DolfContext) -> SetupResult:
    """L3: OI резко вырос ранее, сейчас ↓ при флэте цены → LONG."""
    t = ctx.thresholds
    name = "L3_oi_drop_flat_price"
    oi = ctx.oi.get_series(ctx.symbol, ctx.timestamp_ms, t.oi_lookback * 2)
    if len(oi) < t.oi_lookback * 2 or len(ctx.closes) < t.oi_lookback:
        return SetupResult(False, name)
    half = len(oi) // 2
    oi_rose_before = _pct(oi[0], max(oi[:half])) > t.oi_div_min_pct
    oi_falling_now = oi[-1] < max(oi[half:])
    price_flat = abs(_pct(ctx.closes[-t.oi_lookback], ctx.closes[-1])) < Decimal(
        str(t.oi_div_min_pct)
    )
    if oi_rose_before and oi_falling_now and price_flat:
        return SetupResult(True, name, SetupSide.LONG, "OI вырос→падает, цена флэт")
    return SetupResult(False, name)


def detect_l4_trend_continuation(ctx: DolfContext) -> SetupResult:
    """L4: откат цены вниз при стабильном/растущем OI → LONG (докуп)."""
    t = ctx.thresholds
    name = "L4_trend_continuation"
    if len(ctx.closes) < t.oi_lookback + 1:
        return SetupResult(False, name)
    oi = ctx.oi.get_series(ctx.symbol, ctx.timestamp_ms, t.oi_lookback)
    if len(oi) < 2:
        return SetupResult(False, name)
    price_pullback = ctx.closes[-1] < ctx.closes[-t.oi_lookback - 1]
    oi_held = _pct(oi[0], oi[-1]) >= -Decimal(str(t.oi_div_min_pct))
    if price_pullback and oi_held:
        return SetupResult(True, name, SetupSide.LONG, "откат цены, OI держится")
    return SetupResult(False, name)


def detect_l5_shortodon(ctx: DolfContext) -> SetupResult:
    """L5 «Шортодон»: цена↓ но OI↑ & vol↑ (паника шортов) → LONG."""
    t = ctx.thresholds
    name = "L5_shortodon"
    if len(ctx.closes) < t.oi_lookback + 1 or len(ctx.volumes) < t.oi_lookback + 1:
        return SetupResult(False, name)
    oi = ctx.oi.get_series(ctx.symbol, ctx.timestamp_ms, t.oi_lookback)
    if len(oi) < 2:
        return SetupResult(False, name)
    price_down = ctx.closes[-1] < ctx.closes[-t.oi_lookback - 1]
    oi_up = oi[-1] > oi[0]
    vol_up = ctx.volumes[-1] > ctx.volumes[-t.oi_lookback - 1]
    if price_down and oi_up and vol_up:
        return SetupResult(True, name, SetupSide.LONG, "цена↓ при OI↑ и vol↑")
    return SetupResult(False, name)


def detect_s1_oi_drop_after_pump(ctx: DolfContext) -> SetupResult:
    """S1: сильный рост price+OI, затем OI начал падать → SHORT.
    ⚠️ план 23: чёткое подтверждение требует 15m (STANDARD-тариф)."""
    t = ctx.thresholds
    name = "S1_oi_drop_after_pump"
    oi = ctx.oi.get_series(ctx.symbol, ctx.timestamp_ms, t.oi_lookback * 2)
    if len(oi) < t.oi_lookback * 2 or len(ctx.closes) < t.oi_lookback * 2:
        return SetupResult(False, name)
    half = len(oi) // 2
    pumped = (
        _pct(oi[0], max(oi[:half])) > t.oi_div_min_pct
        and _pct(ctx.closes[0], max(ctx.closes[:half])) > t.oi_div_min_pct
    )
    oi_dropping = oi[-1] < max(oi[half:])
    if pumped and oi_dropping:
        return SetupResult(True, name, SetupSide.SHORT, "OI↓ после пампа price+OI")
    return SetupResult(False, name)


def detect_s2_price_oi_divergence(ctx: DolfContext) -> SetupResult:
    """S2: цена↑ недавно, но OI флэт/↓ (манипуляция) → SHORT."""
    t = ctx.thresholds
    name = "S2_price_oi_divergence"
    if len(ctx.closes) < t.oi_lookback + 1:
        return SetupResult(False, name)
    oi = ctx.oi.get_series(ctx.symbol, ctx.timestamp_ms, t.oi_lookback)
    if len(oi) < 2:
        return SetupResult(False, name)
    price_up = _pct(ctx.closes[-t.oi_lookback - 1], ctx.closes[-1]) > t.oi_div_min_pct
    oi_not_confirming = _pct(oi[0], oi[-1]) <= 0
    if price_up and oi_not_confirming:
        return SetupResult(True, name, SetupSide.SHORT, "цена↑ при OI флэт/↓")
    return SetupResult(False, name)


# Реестр для изолированного бэктеста (план 23 фаза 23.2+).
# S4 (FOMO-свечи) отложен — нужен внутрибарный 15m (STANDARD-тариф).
ALL_DETECTORS = [
    detect_l1_trend_start,
    detect_l2_golden_funding,
    detect_l3_oi_drop_flat_price,
    detect_l4_trend_continuation,
    detect_l5_shortodon,
    detect_l6_long_from_long_liq,
    detect_s1_oi_drop_after_pump,
    detect_s2_price_oi_divergence,
    detect_s3_nedogora,
    detect_s5_short_from_short_liq,
]

"""Pydantic-модели для Coinglass data — план #17 Layer 1."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class CoinglassOIPoint(BaseModel):
    """Open Interest snapshot для одного символа в моменте.

    Один из ключевых сигналов: резкий рост OI = вход новых денег
    (часто перед движением).
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    symbol: str = Field(min_length=1)
    timestamp_ms: int = Field(gt=0)
    open_interest_usd: Decimal = Field(ge=0)
    open_interest_change_24h_pct: Decimal | None = None


class CoinglassFundingPoint(BaseModel):
    """Funding rate snapshot.

    Экстремальные значения (>0.1%/8ч или <−0.05%/8ч) — сигнал
    для contrarian setups (см. бизнес/идеи.md «Funding extremes»).
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    symbol: str = Field(min_length=1)
    timestamp_ms: int = Field(gt=0)
    funding_rate_pct: Decimal = Field(description="Например 0.01 = 0.01%/interval")
    next_funding_time_ms: int | None = None
    interval_hours: int = Field(default=8, ge=1, le=24)


class CoinglassLiquidationBucket(BaseModel):
    """Один таймбакет агрегированных ликвидаций (history endpoint).

    ``/api/futures/liquidation/history`` отдаёт long/short объёмы
    ликвидаций за интервал. Используется liquidation_reversal как
    исторический LiquidationProvider (план 21 фаза 21.4).
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    timestamp_ms: int = Field(gt=0)
    long_liquidation_usd: Decimal = Field(ge=0)
    short_liquidation_usd: Decimal = Field(ge=0)


class CoinglassLiquidationCluster(BaseModel):
    """Один кластер ликвидаций на heatmap.

    ``side`` = "long" или "short" (что ликвидируется).
    ``volume_usd`` = совокупный объём stop'ов в этом ценовом уровне.
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    price_level: Decimal
    volume_usd: Decimal = Field(ge=0)
    side: str = Field(pattern="^(long|short)$")


class CoinglassLiquidationHeatmap(BaseModel):
    """Полная heatmap ликвидаций для символа.

    Использование: bot ищет large clusters над/под текущей ценой → ставит
    TP за кластером (магниты ликвидности) или SL подальше от кластера.
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    symbol: str = Field(min_length=1)
    timestamp_ms: int = Field(gt=0)
    current_price: Decimal = Field(gt=0)
    clusters_above: tuple[CoinglassLiquidationCluster, ...] = ()
    clusters_below: tuple[CoinglassLiquidationCluster, ...] = ()

    @property
    def largest_above(self) -> CoinglassLiquidationCluster | None:
        if not self.clusters_above:
            return None
        return max(self.clusters_above, key=lambda c: c.volume_usd)

    @property
    def largest_below(self) -> CoinglassLiquidationCluster | None:
        if not self.clusters_below:
            return None
        return max(self.clusters_below, key=lambda c: c.volume_usd)

"""Pydantic-модели Hyperliquid (план 22 фаза 22.C).

Hyperliquid — крупнейший on-chain перп-DEX (~52% RWA-рынка, стек
проекта). Публичный ``POST /info`` без ключа отдаёт по каждому
перпу: OI (в монетах), funding, mark/oracle цену, дневной объём.

Используется как источник OI/funding для composite-фильтров
(НЕ триггер — путь parse → статистика → edge, принцип №1).
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class HyperliquidAssetCtx(BaseModel):
    """Снимок состояния одного перпа Hyperliquid в моменте.

    ``open_interest`` — в единицах базовой монеты (как отдаёт API).
    ``open_interest_usd`` — производное (OI * mark_px), для сравнения
    с Coinglass/BingX в долларах.
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    coin: str = Field(min_length=1)
    timestamp_ms: int = Field(gt=0)
    mark_px: Decimal = Field(gt=0)
    oracle_px: Decimal = Field(gt=0)
    open_interest: Decimal = Field(ge=0)
    funding: Decimal = Field(description="Часовой funding, доля (0.0000125 = 0.00125%)")
    day_volume_usd: Decimal = Field(ge=0)

    @property
    def open_interest_usd(self) -> Decimal:
        return self.open_interest * self.mark_px

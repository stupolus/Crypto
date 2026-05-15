"""Coinglass API адаптер (план #17 Layer 1).

Coinglass даёт:
- Heatmap ликвидаций по символам и интервалам времени
- Open Interest / Funding Rate / Long-Short Ratio
- Liquidations volume (real-time + история)

Тарифы (2026):
- Standard: $29/мес — 15 req/min, базовые endpoints (для D3 тестов)
- Pro: $129/мес — 100 req/min, heatmap, breakdown по биржам (для live)

В первой имплементации делаем только модели + skeleton клиента.
Реальная имплементация с API ключом — после регистрации пользователя.
"""

from parsers.coinglass.client import CoinglassClient, CoinglassSettings
from parsers.coinglass.models import (
    CoinglassFundingPoint,
    CoinglassLiquidationBucket,
    CoinglassLiquidationHeatmap,
    CoinglassOIPoint,
)

__all__ = [
    "CoinglassClient",
    "CoinglassFundingPoint",
    "CoinglassLiquidationBucket",
    "CoinglassLiquidationHeatmap",
    "CoinglassOIPoint",
    "CoinglassSettings",
]

"""Bybit V5 адаптер — ТОЛЬКО публичная market-data.

Никаких trading-методов (no `place_order`, no `cancel_order`).
Этот пакет нельзя превратить в торговый бот случайно — даже подписи
запросов нет. План: трейдер/планы/02-скальп-вариант-параллельно-2026-05-27.md
"""

from adapters.bybit.models import BybitFundingRate, BybitKline, BybitOISample
from adapters.bybit.public import BybitPublicAPI
from adapters.bybit.settings import BybitSettings

__all__ = [
    "BybitFundingRate",
    "BybitKline",
    "BybitOISample",
    "BybitPublicAPI",
    "BybitSettings",
]

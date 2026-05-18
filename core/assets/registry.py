"""Asset class registry — поддержка multi-symbol (crypto / commodity / energy / stock).

Каждый symbol (BTC-USDT, XAU-USDT, CL-USDT, TSLA-USDT, ...) принадлежит
одному asset class'у. Класс определяет:
- session_window — когда торги открыты (для крипты 24/7)
- max_leverage — cap плеча (CLAUDE.md: ≤5x для крипты, обычно меньше для
  TradFi из-за overnight gaps)
- volatility_profile — для размера риска (low/normal/high)

Sessions выражены через ``SessionWindow`` (UTC time windows на день недели).
``is_session_open(symbol, now_utc)`` — главная функция для runner check.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time
from decimal import Decimal
from enum import StrEnum
from typing import Literal


class AssetClass(StrEnum):
    """Категория инструмента."""

    CRYPTO = "crypto"
    COMMODITY = "commodity"
    ENERGY = "energy"
    STOCK_PERP = "stock_perp"


VolatilityProfile = Literal["low", "normal", "high"]


@dataclass(frozen=True)
class SessionWindow:
    """Окно торгов в UTC.

    Дни недели: 0=Monday, 6=Sunday (стандарт ``datetime.weekday()``).

    Crypto: weekdays = (0..6), start = time(0,0), end = time(23,59,59)
        — фактически всегда открыты.

    Stocks (US): weekdays = (0..4), start = 13:30 UTC, end = 20:00 UTC
        — NY session 9:30-16:00 EST.

    Commodity (CME-like): weekdays = (6,0,1,2,3,4), start = 23:00 UTC Sun,
        end = 22:00 UTC Fri. Упрощённо в нашем MVP: торгуем 0..4 + Sun
        вечер.
    """

    weekdays: frozenset[int]
    start: time
    end: time

    @classmethod
    def always_open(cls) -> SessionWindow:
        return cls(
            weekdays=frozenset(range(7)),
            start=time(0, 0),
            end=time(23, 59, 59),
        )

    @classmethod
    def us_market_hours(cls) -> SessionWindow:
        """NYSE 9:30-16:00 EST = 13:30-20:00 UTC. Mon-Fri (0..4)."""
        return cls(
            weekdays=frozenset(range(5)),
            start=time(13, 30),
            end=time(20, 0),
        )

    @classmethod
    def commodity_extended(cls) -> SessionWindow:
        """CME commodity: Sun 23:00 - Fri 22:00 UTC. Упрощённо: Mon-Fri."""
        return cls(
            weekdays=frozenset(range(5)),
            start=time(0, 0),
            end=time(23, 59, 59),
        )

    def is_open(self, now_utc: datetime) -> bool:
        """Открыт ли рынок сейчас (now_utc должно быть в UTC)."""
        if now_utc.weekday() not in self.weekdays:
            return False
        t = now_utc.time()
        # Обработка случая когда window переходит через полночь (end < start)
        if self.end >= self.start:
            return self.start <= t <= self.end
        return t >= self.start or t <= self.end


@dataclass(frozen=True)
class AssetConfig:
    """Параметры одного asset class'а."""

    asset_class: AssetClass
    session: SessionWindow
    max_leverage: int  # cap по CLAUDE.md и asset-specific нюансам
    volatility_profile: VolatilityProfile
    min_notional_usdt: Decimal
    # Tickers (suffix без _USDT для документации). Symbol на BingX = "{base}-USDT"
    base_symbols: tuple[str, ...]


class UnknownAssetError(KeyError):
    """Символ не найден в registry."""


class AssetRegistry:
    """Lookup symbol → AssetConfig.

    Все BingX symbols имеют формат ``<BASE>-USDT``. Мы храним конфиг
    по base (BTC, ETH, XAU, CL, TSLA, ...) и резолвим из полного symbol.
    """

    def __init__(self, configs: dict[str, AssetConfig]):
        # Build symbol → config lookup
        self._by_symbol: dict[str, AssetConfig] = {}
        for cfg in configs.values():
            for base in cfg.base_symbols:
                full_symbol = f"{base}-USDT"
                self._by_symbol[full_symbol] = cfg

    def get(self, symbol: str) -> AssetConfig:
        try:
            return self._by_symbol[symbol]
        except KeyError as e:
            raise UnknownAssetError(
                f"Unknown symbol {symbol!r}. Known: {sorted(self._by_symbol)}"
            ) from e

    def is_open(self, symbol: str, now_utc: datetime | None = None) -> bool:
        cfg = self.get(symbol)
        return cfg.session.is_open(now_utc or datetime.now(UTC))

    def all_symbols(self) -> list[str]:
        return sorted(self._by_symbol)


def is_session_open(symbol: str, now_utc: datetime | None = None) -> bool:
    """Convenience wrapper над DEFAULT_REGISTRY."""
    return DEFAULT_REGISTRY.is_open(symbol, now_utc)


def _build_default_registry() -> AssetRegistry:
    """Дефолтные asset classes для нашего портфолио."""
    return AssetRegistry(
        {
            "crypto": AssetConfig(
                asset_class=AssetClass.CRYPTO,
                session=SessionWindow.always_open(),
                max_leverage=5,
                volatility_profile="high",
                min_notional_usdt=Decimal("5"),
                base_symbols=("BTC", "ETH", "SOL", "XRP", "DOGE", "BNB"),
            ),
            "commodity": AssetConfig(
                asset_class=AssetClass.COMMODITY,
                session=SessionWindow.commodity_extended(),
                max_leverage=3,
                volatility_profile="normal",
                min_notional_usdt=Decimal("10"),
                # BingX VST: реальные имена. XAUT (Tether Gold) для золота.
                # XAU/XAG/NCCOGOLD2USD оставлены для backwards-compat в коде.
                base_symbols=("XAUT", "XAU", "XAG", "NCCOGOLD2USD"),
            ),
            "energy": AssetConfig(
                asset_class=AssetClass.ENERGY,
                session=SessionWindow.commodity_extended(),
                max_leverage=3,
                volatility_profile="high",  # EIA inventory swings
                min_notional_usdt=Decimal("10"),
                # BingX VST: NCCO1OILWTI2USD (WTI). CL/BZ/NG — alias backward-compat.
                base_symbols=("NCCO1OILWTI2USD", "NCCO7241OILWTI2USD", "CL", "BZ", "NG"),
            ),
            "stock_perp": AssetConfig(
                asset_class=AssetClass.STOCK_PERP,
                session=SessionWindow.us_market_hours(),
                max_leverage=3,  # overnight gap risk → ниже cap
                volatility_profile="normal",
                min_notional_usdt=Decimal("10"),
                # BingX VST формат: NCSK<TICKER>2USD. TSLA/NVDA/... — alias.
                base_symbols=(
                    "NCSKTSLA2USD",
                    "NCSKNVDA2USD",
                    "TSLA",
                    "NVDA",
                    "AAPL",
                    "AMZN",
                    "GOOG",
                    "META",
                ),
            ),
        }
    )


DEFAULT_REGISTRY: AssetRegistry = _build_default_registry()

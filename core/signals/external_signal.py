"""Перенос сигнала с глубокого базового актива на BingX-перп (план 27).

Перпы BingX (золото/нефть/акции) листанулы недавно → истории
мало. Решение: считать сигнал по БАЗОВОМУ активу (десятилетия
Yahoo), исполнять на перпе. Здесь — провайдер дискретного
направления (LONG/SHORT/FLAT), а не «чужой триггер»: логика
собственная (TSMOM, публичная академия Moskowitz 2012, план 26).

⚠️ Архитектура валидна, но к LIVE не ведёт без месяцев демо +
явного подтверждения (фрикции перпа на <1г истории не
валидируемы — план 27). Только золото (план 26: нефть/индексы
не проходят).

Graceful: Yahoo недоступен → FLAT (раннер/бэктест не падает).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol, runtime_checkable

import httpx

from parsers.macro.seasonality import _fetch_monthly_closes

# Перп BingX → тикер базового актива Yahoo (глубокая история).
# Принцип CLAUDE.md №1: сигнал валидируется во внешнем глубоком
# источнике, исполняется на перпе. Это КАРТА покрытия, НЕ
# гарантия edge — проходимость гейта проверяет план 26 (tsmom_eval).
# Крипто-перпы сюда НЕ входят: их «глубокий источник» — Coinglass
# (DOLF, план 23), а не ценовой прокси.
_PERP_TO_UNDERLYING: dict[str, str] = {
    # Металлы / товары
    "XAUT-USDT": "GC=F",
    "NCCOGOLD2USD-USDT": "GC=F",
    "NCCO1OILWTI2USD-USDT": "CL=F",
    "NCCO1OILBRENT2USD-USDT": "BZ=F",
    "NCCOHEATINGOIL2USD-USDT": "HO=F",
    # Индексы
    "NCSINASDAQ1002USD-USDT": "^IXIC",
    "NCSISP5002USD-USDT": "^GSPC",
    "NCSIDOWJONES2USD-USDT": "^DJI",
    # Токен-акции
    "NCSKTSLA2USD-USDT": "TSLA",
    "NCSKNVDA2USD-USDT": "NVDA",
    "NCSKAAPL2USD-USDT": "AAPL",
    "NCSKGOOGL2USD-USDT": "GOOGL",
    "NCSKMETA2USD-USDT": "META",
    "NCSKMSTR2USD-USDT": "MSTR",
    "AAPLX-USDT": "AAPL",
    "NVDAX-USDT": "NVDA",
    "METAX-USDT": "META",
    # FX
    "NCFXAUD2USD-USDT": "AUDUSD=X",
}
_TSMOM_LOOKBACK_M = 12  # план 26 / Moskowitz 2012


class SignalDirection(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"
    FLAT = "FLAT"


@runtime_checkable
class SignalProvider(Protocol):
    """Дискретное направление по символу-перпу на момент ts."""

    def direction(self, perp_symbol: str, timestamp_ms: int) -> SignalDirection: ...


def map_perp_to_underlying(perp_symbol: str) -> str | None:
    """Перп BingX → базовый тикер Yahoo (None если не поддержан)."""
    return _PERP_TO_UNDERLYING.get(perp_symbol)


class TsmomSignalProvider:
    """TSMOM-направление по базовому активу (знак 12-мес доходности).

    Сигнал не зависит от истории перпа — считается по глубокому
    базовому. ``client`` DI для тестов. Кэш на инстанс (Yahoo
    дёргать на каждый бар не нужно — месячный сигнал).
    """

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        lookback_months: int = _TSMOM_LOOKBACK_M,
        backoff: float = 2.0,
    ) -> None:
        self._client = client
        self._lookback = lookback_months
        self._backoff = backoff
        self._cache: dict[str, list[float]] = {}

    def _closes(self, underlying: str) -> list[float]:
        if underlying not in self._cache:
            series = _fetch_monthly_closes(
                underlying, years=20, client=self._client, backoff=self._backoff
            )
            self._cache[underlying] = [c for _, c in series]
        return self._cache[underlying]

    def direction(self, perp_symbol: str, timestamp_ms: int) -> SignalDirection:
        underlying = map_perp_to_underlying(perp_symbol)
        if underlying is None:
            return SignalDirection.FLAT
        closes = self._closes(underlying)
        if len(closes) <= self._lookback:
            return SignalDirection.FLAT  # Yahoo пусто/мало → no-op
        past = closes[-self._lookback - 1]
        now = closes[-1]
        if past <= 0:
            return SignalDirection.FLAT
        ret = now / past - 1.0
        if ret > 0:
            return SignalDirection.LONG
        if ret < 0:
            return SignalDirection.SHORT
        return SignalDirection.FLAT

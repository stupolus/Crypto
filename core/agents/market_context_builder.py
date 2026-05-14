"""MarketContextBuilder — конвертация Kline history → MarketContextData.

Строит ``MarketContextData`` (input для Market Analyst Layer 3.1) из
истории свечей + текущих индикаторов. Используется в llm_runner между
``strategy.on_candle_close`` и ``llm_gate``.

Базовые индикаторы (ATR, Donchian, EMA20, EMA50) считаются из ``Kline``
истории через ``core.signals.indicators``. Орденбук / OI / funding —
пока заглушки "0", т.к. требуют отдельных каналов (BingX public WS).
Добавим в отдельных PR по мере подключения источников.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from adapters.bingx.models import Kline
from core.agents.evaluate import MarketContextData
from core.signals.indicators import atr, donchian_channel, ema

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MarketBuilderConfig:
    """Параметры индикаторов для контекста.

    Defaults подобраны под 15m стратегии (btc_breakout/us_session_breakout):
    - ATR 14 — стандарт
    - Donchian 20 — соответствует btc_breakout config
    - EMA 20/50 — fast/slow для trend filter
    - ohlcv_recent_n 20 — Market Analyst видит ~5 часов истории на 15m
    """

    atr_period: int = 14
    donchian_period: int = 20
    ema_fast_period: int = 20
    ema_slow_period: int = 50
    ohlcv_recent_n: int = 20


class MarketContextBuilder:
    """Сборщик MarketContextData из истории свечей.

    Не делает никакого I/O — только pure compute. Sentinel-defaults ("0")
    для индикаторов, которых не хватает (мало истории / источник недоступен).

    Использование::

        builder = MarketContextBuilder()
        ctx = builder.build(history=state.candles_history)
    """

    def __init__(self, config: MarketBuilderConfig | None = None) -> None:
        self._config = config or MarketBuilderConfig()

    def build(
        self,
        *,
        history: Sequence[Kline],
        funding_rate: Decimal | None = None,
        oi_change_24h_pct: Decimal | None = None,
        bid_5: Decimal | None = None,
        ask_5: Decimal | None = None,
        orderbook_imbalance: Decimal | None = None,
    ) -> MarketContextData:
        """Построить MarketContextData. При нехватке свечей — defaults "0"."""
        return MarketContextData(
            ohlcv_recent_json=self._serialize_ohlcv(history),
            atr=_decimal_or_zero(self._safe_atr(history)),
            donchian_high=self._safe_donchian(history)[0],
            donchian_low=self._safe_donchian(history)[1],
            ema20=_decimal_or_zero(self._safe_ema(history, self._config.ema_fast_period)),
            ema50=_decimal_or_zero(self._safe_ema(history, self._config.ema_slow_period)),
            bid_5=_decimal_or_zero(bid_5),
            ask_5=_decimal_or_zero(ask_5),
            orderbook_imbalance=_decimal_or_zero(orderbook_imbalance),
            funding_rate=_decimal_or_zero(funding_rate),
            oi_change_24h_pct=_decimal_or_zero(oi_change_24h_pct),
        )

    def _safe_atr(self, history: Sequence[Kline]) -> Decimal | None:
        period = self._config.atr_period
        if len(history) < period + 1:
            logger.debug("MarketContextBuilder: not enough candles for ATR(%d)", period)
            return None
        try:
            return atr(history, period)
        except ValueError as e:
            logger.warning("MarketContextBuilder atr failed: %s", e)
            return None

    def _safe_donchian(self, history: Sequence[Kline]) -> tuple[str, str]:
        period = self._config.donchian_period
        if len(history) < period:
            return "0", "0"
        try:
            upper, lower = donchian_channel(history, period)
        except ValueError as e:
            logger.warning("MarketContextBuilder donchian failed: %s", e)
            return "0", "0"
        return str(upper), str(lower)

    def _safe_ema(self, history: Sequence[Kline], period: int) -> Decimal | None:
        if len(history) < period:
            return None
        closes = [c.close for c in history]
        try:
            return ema(closes, period)
        except ValueError as e:
            logger.warning("MarketContextBuilder ema(%d) failed: %s", period, e)
            return None

    def _serialize_ohlcv(self, history: Sequence[Kline]) -> str:
        """Последние N свечей в JSON для Market Analyst.

        Формат: список dict-ов с time/open/high/low/close/volume — те же
        поля что в Kline, Decimal сериализуем как строки чтобы не терять
        точность.
        """
        n = self._config.ohlcv_recent_n
        if not history:
            return "[]"
        recent = list(history[-n:])
        payload = [
            {
                "time": c.open_time_ms,
                "open": str(c.open),
                "high": str(c.high),
                "low": str(c.low),
                "close": str(c.close),
                "volume": str(c.volume),
            }
            for c in recent
        ]
        return json.dumps(payload, ensure_ascii=False)


def _decimal_or_zero(value: Decimal | None) -> str:
    return str(value) if value is not None else "0"

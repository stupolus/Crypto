"""Live-обёртки провайдеров для liquidation_reversal (план 21 фаза 21.3).

BingX отдаёт открытый интерес как snapshot (не временной ряд). Live-
стратегии нужен ряд — поэтому runner периодически поллит snapshot и
кладёт в in-memory ring через ``record``. Стратегия читает ``get_series``
(тот же протокол ``OpenInterestProvider``, что и Static-заглушка).

Coinglass-обёртка для ликвидаций — отдельная задача, ждёт API-ключ
(plan 21 TODO, бюджет одобрен 2026-05-15).
"""

from __future__ import annotations

import logging
from collections import deque
from decimal import Decimal

logger = logging.getLogger(__name__)

_DEFAULT_MAXLEN = 500


class RollingOpenInterestProvider:
    """In-memory ring OI per symbol. Runner кормит snapshot'ами.

    Реализует ``OpenInterestProvider`` (``get_series``). ``record``
    добавляет точку; дубликаты по ts игнорируются (idempotent poll).
    ``maxlen`` ограничивает память (по умолчанию 500 точек на symbol).
    """

    def __init__(self, maxlen: int = _DEFAULT_MAXLEN) -> None:
        self._maxlen = maxlen
        self._series: dict[str, deque[tuple[int, Decimal]]] = {}

    def record(self, symbol: str, timestamp_ms: int, oi: Decimal) -> None:
        dq = self._series.setdefault(symbol, deque(maxlen=self._maxlen))
        if dq and dq[-1][0] == timestamp_ms:
            return  # тот же срез — не дублируем
        dq.append((timestamp_ms, oi))

    def get_series(self, symbol: str, timestamp_ms: int, n: int) -> list[Decimal]:
        dq = self._series.get(symbol)
        if not dq:
            return []
        vals = [v for ts, v in dq if ts <= timestamp_ms]
        return vals[-n:]


async def poll_open_interest(
    public_api: object,
    symbol: str,
    provider: RollingOpenInterestProvider,
) -> bool:
    """Запросить текущий OI у BingX и записать в provider.

    ``public_api`` — ``adapters.bingx.public.PublicAPI`` (duck-typed
    чтобы не тащить адаптер в core). Best-effort: ошибка → False + log,
    runner не падает.
    """
    try:
        oi = await public_api.get_open_interest(symbol)  # type: ignore[attr-defined]
    except Exception as e:
        logger.warning("poll_open_interest failed for %s: %s", symbol, e)
        return False
    provider.record(symbol, oi.time_ms, oi.open_interest)
    return True

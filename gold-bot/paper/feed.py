"""PaperFeed: опрос fetch_ohlcv и выдача только закрытых свечей.

Принципы (plan 06 §«Ключевые инварианты»):
- Решения принимаются ТОЛЬКО по закрытым свечам.
- Свеча считается закрытой, когда `now_ms >= candle.timestamp + tf_ms + close_grace_ms`.
- Свеча с тем же timestamp, что и last_seen, не эмитится повторно.
- Если poll пропустил окно (рестарт, сеть) — догоняем все пропущенные.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Protocol

from exchanges.models import OHLCV
from marketdata.candles import timeframe_to_ms


class _OhlcvSource(Protocol):
    async def fetch_ohlcv(
        self, symbol: str, timeframe: str, since: int | None = None, limit: int | None = None
    ) -> list[OHLCV]: ...


def _now_ms() -> int:
    return int(time.time() * 1000)


class PaperFeed:
    """Поллер закрытых свечей по одному символу.

    Состояние last_seen_ts хранится снаружи (в журнале) — feed не пишет
    в журнал. Caller отвечает за персистенцию.
    """

    def __init__(
        self,
        adapter: _OhlcvSource,
        symbol: str,
        timeframe: str,
        close_grace_ms: int,
        clock: Callable[[], int] = _now_ms,
        page_limit: int = 500,
    ) -> None:
        self._adapter = adapter
        self._symbol = symbol
        self._timeframe = timeframe
        self._tf_ms = timeframe_to_ms(timeframe)
        self._grace = max(0, int(close_grace_ms))
        self._clock = clock
        self._page_limit = page_limit

    def _is_closed(self, candle: OHLCV) -> bool:
        return self._clock() >= candle.timestamp + self._tf_ms + self._grace

    async def fetch_new_closed(self, last_seen_ts: int | None) -> list[OHLCV]:
        """Вернуть закрытые свечи с timestamp > last_seen_ts по возрастанию.

        Безопасно к повторам: одна и та же свеча не вернётся дважды, если
        caller продвигает last_seen_ts. Если last_seen_ts is None —
        возвращается одна последняя закрытая свеча (стартовое заполнение).
        """
        since = None if last_seen_ts is None else last_seen_ts + 1
        raw = await self._adapter.fetch_ohlcv(
            self._symbol, self._timeframe, since=since, limit=self._page_limit
        )
        result: list[OHLCV] = []
        for candle in sorted(raw, key=lambda c: c.timestamp):
            if last_seen_ts is not None and candle.timestamp <= last_seen_ts:
                continue
            if not self._is_closed(candle):
                continue
            result.append(candle)
        if last_seen_ts is None and len(result) > 1:
            # стартовый случай: берём только самую свежую закрытую,
            # чтобы не «торговать прошлым» при первом запуске
            return [result[-1]]
        return result


_FetchFn = Callable[[str, str, int | None, int | None], Awaitable[list[OHLCV]]]

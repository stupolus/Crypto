"""Загрузка и хранение исторических OHLCV-свечей.

Скачивает свечи через адаптер (plan 01) с пагинацией и дедупликацией,
хранит в parquet. Цены/объёмы в parquet — строки, чтобы не терять точность
Decimal. Все timestamp — ms epoch (как ccxt).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol

import pyarrow as pa
import pyarrow.parquet as pq

from exchanges.models import OHLCV
from exchanges.normalize import to_canonical

_TF_UNITS_MS = {"m": 60_000, "h": 3_600_000, "d": 86_400_000, "w": 604_800_000}
_TF_RE = re.compile(r"^(\d+)([mhdw])$")
_PRICE_FIELDS = ("open", "high", "low", "close", "volume")


class _OhlcvSource(Protocol):
    async def fetch_ohlcv(
        self, symbol: str, timeframe: str, since: int | None = None, limit: int | None = None
    ) -> list[OHLCV]: ...


def timeframe_to_ms(timeframe: str) -> int:
    m = _TF_RE.match(timeframe.strip().lower())
    if not m:
        raise ValueError(f"не разобрать таймфрейм: {timeframe!r}")
    amount, unit = int(m.group(1)), m.group(2)
    if amount <= 0:
        raise ValueError(f"таймфрейм должен быть положительным: {timeframe!r}")
    return amount * _TF_UNITS_MS[unit]


async def download_ohlcv(
    adapter: _OhlcvSource,
    symbol: str,
    timeframe: str,
    start_ms: int,
    end_ms: int | None = None,
    page_limit: int = 1000,
) -> list[OHLCV]:
    """Скачать свечи [start_ms, end_ms] с пагинацией вперёд и дедупом по timestamp."""
    timeframe_to_ms(timeframe)  # валидация таймфрейма
    collected: dict[int, OHLCV] = {}
    since = start_ms
    while True:
        page = await adapter.fetch_ohlcv(symbol, timeframe, since=since, limit=page_limit)
        if not page:
            break
        page_max = max(c.timestamp for c in page)
        for candle in page:
            if end_ms is not None and candle.timestamp > end_ms:
                continue
            collected.setdefault(candle.timestamp, candle)
        if end_ms is not None and page_max >= end_ms:
            break
        next_since = page_max + 1
        if next_since <= since:  # нет прогресса — защита от бесконечного цикла
            break
        since = next_since
    return [collected[ts] for ts in sorted(collected)]


def candles_path(base_dir: Path | str, exchange: str, symbol: str, timeframe: str) -> Path:
    safe = to_canonical(symbol).replace("/", "_").replace(":", "_")
    return Path(base_dir) / "candles" / exchange / safe / f"{timeframe}.parquet"


def save_parquet(candles: Sequence[OHLCV], path: Path | str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    columns: dict[str, list[Any]] = {"timestamp": [c.timestamp for c in candles]}
    for field in _PRICE_FIELDS:
        columns[field] = [str(getattr(c, field)) for c in candles]
    table = pa.table(columns)
    pq.write_table(table, target)


def load_parquet(path: Path | str) -> list[OHLCV]:
    table = pq.read_table(Path(path))
    data: dict[str, list[Any]] = table.to_pydict()
    timestamps: list[Any] = data["timestamp"]
    rows: list[OHLCV] = []
    for i in range(len(timestamps)):
        rows.append(
            OHLCV(
                timestamp=int(timestamps[i]),
                open=Decimal(data["open"][i]),
                high=Decimal(data["high"][i]),
                low=Decimal(data["low"][i]),
                close=Decimal(data["close"][i]),
                volume=Decimal(data["volume"][i]),
            )
        )
    rows.sort(key=lambda c: c.timestamp)
    return rows

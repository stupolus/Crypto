"""Простые метрики латенси/слиппеджа для ордеров (фаза 0.E).

JSON-lines writer. Один файл на запуск (`ops/metrics-<startts>.jsonl`) или
общий append-only (`ops/metrics.jsonl`). По умолчанию — общий.

Принципы:
- ``Decimal`` сериализуется в строку (стандартный JSON не умеет Decimal).
- Запись через ``asyncio.to_thread`` — синхронный fopen не блокирует loop.
- Структура events задана `OrderMetric`. Расширение полей — Optional, чтобы
  старые записи оставались парсимыми.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path


@dataclass(frozen=True)
class OrderMetric:
    client_order_id: str
    symbol: str
    side: str
    type: str
    request_started_ms: int
    ack_received_ms: int
    latency_ms: int
    ack_status: str
    request_mark_price: Decimal | None = None
    ack_avg_price: Decimal | None = None
    slippage_bps: Decimal | None = None


def _serialize(metric: OrderMetric) -> str:
    data = asdict(metric)
    # Decimal → str (JSON стандартный не сериализует Decimal).
    for key, value in list(data.items()):
        if isinstance(value, Decimal):
            data[key] = format(value.normalize(), "f")
    return json.dumps(data, ensure_ascii=False)


def compute_slippage_bps(
    side: str,
    request_mark_price: Decimal | None,
    ack_avg_price: Decimal | None,
) -> Decimal | None:
    """Slippage в bps относительно mark price на момент отправки.

    Положительный = хуже для нас (купили дороже / продали дешевле).
    Не считаем если нет либо референсной, либо ack-цены.
    """
    if request_mark_price is None or ack_avg_price is None:
        return None
    if request_mark_price <= 0:
        return None
    if ack_avg_price <= 0:
        # MARKET без fill (например, REJECTED) — slippage не определён.
        return None
    diff = ack_avg_price - request_mark_price
    bps = (diff / request_mark_price) * Decimal(10000)
    # Для SELL знак переворачиваем — там «хуже» = avg ниже mark.
    if side.upper() == "SELL":
        bps = -bps
    return bps.quantize(Decimal("0.0001"))


class MetricsWriter:
    """Append-only JSON-lines writer метрик ордера."""

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _write_sync(self, line: str) -> None:
        with self._path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    async def record(self, metric: OrderMetric) -> None:
        line = _serialize(metric)
        await asyncio.to_thread(self._write_sync, line)


def now_ms() -> int:
    """Локальное время в миллисекундах. Для latency расчётов."""
    return int(time.time() * 1000)

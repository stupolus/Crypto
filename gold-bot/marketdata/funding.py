"""Загрузка и хранение исторических funding-rates для перпов.

Используется в плане 11 (funding-arb). Без funding-истории на 2 биржах
синхронизированной по времени нельзя сделать бэктест арбитража.

Формат хранения — parquet, цены/ставки — строки чтобы не терять точность
Decimal. Все timestamp — ms epoch (как ccxt).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol

import pyarrow as pa
import pyarrow.parquet as pq

from exchanges.normalize import to_canonical


@dataclass(frozen=True)
class FundingRate:
    """Одна точка funding-rate на бирже.

    `timestamp` — момент применения funding (settlement), не «текущее значение
    funding»: в ccxt fetch_funding_rate_history возвращает уже применённые ставки.
    """

    timestamp: int
    rate: Decimal


class _FundingSource(Protocol):
    """Минимальный контракт адаптера для скачивания funding-истории."""

    async def fetch_funding_rate_history(
        self,
        symbol: str,
        since: int | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]: ...


async def download_funding_history(
    adapter: _FundingSource,
    symbol: str,
    start_ms: int,
    end_ms: int | None = None,
    page_limit: int = 200,
) -> list[FundingRate]:
    """Скачать funding-историю с пагинацией вперёд и дедупом по timestamp.

    ccxt fetch_funding_rate_history возвращает list[dict] с ключами
    `timestamp` (ms) и `fundingRate` (float/None). Нормализуем в Decimal.
    """
    collected: dict[int, FundingRate] = {}
    since = start_ms
    while True:
        page = await adapter.fetch_funding_rate_history(symbol, since=since, limit=page_limit)
        if not page:
            break
        page_max = max(int(p["timestamp"]) for p in page if p.get("timestamp") is not None)
        for entry in page:
            ts = entry.get("timestamp")
            rate_raw = entry.get("fundingRate")
            if ts is None or rate_raw is None:
                continue
            ts_int = int(ts)
            if end_ms is not None and ts_int > end_ms:
                continue
            collected.setdefault(ts_int, FundingRate(timestamp=ts_int, rate=Decimal(str(rate_raw))))
        if end_ms is not None and page_max >= end_ms:
            break
        next_since = page_max + 1
        if next_since <= since:  # нет прогресса — защита от бесконечного цикла
            break
        since = next_since
    return [collected[ts] for ts in sorted(collected)]


def funding_path(base_dir: Path | str, exchange: str, symbol: str) -> Path:
    """Канонический путь для хранения funding-истории символа."""
    safe = to_canonical(symbol).replace("/", "_").replace(":", "_")
    return Path(base_dir) / "funding" / exchange / f"{safe}.parquet"


def save_parquet(rates: Sequence[FundingRate], path: Path | str) -> None:
    """Сохранить funding-историю в parquet (timestamp + rate как строка)."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    columns: dict[str, list[Any]] = {
        "timestamp": [r.timestamp for r in rates],
        "rate": [str(r.rate) for r in rates],
    }
    table = pa.table(columns)
    pq.write_table(table, target)


def load_parquet(path: Path | str) -> list[FundingRate]:
    """Загрузить funding-историю из parquet, отсортированную по timestamp."""
    table = pq.read_table(Path(path))
    data: dict[str, list[Any]] = table.to_pydict()
    timestamps: list[Any] = data["timestamp"]
    rates: list[Any] = data["rate"]
    rows: list[FundingRate] = []
    for i in range(len(timestamps)):
        rows.append(FundingRate(timestamp=int(timestamps[i]), rate=Decimal(rates[i])))
    rows.sort(key=lambda r: r.timestamp)
    return rows


def align_funding_pair(
    rates_a: Sequence[FundingRate],
    rates_b: Sequence[FundingRate],
    tolerance_ms: int = 60_000,
) -> list[tuple[FundingRate, FundingRate]]:
    """Парный выравниватель funding-точек двух бирж по timestamp.

    Возвращает только те пары (a, b), где |a.timestamp - b.timestamp| <= tolerance_ms.
    Используется в funding-arb бэктесте: на каждую точку funding-периода нужны
    значения обеих бирж в синхронном моменте.

    Если расписание funding разное (BingX каждые 8h в 00/08/16 UTC, Bybit может
    отличаться) — tolerance_ms должен быть достаточным чтобы матчить ближайшие
    точки, но не настолько большим чтобы матчить разные периоды.
    """
    if tolerance_ms < 0:
        raise ValueError("tolerance_ms должен быть >= 0")
    sorted_a = sorted(rates_a, key=lambda r: r.timestamp)
    sorted_b = sorted(rates_b, key=lambda r: r.timestamp)
    out: list[tuple[FundingRate, FundingRate]] = []
    j = 0
    for a in sorted_a:
        # двигаем j до ближайшей точки b
        while j + 1 < len(sorted_b) and abs(sorted_b[j + 1].timestamp - a.timestamp) <= abs(
            sorted_b[j].timestamp - a.timestamp
        ):
            j += 1
        if j >= len(sorted_b):
            break
        b = sorted_b[j]
        if abs(b.timestamp - a.timestamp) <= tolerance_ms:
            out.append((a, b))
    return out


def divergence_stats(
    paired: Sequence[tuple[FundingRate, FundingRate]],
) -> dict[str, Decimal | int]:
    """Статистика расхождения funding между двух бирж по выравненным парам.

    Используется для recon-стадии плана 11B: смотрим median(|Δ|), max(|Δ|),
    quantiles. Если медиана < 0.005% → гипотеза funding-arb мертва, кода
    стратегии не пишем.
    """
    if not paired:
        return {
            "n": 0,
            "median_abs_diff": Decimal(0),
            "max_abs_diff": Decimal(0),
            "p90_abs_diff": Decimal(0),
        }
    diffs = sorted(abs(a.rate - b.rate) for a, b in paired)
    n = len(diffs)
    median = diffs[n // 2]
    p90_idx = min(n - 1, int(n * 0.9))
    p90 = diffs[p90_idx]
    max_d = diffs[-1]
    return {
        "n": n,
        "median_abs_diff": median,
        "max_abs_diff": max_d,
        "p90_abs_diff": p90,
    }

"""Скрипт загрузки исторических свечей через BingX REST.

Запуск:
    .venv/bin/python -m scripts.download_klines \\
        --symbol BTC-USDT --interval 15m --months 6

Сохраняет JSON-lines в ``data/candles/<symbol>-<interval>.jsonl``
(уже в gitignore).

Принципы:
- BingX отдаёт максимум 1440 свечей за запрос (квирк §7 п.13). Идём
  пачками назад от текущего момента, склеиваем без дубликатов.
- Token-bucket rate limit (350/10s) применяется автоматически
  ``BingXClient``.
- При повторном запуске — догружаем недостающее (idempotent через
  набор уникальных ``open_time_ms``).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import time
from pathlib import Path

from adapters.bingx.client import BingXClient
from adapters.bingx.models import Kline
from adapters.bingx.public import PublicAPI

logger = logging.getLogger(__name__)

# Длительность интервалов в миллисекундах. Поддерживаем те же, что в
# `adapters/bingx/config.yaml` → klines.intervals_rest.
_INTERVAL_MS: dict[str, int] = {
    "1m": 60_000,
    "3m": 3 * 60_000,
    "5m": 5 * 60_000,
    "15m": 15 * 60_000,
    "30m": 30 * 60_000,
    "1h": 60 * 60_000,
    "2h": 2 * 60 * 60_000,
    "4h": 4 * 60 * 60_000,
    "6h": 6 * 60 * 60_000,
    "8h": 8 * 60 * 60_000,
    "12h": 12 * 60 * 60_000,
    "1d": 24 * 60 * 60_000,
}


async def download(
    symbol: str,
    interval: str,
    months: int,
    out_path: Path,
) -> None:
    interval_ms = _INTERVAL_MS[interval]
    end_ms = int(time.time() * 1000)
    start_ms = end_ms - months * 30 * 24 * 60 * 60_000
    batch_size = 1440  # лимит BingX

    seen_times: set[int] = set()
    candles: list[Kline] = []

    # Если файл уже существует — читаем что есть, продолжаем оттуда.
    if out_path.exists():
        with out_path.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                raw = json.loads(line)
                kline = Kline.model_validate(raw)
                seen_times.add(kline.open_time_ms)
                candles.append(kline)
        logger.info("loaded %d existing candles from %s", len(candles), out_path)
        candles.sort(key=lambda k: k.open_time_ms)

    async with BingXClient() as client:
        api = PublicAPI(client, client.config)
        cursor_end_ms = end_ms
        batches_done = 0

        while cursor_end_ms > start_ms:
            cursor_start_ms = max(cursor_end_ms - batch_size * interval_ms, start_ms)
            logger.info(
                "batch %d: %s → %s",
                batches_done + 1,
                cursor_start_ms,
                cursor_end_ms,
            )
            batch = await api.get_klines(
                symbol=symbol,
                interval=interval,
                limit=batch_size,
                start_time_ms=cursor_start_ms,
                end_time_ms=cursor_end_ms,
            )
            new_candles = [k for k in batch if k.open_time_ms not in seen_times]
            for k in new_candles:
                seen_times.add(k.open_time_ms)
                candles.append(k)
            logger.info(
                "  got %d candles, %d new (total %d)",
                len(batch),
                len(new_candles),
                len(candles),
            )
            if not new_candles:
                break  # BingX больше нечего отдавать
            cursor_end_ms = min(k.open_time_ms for k in batch) - 1
            batches_done += 1
            # Лёгкая задержка чтобы не упереться в rate limit при большой
            # глубине — token bucket уже регулирует, но это запас.
            await asyncio.sleep(0.1)

    candles.sort(key=lambda k: k.open_time_ms)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for k in candles:
            f.write(k.model_dump_json(by_alias=True) + "\n")
    logger.info("saved %d candles to %s", len(candles), out_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Download BingX klines")
    parser.add_argument("--symbol", default="BTC-USDT")
    parser.add_argument("--interval", default="15m", choices=sorted(_INTERVAL_MS))
    parser.add_argument("--months", type=int, default=6)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Override output path (default: data/candles/<symbol>-<interval>.jsonl)",
    )
    parser.add_argument("--log-level", default="INFO", help="DEBUG / INFO / WARNING")
    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    out = args.output or Path(f"data/candles/{args.symbol.lower()}-{args.interval}.jsonl")
    asyncio.run(download(args.symbol, args.interval, args.months, out))


if __name__ == "__main__":
    main()

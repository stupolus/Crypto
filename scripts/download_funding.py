"""Скачивание истории funding rate через BingX REST.

Запуск:
    .venv/bin/python -m scripts.download_funding --symbol BTC-USDT --limit 1000

Сохраняет JSON-lines в ``data/funding/<symbol>.jsonl``.

Подготовка к future funding-strategies (D2 в plans/02 §13).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path

from adapters.bingx.client import BingXClient

logger = logging.getLogger(__name__)


async def download(symbol: str, limit: int, out_path: Path) -> None:
    """``GET /openApi/swap/v2/quote/fundingRate``.

    Параметр ``limit`` — сколько последних записей (макс. 1000 по docs-v3).
    Возвращаются по убыванию времени. Сохраняем как есть в jsonl.
    """
    async with BingXClient() as client:
        path = client.config.rest_endpoints.funding_rate_history
        data = await client.request_public(
            "GET",
            path,
            params={"symbol": symbol, "limit": limit},
        )
        # BingX отдаёт list или dict в зависимости от endpoint — нормализуем.
        if isinstance(data, dict) and "data" in data:
            data = data["data"]
        if not isinstance(data, list):
            raise SystemExit(
                f"unexpected funding response shape: {type(data).__name__}"
            )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Sort ASC by fundingTime для удобства time-series.
    data_sorted = sorted(data, key=lambda x: int(x.get("fundingTime", 0)))
    with out_path.open("w", encoding="utf-8") as f:
        for entry in data_sorted:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    logger.info("saved %d funding records to %s", len(data_sorted), out_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Download BingX funding history")
    parser.add_argument("--symbol", required=True)
    parser.add_argument(
        "--limit",
        type=int,
        default=1000,
        help="Сколько последних записей (макс 1000 на запрос)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Override output path (default: data/funding/<symbol>.jsonl)",
    )
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    out = args.output or Path(f"data/funding/{args.symbol.lower()}.jsonl")
    asyncio.run(download(args.symbol, args.limit, out))


if __name__ == "__main__":
    main()

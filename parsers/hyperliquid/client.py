"""Hyperliquid HTTP-клиент (план 22 фаза 22.C).

Публичный API без ключа: ``POST https://api.hyperliquid.xyz/info``
с телом ``{"type":"metaAndAssetCtxs"}`` → ``[meta, assetCtxs]``:

- ``meta.universe[i].name`` — тикер перпа (BTC, ETH, HYPE, ...)
- ``assetCtxs[i]`` — параллельный массив: ``openInterest`` (в
  монетах), ``funding`` (часовой, доля), ``markPx``, ``oraclePx``,
  ``dayNtlVlm`` (дневной объём в USD).

Best-effort: сетевая ошибка / неожиданный формат → ``[]`` +
WARNING (фильтры no-op, runner не падает) — как CoinglassClient.
"""

from __future__ import annotations

import logging
import time
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from parsers.hyperliquid.models import HyperliquidAssetCtx

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.hyperliquid.xyz"
_INFO_PATH = "/info"
_TIMEOUT_S = 15.0


def _to_decimal(v: Any) -> Decimal:
    try:
        return Decimal(str(v))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


class HyperliquidClient:
    """Тонкий httpx-клиент к публичному ``/info``. Ключ не нужен.

    ``client`` DI для тестов (respx).
    """

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        base_url: str = _BASE_URL,
    ) -> None:
        self._owns = client is None
        self._client = client or httpx.Client(timeout=_TIMEOUT_S, base_url=base_url)

    def close(self) -> None:
        if self._owns:
            self._client.close()

    def _post_info(self, body: dict[str, Any]) -> Any:
        try:
            resp = self._client.post(_INFO_PATH, json=body)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning("Hyperliquid %s failed: %s", body.get("type"), e)
            return None

    def get_asset_contexts(self) -> list[HyperliquidAssetCtx]:
        """Снимок OI/funding/цен по всем перпам. Пусто при ошибке.

        ``metaAndAssetCtxs`` → ``[{"universe":[...]}, [ctx, ...]]``;
        массивы параллельны по индексу.
        """
        data = self._post_info({"type": "metaAndAssetCtxs"})
        if not isinstance(data, list) or len(data) != 2:
            return []
        meta, ctxs = data
        universe = meta.get("universe") if isinstance(meta, dict) else None
        if not isinstance(universe, list) or not isinstance(ctxs, list):
            return []
        ts = int(time.time() * 1000)
        out: list[HyperliquidAssetCtx] = []
        for asset, ctx in zip(universe, ctxs, strict=False):
            if not isinstance(asset, dict) or not isinstance(ctx, dict):
                continue
            name = asset.get("name")
            mark = _to_decimal(ctx.get("markPx"))
            oracle = _to_decimal(ctx.get("oraclePx"))
            if not name or mark <= 0 or oracle <= 0:
                continue
            out.append(
                HyperliquidAssetCtx(
                    coin=str(name),
                    timestamp_ms=ts,
                    mark_px=mark,
                    oracle_px=oracle,
                    open_interest=_to_decimal(ctx.get("openInterest")),
                    funding=_to_decimal(ctx.get("funding")),
                    day_volume_usd=_to_decimal(ctx.get("dayNtlVlm")),
                )
            )
        return out

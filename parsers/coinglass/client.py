"""Coinglass HTTP-клиент (план 21 фаза 21.4).

Подтверждено ЖИВЫМ ключом (HOBBYIST $29) 2026-05-15:
- Base: ``https://open-api-v4.coinglass.com``, header ``CG-API-KEY``
- Envelope: ``{"code":"0","msg":"...","data":[...]}``
- ``/api/futures/liquidation/history`` → {time, long_liquidation_usd,
  short_liquidation_usd}
- ``/api/futures/open-interest/aggregated-history`` → OHLC (берём close)
- ``/api/futures/taker-buy-sell-volume/history`` → {taker_buy_volume_usd,
  taker_sell_volume_usd} → CVD = cumsum(buy−sell) (решает блокер B2)
- ``/api/futures/funding-rate/history`` → OHLC funding (берём close)

⚠️ Тариф HOBBYIST: liquidation/история только interval ∈
{4h,6h,8h,12h,1d,1w}. 15m/1h требуют STANDARD. Стратегия
liquidation_reversal должна гоняться на 4h+ на этом плане.

Graceful: 401/403/upgrade/network → ``[]`` + WARNING (стратегия
no-op, не падает).
"""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import httpx
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from parsers.coinglass.models import CoinglassLiquidationBucket

logger = logging.getLogger(__name__)

_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
_BASE_URL = "https://open-api-v4.coinglass.com"
_LIQ_HISTORY_PATH = "/api/futures/liquidation/history"
# По-биржевой OI history. Эмпирически (платный ключ, 2026-05-19): этот
# путь отдаёт 1000 OHLC-точек, тогда как aggregated-history на том же
# тарифе пуст. Aggregated оставлен как override-константа.
_OI_HISTORY_PATH = "/api/futures/open-interest/history"
_OI_AGG_HISTORY_PATH = "/api/futures/open-interest/aggregated-history"
_TIMEOUT_S = 15.0


class CoinglassSettings(BaseSettings):
    """``COINGLASS_API_KEY`` из .env (gitignored). None → клиент noop."""

    model_config = SettingsConfigDict(
        env_prefix="COINGLASS_",
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        frozen=True,
    )

    api_key: str | None = Field(default=None)


class CoinglassPlanError(Exception):
    """Coinglass вернул 401 'Upgrade plan' — нужен платный тариф."""


def _extract_ts(row: dict[str, Any]) -> int | None:
    """ts из row по ключам time/timestamp/t. Explicit None (ts=0 валиден,
    `or`-цепочка ошибочно отбрасывала бы falsy 0)."""
    for k in ("time", "timestamp", "t"):
        v = row.get(k)
        if v is not None:
            return int(v)
    return None


def _to_decimal(v: Any) -> Decimal:
    try:
        return Decimal(str(v))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


class CoinglassClient:
    """Тонкий httpx-клиент. Best-effort: сетевые/планные ошибки →
    пустой результат + WARNING (не валит стратегию/runner).

    ``client`` DI для тестов (respx). ``api_key`` override для тестов.
    """

    _UNSET = "__unset__"

    def __init__(
        self,
        api_key: str | None = _UNSET,
        *,
        client: httpx.Client | None = None,
        base_url: str = _BASE_URL,
        oi_history_path: str = _OI_HISTORY_PATH,
    ) -> None:
        # api_key опущен → читаем .env; явный None/строка → как передан
        # (None = тест unconfigured-пути).
        if api_key == self._UNSET:
            self._api_key = CoinglassSettings().api_key
        else:
            self._api_key = api_key
        self._owns = client is None
        self._client = client or httpx.Client(timeout=_TIMEOUT_S, base_url=base_url)
        self._base_url = base_url
        self._oi_path = oi_history_path

    def close(self) -> None:
        if self._owns:
            self._client.close()

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    def _get(self, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        if not self._api_key:
            logger.warning("CoinglassClient: no COINGLASS_API_KEY — returning empty")
            return []
        try:
            resp = self._client.get(path, params=params, headers={"CG-API-KEY": self._api_key})
            resp.raise_for_status()
            body = resp.json()
        except Exception as e:
            logger.warning("Coinglass %s failed: %s", path, e)
            return []
        code = str(body.get("code", ""))
        if code != "0":
            msg = body.get("msg", "")
            if "upgrade" in str(msg).lower() or code == "401":
                logger.warning(
                    "Coinglass %s: plan inactive (%s) — нужен платный тариф",
                    path,
                    msg,
                )
            else:
                logger.warning("Coinglass %s code=%s msg=%s", path, code, msg)
            return []
        data = body.get("data")
        return data if isinstance(data, list) else []

    def get_liquidation_history(
        self,
        *,
        exchange: str,
        symbol: str,
        interval: str,
        limit: int = 1000,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
    ) -> list[CoinglassLiquidationBucket]:
        """История long/short ликвидаций. Пусто если план не активен."""
        params: dict[str, Any] = {
            "exchange": exchange,
            "symbol": symbol,
            "interval": interval,
            "limit": min(max(limit, 1), 1000),
        }
        if start_time_ms is not None:
            params["start_time"] = start_time_ms
        if end_time_ms is not None:
            params["end_time"] = end_time_ms
        out: list[CoinglassLiquidationBucket] = []
        for row in self._get(_LIQ_HISTORY_PATH, params):
            ts = _extract_ts(row)
            if ts is None:
                continue
            out.append(
                CoinglassLiquidationBucket(
                    timestamp_ms=ts,
                    long_liquidation_usd=_to_decimal(
                        row.get("long_liquidation_usd")
                        or row.get("longLiquidationUsd")
                        or row.get("long")
                        or 0
                    ),
                    short_liquidation_usd=_to_decimal(
                        row.get("short_liquidation_usd")
                        or row.get("shortLiquidationUsd")
                        or row.get("short")
                        or 0
                    ),
                )
            )
        return out

    def get_open_interest_history(
        self,
        *,
        symbol: str,
        interval: str,
        exchange: str = "Binance",
        limit: int = 1000,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
    ) -> list[tuple[int, Decimal]]:
        """История OI как [(ts_ms, oi_usd)]. Пусто если план не активен.

        Путь ``/api/futures/open-interest/history`` требует ``exchange``
        и пары-символ (``BTCUSDT``). Парсинг полей толерантен
        (close/openInterest/value).
        """
        params: dict[str, Any] = {
            "exchange": exchange,
            "symbol": symbol,
            "interval": interval,
            "limit": min(max(limit, 1), 1000),
        }
        if start_time_ms is not None:
            params["start_time"] = start_time_ms
        if end_time_ms is not None:
            params["end_time"] = end_time_ms
        out: list[tuple[int, Decimal]] = []
        for row in self._get(self._oi_path, params):
            ts = _extract_ts(row)
            if ts is None:
                continue
            val = (
                row.get("close")
                or row.get("open_interest_usd")
                or row.get("openInterest")
                or row.get("value")
                or 0
            )
            out.append((ts, _to_decimal(val)))
        return out

    def get_cvd_history(
        self,
        *,
        exchange: str,
        symbol: str,
        interval: str,
        limit: int = 1000,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
    ) -> list[tuple[int, Decimal]]:
        """CVD = накопленная (taker_buy − taker_sell) из taker-volume.

        Coinglass ``/api/futures/taker-buy-sell-volume/history`` отдаёт
        per-bar buy/sell USD (подтверждено живым ключом 2026-05-15).
        Дельта бара = buy−sell; CVD = кумулятивная сумма (как в видео
        011 Щукина). Возвращаем [(ts, cvd)] ASC.
        """
        params: dict[str, Any] = {
            "exchange": exchange,
            "symbol": symbol,
            "interval": interval,
            "limit": min(max(limit, 1), 1000),
        }
        if start_time_ms is not None:
            params["start_time"] = start_time_ms
        if end_time_ms is not None:
            params["end_time"] = end_time_ms
        rows = self._get("/api/futures/taker-buy-sell-volume/history", params)
        timed: list[tuple[int, dict[str, Any]]] = []
        for r in rows:
            ts_v = _extract_ts(r)
            if ts_v is None:
                continue
            timed.append((ts_v, r))
        timed.sort(key=lambda x: x[0])
        cvd = Decimal("0")
        out: list[tuple[int, Decimal]] = []
        for ts, r in timed:
            buy = _to_decimal(r.get("taker_buy_volume_usd") or r.get("buy") or 0)
            sell = _to_decimal(r.get("taker_sell_volume_usd") or r.get("sell") or 0)
            cvd += buy - sell
            out.append((ts, cvd))
        return out

    def get_funding_history(
        self,
        *,
        exchange: str,
        symbol: str,
        interval: str,
        limit: int = 1000,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
    ) -> list[tuple[int, Decimal]]:
        """Funding rate (доля, не %). [(ts, funding_close)] ASC.

        ``/api/futures/funding-rate/history`` — OHLC; берём ``close``.
        """
        params: dict[str, Any] = {
            "exchange": exchange,
            "symbol": symbol,
            "interval": interval,
            "limit": min(max(limit, 1), 1000),
        }
        if start_time_ms is not None:
            params["start_time"] = start_time_ms
        if end_time_ms is not None:
            params["end_time"] = end_time_ms
        out: list[tuple[int, Decimal]] = []
        for row in self._get("/api/futures/funding-rate/history", params):
            ts = _extract_ts(row)
            if ts is None:
                continue
            out.append((ts, _to_decimal(row.get("close") or 0)))
        return out

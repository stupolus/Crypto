"""Публичные REST-методы BingX (USDT-M perpetual).

Все эндпоинты — без подписи. Источники, формат ответа и квирки —
``бизнес/инструменты-bingx.md`` и ``plans/01-bingx-адаптер.md`` §4.4, §7.

Архитектура: ``PublicAPI`` оборачивает ``BingXClient`` и возвращает уже
типизированные pydantic-модели. Сами эндпоинты + методы валидации —
изолированы от транспорта (``client.py``), чтобы тестировать через respx
без живого HTTP.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from adapters.bingx.client import BingXClient
from adapters.bingx.config import BingXConfig
from adapters.bingx.exceptions import APIError, InvalidResponseError
from adapters.bingx.models import Contract, Kline, ServerTime, Ticker


class PublicAPI:
    """Публичные эндпоинты BingX, типизированные."""

    def __init__(self, client: BingXClient, config: BingXConfig) -> None:
        self._client = client
        self._cfg = config

    # ── server time ────────────────────────────────────────────────────────
    async def get_server_time(self) -> ServerTime:
        """``GET /openApi/swap/v2/server/time`` — миллисекундный таймстамп BingX.

        Используется для синхронизации часов адаптера перед подписью
        (квирк §7 п.19 plans/01: ``|ts - serverTime| > recvWindow`` → reject).
        """
        data = await self._client.request_public("GET", self._cfg.rest_endpoints.server_time)
        return ServerTime.model_validate(_ensure_dict(data, "server_time"))

    # ── contracts ──────────────────────────────────────────────────────────
    async def get_contracts(self) -> list[Contract]:
        """``GET /openApi/swap/v2/quote/contracts`` — все USDT-M perpetuals.

        Источник правды для ``pricePrecision``/``quantityPrecision``,
        ``tradeMinUSDT``, ``maxLongLeverage``. Без него адаптер не может
        безопасно округлять ордера (квирк §7 п.10 plans/01: точность
        молча усечётся, если перебрать).
        """
        data = await self._client.request_public("GET", self._cfg.rest_endpoints.contracts)
        return [Contract.model_validate(item) for item in _ensure_list(data, "contracts")]

    async def get_contract(self, symbol: str) -> Contract:
        """Удобный фильтр по одному символу. Бросает APIError(404), если нет."""
        target = _normalize_symbol(symbol)
        for contract in await self.get_contracts():
            if contract.symbol == target:
                return contract
        raise APIError(404, f"contract {target!r} not in BingX listing", endpoint="contracts")

    # ── ticker ─────────────────────────────────────────────────────────────
    async def get_ticker(self, symbol: str) -> Ticker:
        """``GET /openApi/swap/v2/quote/ticker?symbol=BTC-USDT``.

        Возвращает 24h-статистику и last price. Параметр ``symbol``
        обязателен (квирк §7 п.1: с дефисом).
        """
        params = {"symbol": _normalize_symbol(symbol)}
        data = await self._client.request_public(
            "GET", self._cfg.rest_endpoints.ticker, params=params
        )
        return Ticker.model_validate(_ensure_dict(data, "ticker"))

    # ── klines ─────────────────────────────────────────────────────────────
    async def get_klines(
        self,
        symbol: str,
        interval: str,
        *,
        limit: int | None = None,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
    ) -> list[Kline]:
        """``GET /openApi/swap/v3/quote/klines``.

        Возвращает свечи, отсортированные по ``open_time_ms`` по возрастанию
        (oldest → newest). Сам BingX отдаёт DESC (newest first) —
        нормализуем здесь, чтобы стратегии/бэктест получали удобный для
        time-series анализа порядок.

        Квирки (§7 plans/01):
        - п.11: V3 не отдаёт ``n`` и ``q`` (только OHLCV+time).
        - п.13: ``limit`` ≤ 1440. Перебор не отвергается, а молча усекается —
          валидируем локально.
        - п.27 (новый, integration 2026-05-10): live BingX принимает только
          REST-форму интервала (``1m``, ``15m``) и в WS-канале. Формы
          ``1min``/``15min`` из docs отвергаются ``code=80015``.
        """
        rest_interval = self._normalize_interval_to_rest(interval)
        effective_limit = limit if limit is not None else self._cfg.klines.limit_default
        if effective_limit <= 0 or effective_limit > self._cfg.klines.limit_max:
            raise ValueError(
                f"klines limit must be in (0, {self._cfg.klines.limit_max}], got {effective_limit}"
            )

        params: dict[str, Any] = {
            "symbol": _normalize_symbol(symbol),
            "interval": rest_interval,
            "limit": effective_limit,
        }
        if start_time_ms is not None:
            params["startTime"] = start_time_ms
        if end_time_ms is not None:
            params["endTime"] = end_time_ms

        data = await self._client.request_public(
            "GET", self._cfg.rest_endpoints.klines, params=params
        )
        klines = [Kline.model_validate(item) for item in _ensure_list(data, "klines")]
        klines.sort(key=lambda k: k.open_time_ms)
        return klines

    # ── интервал-маппинг REST <-> WS ───────────────────────────────────────
    def _normalize_interval_to_rest(self, interval: str) -> str:
        rest = self._cfg.klines.intervals_rest
        ws = self._cfg.klines.intervals_ws
        if interval in rest:
            return interval
        if interval in ws:
            # parallel index: REST и WS списки выровнены по позициям в config.yaml.
            return rest[ws.index(interval)]
        raise ValueError(
            f"unknown kline interval {interval!r}; expected one of REST {rest} or WS {ws}"
        )


def _normalize_symbol(symbol: str) -> str:
    """Привести символ к BingX-форме ``BTC-USDT``.

    Принимаем ``BTCUSDT`` и ``btc-usdt`` для устойчивости, но в API всегда
    шлём с дефисом, верхним регистром (квирк §7 п.1 plans/01).
    """
    s = symbol.strip().upper()
    if "-" in s:
        return s
    if s.endswith("USDT") and len(s) > 4:
        return f"{s[:-4]}-USDT"
    raise ValueError(f"cannot normalize symbol {symbol!r}; expected like 'BTC-USDT' or 'BTCUSDT'")


def _ensure_dict(data: Any, where: str) -> Mapping[str, Any]:
    if not isinstance(data, Mapping):
        raise InvalidResponseError(
            f"BingX {where} expected object, got {type(data).__name__}: {data!r}"
        )
    return data


def _ensure_list(data: Any, where: str) -> list[Any]:
    if not isinstance(data, list):
        raise InvalidResponseError(
            f"BingX {where} expected list, got {type(data).__name__}: {data!r}"
        )
    return data

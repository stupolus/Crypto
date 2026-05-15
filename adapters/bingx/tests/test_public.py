"""Unit-тесты публичных REST-методов BingX.

Каждый метод проверяется на фикстуре с реальным форматом ответа из docs-v3
(см. ``adapters/bingx/tests/fixtures/``). Парсинг идёт через pydantic-модели,
поэтому ошибка схемы — это упавший тест, не молчаливая деградация.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import httpx
import pytest
import respx

from adapters.bingx.client import BingXClient
from adapters.bingx.config import BingXConfig
from adapters.bingx.exceptions import APIError, InvalidResponseError
from adapters.bingx.models import Contract
from adapters.bingx.public import PublicAPI, _normalize_symbol

# ── server time ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_server_time_parses_ms_timestamp(
    cfg: BingXConfig, server_time_payload: dict[str, Any]
) -> None:
    async with BingXClient(cfg) as client, respx.mock(base_url=cfg.active_rest_base) as mock:
        mock.get(cfg.rest_endpoints.server_time).mock(
            return_value=httpx.Response(200, json=server_time_payload)
        )
        public = PublicAPI(client, cfg)
        st = await public.get_server_time()
    assert st.server_time_ms == 1758297600123
    assert st.utc.year >= 2025  # ms timestamp в разумном диапазоне


# ── contracts ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_contracts_parses_btc_with_min_notional(
    cfg: BingXConfig, contracts_payload: dict[str, Any]
) -> None:
    """Подтверждаем главный факт из бизнес/инструменты-bingx.md:
    ``tradeMinUSDT == 2`` для BTC-USDT — основание снятого блокера фазы 1.
    """
    async with BingXClient(cfg) as client, respx.mock(base_url=cfg.active_rest_base) as mock:
        mock.get(cfg.rest_endpoints.contracts).mock(
            return_value=httpx.Response(200, json=contracts_payload)
        )
        public = PublicAPI(client, cfg)
        contracts = await public.get_contracts()

    btc = next(c for c in contracts if c.symbol == "BTC-USDT")
    assert isinstance(btc, Contract)
    assert btc.trade_min_usdt == Decimal("2")
    assert btc.price_precision == 1
    assert btc.quantity_precision == 4
    assert btc.max_long_leverage == 125
    assert btc.taker_fee_rate == Decimal("0.0005")


@pytest.mark.asyncio
async def test_get_contract_returns_single_by_symbol(
    cfg: BingXConfig, contracts_payload: dict[str, Any]
) -> None:
    async with BingXClient(cfg) as client, respx.mock(base_url=cfg.active_rest_base) as mock:
        mock.get(cfg.rest_endpoints.contracts).mock(
            return_value=httpx.Response(200, json=contracts_payload)
        )
        public = PublicAPI(client, cfg)
        eth = await public.get_contract("ETH-USDT")
    assert eth.symbol == "ETH-USDT"
    assert eth.price_precision == 2


@pytest.mark.asyncio
async def test_get_contract_raises_when_symbol_missing(
    cfg: BingXConfig, contracts_payload: dict[str, Any]
) -> None:
    async with BingXClient(cfg) as client, respx.mock(base_url=cfg.active_rest_base) as mock:
        mock.get(cfg.rest_endpoints.contracts).mock(
            return_value=httpx.Response(200, json=contracts_payload)
        )
        public = PublicAPI(client, cfg)
        with pytest.raises(APIError):
            await public.get_contract("DOGE-USDT")


def test_contract_rejects_symbol_without_hyphen() -> None:
    """Квирк §7 п.1 plans/01: BingX требует дефис; модель валидирует."""
    raw = {
        "contractId": "100",
        "symbol": "BTCUSDT",
        "quantityPrecision": 4,
        "pricePrecision": 1,
        "feeRate": 0.0005,
        "makerFeeRate": 0.0002,
        "takerFeeRate": 0.0005,
        "tradeMinQuantity": 0.0001,
        "tradeMinUSDT": 2,
        "maxLongLeverage": 125,
        "maxShortLeverage": 125,
        "currency": "USDT",
        "asset": "BTC",
        "status": 1,
    }
    with pytest.raises(ValueError, match="hyphen"):
        Contract.model_validate(raw)


# ── ticker ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_ticker_parses_24h_stats(
    cfg: BingXConfig, ticker_payload: dict[str, Any]
) -> None:
    async with BingXClient(cfg) as client, respx.mock(base_url=cfg.active_rest_base) as mock:
        mock.get(cfg.rest_endpoints.ticker).mock(
            return_value=httpx.Response(200, json=ticker_payload)
        )
        public = PublicAPI(client, cfg)
        ticker = await public.get_ticker("BTC-USDT")
    assert ticker.symbol == "BTC-USDT"
    assert ticker.last_price == Decimal("60500.7")
    assert ticker.high_price == Decimal("60900.0")
    assert ticker.quote_volume == Decimal("74567890.12")
    assert ticker.open_time.year >= 2025


# ── open interest ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_open_interest_parses_snapshot(cfg: BingXConfig) -> None:
    payload = {
        "code": 0,
        "msg": "",
        "data": {
            "openInterest": "123456.789",
            "symbol": "BTC-USDT",
            "time": 1_700_000_000_000,
        },
    }
    async with BingXClient(cfg) as client, respx.mock(base_url=cfg.active_rest_base) as mock:
        mock.get(cfg.rest_endpoints.open_interest).mock(
            return_value=httpx.Response(200, json=payload)
        )
        public = PublicAPI(client, cfg)
        oi = await public.get_open_interest("BTC-USDT")
    assert oi.symbol == "BTC-USDT"
    assert oi.open_interest == Decimal("123456.789")
    assert oi.time_ms == 1_700_000_000_000
    assert oi.time.year >= 2023


# ── klines ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_klines_parses_array_with_correct_intervals(
    cfg: BingXConfig, klines_payload: dict[str, Any]
) -> None:
    async with BingXClient(cfg) as client, respx.mock(base_url=cfg.active_rest_base) as mock:
        route = mock.get(cfg.rest_endpoints.klines).mock(
            return_value=httpx.Response(200, json=klines_payload)
        )
        public = PublicAPI(client, cfg)
        klines = await public.get_klines("BTC-USDT", "15m", limit=10)
    # Проверим что REST-интервал ушёл правильно.
    sent = route.calls.last.request.url
    assert "interval=15m" in str(sent)
    assert "limit=10" in str(sent)
    assert "symbol=BTC-USDT" in str(sent)
    # Парсинг.
    assert len(klines) == 2
    assert klines[0].close == Decimal("60400.5")
    assert klines[1].open == Decimal("60400.5")
    assert klines[0].open_time.year >= 2025


@pytest.mark.asyncio
async def test_get_klines_returns_ascending_by_open_time(
    cfg: BingXConfig,
) -> None:
    """Сам BingX отдаёт DESC; адаптер нормализует к ASC для удобства потребителей."""
    desc_payload = {
        "code": 0,
        "msg": "",
        "data": [
            {
                "open": "1",
                "high": "2",
                "low": "1",
                "close": "1.5",
                "volume": "10",
                "time": 1758298500000,
            },
            {
                "open": "0.5",
                "high": "1",
                "low": "0.5",
                "close": "1",
                "volume": "5",
                "time": 1758297600000,
            },
        ],
    }
    async with BingXClient(cfg) as client, respx.mock(base_url=cfg.active_rest_base) as mock:
        mock.get(cfg.rest_endpoints.klines).mock(
            return_value=httpx.Response(200, json=desc_payload)
        )
        public = PublicAPI(client, cfg)
        klines = await public.get_klines("BTC-USDT", "15m", limit=10)
    assert [k.open_time_ms for k in klines] == [1758297600000, 1758298500000]


@pytest.mark.asyncio
async def test_get_klines_rejects_unknown_interval(cfg: BingXConfig) -> None:
    async with BingXClient(cfg) as client:
        public = PublicAPI(client, cfg)
        with pytest.raises(ValueError, match="unknown kline interval"):
            await public.get_klines("BTC-USDT", "13s", limit=10)


@pytest.mark.asyncio
async def test_get_klines_rejects_limit_over_max(cfg: BingXConfig) -> None:
    """Квирк §7 п.13 plans/01: limit > 1440 молча усекается биржей.
    Адаптер обязан валидировать локально.
    """
    async with BingXClient(cfg) as client:
        public = PublicAPI(client, cfg)
        with pytest.raises(ValueError, match=r"\(0, 1440\]"):
            await public.get_klines("BTC-USDT", "15m", limit=1441)


@pytest.mark.asyncio
async def test_get_klines_uses_default_limit_when_none(
    cfg: BingXConfig, klines_payload: dict[str, Any]
) -> None:
    async with BingXClient(cfg) as client, respx.mock(base_url=cfg.active_rest_base) as mock:
        route = mock.get(cfg.rest_endpoints.klines).mock(
            return_value=httpx.Response(200, json=klines_payload)
        )
        public = PublicAPI(client, cfg)
        await public.get_klines("BTC-USDT", "15m")
    assert f"limit={cfg.klines.limit_default}" in str(route.calls.last.request.url)


# ── symbol normalization ────────────────────────────────────────────────────


def test_normalize_symbol_accepts_hyphenated_form() -> None:
    assert _normalize_symbol("btc-usdt") == "BTC-USDT"


def test_normalize_symbol_adds_hyphen_for_compact_form() -> None:
    assert _normalize_symbol("ETHUSDT") == "ETH-USDT"


def test_normalize_symbol_rejects_unknown_format() -> None:
    with pytest.raises(ValueError):
        _normalize_symbol("BTC")


# ── envelope-парсинг при битом data ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_contracts_raises_when_data_is_not_list(cfg: BingXConfig) -> None:
    async with BingXClient(cfg) as client, respx.mock(base_url=cfg.active_rest_base) as mock:
        mock.get(cfg.rest_endpoints.contracts).mock(
            return_value=httpx.Response(200, json={"code": 0, "msg": "", "data": {"oops": 1}})
        )
        public = PublicAPI(client, cfg)
        with pytest.raises(InvalidResponseError):
            await public.get_contracts()

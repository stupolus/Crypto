"""Unit-тесты маскирования секретов в логах."""

from __future__ import annotations

from adapters.bingx.client import mask_headers, mask_signed_url


def test_mask_signed_url_replaces_signature_value() -> None:
    url = (
        "https://open-api.bingx.com/openApi/swap/v2/trade/order"
        "?marginType=ISOLATED&symbol=BTC-USDT&timestamp=1700000000000"
        "&signature=deadbeef12345"
    )
    masked = mask_signed_url(url)
    assert "deadbeef12345" not in masked
    assert "signature=***" in masked
    # Бизнес-параметры остаются нетронутыми.
    assert "symbol=BTC-USDT" in masked
    assert "marginType=ISOLATED" in masked


def test_mask_signed_url_no_query_returns_unchanged() -> None:
    url = "https://open-api.bingx.com/openApi/swap/v2/quote/contracts"
    assert mask_signed_url(url) == url


def test_mask_headers_replaces_api_key_case_insensitive() -> None:
    headers = {
        "X-BX-APIKEY": "real-key",
        "Content-Type": "application/json",
        "User-Agent": "crypto-adapter/0.0.1",
    }
    masked = mask_headers(headers)
    assert masked["X-BX-APIKEY"] == "***"
    assert masked["Content-Type"] == "application/json"
    assert masked["User-Agent"] == "crypto-adapter/0.0.1"

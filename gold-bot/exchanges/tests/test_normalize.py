"""Тесты канонизации символов."""

from __future__ import annotations

import pytest

from exchanges.normalize import to_canonical


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("BTC-USDT", "BTC/USDT:USDT"),
        ("BTCUSDT", "BTC/USDT:USDT"),
        ("BTC/USDT", "BTC/USDT:USDT"),
        ("BTC/USDT:USDT", "BTC/USDT:USDT"),
        ("btc-usdt", "BTC/USDT:USDT"),
        ("  BTC-USDT  ", "BTC/USDT:USDT"),
        ("ETHUSDC", "ETH/USDC:USDC"),
        ("PAXGUSDT", "PAXG/USDT:USDT"),
        ("XAUTUSDT", "XAUT/USDT:USDT"),
    ],
)
def test_to_canonical(raw: str, expected: str) -> None:
    assert to_canonical(raw) == expected


def test_settle_override() -> None:
    assert to_canonical("BTC/USDT", settle="USDC") == "BTC/USDT:USDC"


def test_settle_from_symbol_preserved() -> None:
    assert to_canonical("BTC/USD:USDT") == "BTC/USD:USDT"


def test_empty_symbol_raises() -> None:
    with pytest.raises(ValueError):
        to_canonical("   ")


def test_unparsable_concatenated_raises() -> None:
    with pytest.raises(ValueError):
        to_canonical("FOOBAR")


def test_empty_settle_raises() -> None:
    with pytest.raises(ValueError):
        to_canonical("BTC/USDT:")


def test_malformed_pair_raises() -> None:
    with pytest.raises(ValueError):
        to_canonical("BTC/USDT/EXTRA")

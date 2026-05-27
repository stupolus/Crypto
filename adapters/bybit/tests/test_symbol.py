"""Symbol translator round-trip + edge cases."""

from __future__ import annotations

import pytest

from adapters.bybit.symbol import from_project_format, to_project_format


@pytest.mark.parametrize(
    "project,bybit",
    [
        ("BTC-USDT", "BTCUSDT"),
        ("ETH-USDT", "ETHUSDT"),
        ("DOGE-USDT", "DOGEUSDT"),
        ("ETH-USDC", "ETHUSDC"),
    ],
)
def test_roundtrip(project: str, bybit: str) -> None:
    assert from_project_format(project) == bybit
    assert to_project_format(bybit) == project


def test_to_project_idempotent_on_already_project_format() -> None:
    """Если уже в формате с дефисом — не трогаем."""
    assert to_project_format("BTC-USDT") == "BTC-USDT"


def test_to_project_unknown_quote_returns_as_is() -> None:
    """Если суффикс не из списка известных — возвращаем как есть.

    Это страховка от тихих ошибок: лучше вернуть необычный символ, чем
    угадать неверный split.
    """
    assert to_project_format("EXOTIC") == "EXOTIC"

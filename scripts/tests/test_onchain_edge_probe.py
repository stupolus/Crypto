"""Тесты parse_llama_stablecoin_chart (план 47, без сети)."""

from __future__ import annotations

from typing import Any

from scripts.onchain_edge_probe import parse_llama_stablecoin_chart


def test_parse_llama_basic_and_sort_and_skip_nulls() -> None:
    raw: list[dict[str, Any]] = [
        {"date": "200", "totalCirculatingUSD": {"peggedUSD": 2_000_000}},
        {"date": "100", "totalCirculatingUSD": {"peggedUSD": 1_000_000}},
        # Пропуски: нет totalCirculatingUSD → отбрасываем.
        {"date": "150"},
        # Пропуск: нет date.
        {"totalCirculatingUSD": {"peggedUSD": 999}},
        # peggedUSD=None — отбрасываем.
        {"date": "300", "totalCirculatingUSD": {"peggedUSD": None}},
    ]
    rows = parse_llama_stablecoin_chart(raw)
    assert rows == [(100_000, 1_000_000.0), (200_000, 2_000_000.0)]


def test_parse_llama_empty() -> None:
    assert parse_llama_stablecoin_chart([]) == []

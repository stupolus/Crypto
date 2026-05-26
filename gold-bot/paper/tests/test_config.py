"""Тесты конфига paper-runner'а."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from paper.config import PaperConfig, load_paper_config


def _yaml(body: str, tmp_path: Path) -> Path:
    p = tmp_path / "paper.yaml"
    p.write_text(body, encoding="utf-8")
    return p


def test_load_real_config_file() -> None:
    cfg = load_paper_config()
    assert cfg.exchange in {"bingx", "bybit"}
    assert cfg.symbols
    assert cfg.timeframe.endswith("m") or cfg.timeframe.endswith("h")
    assert cfg.starting_equity > 0
    assert cfg.taker_fee >= 0
    assert cfg.slippage_pct >= 0


def test_load_custom(tmp_path: Path) -> None:
    body = """
exchange: bingx
symbols: ["BTC/USDT:USDT"]
timeframe: 15m
starting_equity: "10000"
poll_interval_seconds: 30
close_grace_seconds: 5
taker_fee: "0.0005"
slippage_pct: "0.0005"
journal_path: "/tmp/x.sqlite"
heartbeat_interval_seconds: 60
"""
    cfg = load_paper_config(_yaml(body, tmp_path))
    assert cfg.exchange == "bingx"
    assert cfg.symbols == ["BTC/USDT:USDT"]
    assert cfg.starting_equity == Decimal("10000")
    assert cfg.poll_interval_seconds == 30


def test_rejects_unknown_field(tmp_path: Path) -> None:
    body = """
exchange: bingx
symbols: ["BTC/USDT:USDT"]
timeframe: 15m
starting_equity: "10000"
poll_interval_seconds: 30
close_grace_seconds: 5
taker_fee: "0.0005"
slippage_pct: "0.0005"
journal_path: "/tmp/x.sqlite"
heartbeat_interval_seconds: 60
unknown_field: 1
"""
    with pytest.raises(Exception):  # noqa: B017
        load_paper_config(_yaml(body, tmp_path))


def test_rejects_unsupported_exchange(tmp_path: Path) -> None:
    body = """
exchange: kraken
symbols: ["BTC/USDT:USDT"]
timeframe: 15m
starting_equity: "10000"
poll_interval_seconds: 30
close_grace_seconds: 5
taker_fee: "0.0005"
slippage_pct: "0.0005"
journal_path: "/tmp/x.sqlite"
heartbeat_interval_seconds: 60
"""
    with pytest.raises(Exception):  # noqa: B017
        load_paper_config(_yaml(body, tmp_path))


def test_paperconfig_frozen() -> None:
    cfg = PaperConfig(
        exchange="bingx",
        symbols=["BTC/USDT:USDT"],
        timeframe="15m",
        starting_equity=Decimal("10000"),
        poll_interval_seconds=30,
        close_grace_seconds=5,
        taker_fee=Decimal("0.0005"),
        slippage_pct=Decimal("0.0005"),
        journal_path="/tmp/x.sqlite",
        heartbeat_interval_seconds=60,
    )
    with pytest.raises(Exception):  # noqa: B017
        cfg.poll_interval_seconds = 1  # type: ignore[misc]

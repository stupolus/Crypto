"""Unit-тесты ``scripts.list_strategies``."""

from __future__ import annotations

import json

import pytest

from scripts.list_strategies import (
    _config_to_dict,
    collect_info,
    format_text,
    run,
)


def test_collect_info_returns_all_strategies() -> None:
    infos = collect_info()
    names = {info["name"] for info in infos}
    assert "btc_breakout" in names
    assert "us_session_breakout" in names
    assert "trend_ema_4h" in names


def test_collect_info_contains_meta_fields() -> None:
    infos = collect_info()
    for info in infos:
        if "error" in info:
            continue
        assert "symbol" in info
        assert "timeframe" in info
        assert "risk_tier" in info
        assert "config_fields" in info


def test_format_text_human_readable() -> None:
    infos = [
        {
            "name": "demo",
            "symbol": "BTC-USDT",
            "timeframe": "15m",
            "risk_tier": "B",
            "config_fields": {
                "atr_window": 14,
                "donchian_n": 20,
            },
        }
    ]
    text = format_text(infos)
    assert "Registered strategies" in text
    assert "demo" in text
    assert "BTC-USDT" in text
    assert "atr_window: 14" in text


def test_format_text_handles_error() -> None:
    infos = [{"name": "broken", "error": "ImportError: missing"}]
    text = format_text(infos)
    assert "✗ broken" in text
    assert "ImportError" in text


def test_config_to_dict_pydantic() -> None:
    from strategies.btc_breakout.config import get_default_config

    cfg = get_default_config()
    result = _config_to_dict(cfg)
    assert isinstance(result, dict)
    assert "symbol" in result
    assert result["symbol"] == "BTC-USDT"


def test_run_text_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    rc = run(as_json=False)
    assert rc == 0
    out = capsys.readouterr().out
    assert "Registered strategies" in out
    assert "btc_breakout" in out


def test_run_json_outputs_valid(capsys: pytest.CaptureFixture[str]) -> None:
    rc = run(as_json=True)
    assert rc == 0
    out = capsys.readouterr().out
    data = json.loads(out)  # должен парситься
    assert isinstance(data, list)
    assert any(item.get("name") == "btc_breakout" for item in data)

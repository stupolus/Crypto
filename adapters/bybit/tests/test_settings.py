"""Тесты BybitSettings: env-маршрутизация active_*, base URL, recv_window."""

from __future__ import annotations

import pytest

from adapters.bybit.settings import BybitSettings


def test_default_env_is_testnet() -> None:
    """По умолчанию env=testnet — нельзя случайно уйти в live."""
    s = BybitSettings(_env_file=None)
    assert s.env == "testnet"


def test_active_key_routes_by_env() -> None:
    s = BybitSettings(
        _env_file=None,
        env="testnet",
        testnet_api_key="t-key",
        testnet_api_secret="t-sec",
        live_api_key="L-key",
        live_api_secret="L-sec",
    )
    assert s.active_key == "t-key"
    assert s.active_secret == "t-sec"

    s_live = s.model_copy(update={"env": "live"})
    assert s_live.active_key == "L-key"
    assert s_live.active_secret == "L-sec"


def test_rest_base_url_routes_by_env() -> None:
    s = BybitSettings(_env_file=None, env="testnet")
    assert s.rest_base_url == "https://api-testnet.bybit.com"
    s2 = BybitSettings(_env_file=None, env="live")
    assert s2.rest_base_url == "https://api.bybit.com"


def test_has_credentials_requires_both() -> None:
    """Только key без secret — has_credentials = False."""
    s = BybitSettings(
        _env_file=None,
        env="testnet",
        testnet_api_key="k",
        # secret отсутствует
    )
    assert s.has_credentials() is False
    s2 = s.model_copy(update={"testnet_api_secret": "s"})
    assert s2.has_credentials() is True


def test_recv_window_bounds() -> None:
    """Жёсткие границы: 100..60000."""
    with pytest.raises(ValueError):
        BybitSettings(_env_file=None, recv_window_ms=50)
    with pytest.raises(ValueError):
        BybitSettings(_env_file=None, recv_window_ms=120_000)
    s = BybitSettings(_env_file=None, recv_window_ms=10_000)
    assert s.recv_window_ms == 10_000

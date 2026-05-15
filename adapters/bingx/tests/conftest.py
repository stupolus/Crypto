"""Общие фикстуры для тестов BingX-адаптера."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from adapters.bingx.config import BingXConfig, load_config

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))
    return data


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture(scope="session")
def cfg() -> BingXConfig:
    base = load_config()
    # Для тестов compensating-check проверка SL — без задержки и за 1 попытку,
    # чтобы юниты не висели на asyncio.sleep. Реальные значения проверяем
    # в integration-тестах.
    return base.model_copy(
        update={
            "place_order": base.place_order.model_copy(
                update={
                    "compensating_check_delay_ms": 0,
                    "compensating_check_attempts": 1,
                }
            )
        }
    )


@pytest.fixture
def server_time_payload() -> dict[str, Any]:
    return _load_fixture("server_time.json")


@pytest.fixture
def contracts_payload() -> dict[str, Any]:
    return _load_fixture("contracts.json")


@pytest.fixture
def ticker_payload() -> dict[str, Any]:
    return _load_fixture("ticker.json")


@pytest.fixture
def klines_payload() -> dict[str, Any]:
    return _load_fixture("klines.json")


@pytest.fixture
def rate_limit_payload() -> dict[str, Any]:
    return _load_fixture("error_rate_limit.json")

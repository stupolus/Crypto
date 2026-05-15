"""Unit-тесты конфига soft-reconcile (отложенная 0.E задача)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from adapters.bingx.config import BingXConfig, load_config


def test_soft_reconcile_enabled_in_default_config() -> None:
    """С 2026-05-12 включён в config.yaml (120s) для D3 demo + live.
    См. ветку claude/ws-resubscribe-retry-and-soft-reconcile."""
    cfg = load_config()
    assert cfg.user_data_stream.soft_reconcile_interval_s == 120.0


def test_soft_reconcile_negative_rejected() -> None:
    """Field validator ge=0 — отрицательные не принимаются."""
    base = load_config().model_dump()
    base["user_data_stream"]["soft_reconcile_interval_s"] = -1.0
    with pytest.raises(ValidationError):
        BingXConfig.model_validate(base)


def test_soft_reconcile_positive_accepted() -> None:
    base = load_config().model_dump()
    base["user_data_stream"]["soft_reconcile_interval_s"] = 60.0
    new = BingXConfig.model_validate(base)
    assert new.user_data_stream.soft_reconcile_interval_s == 60.0

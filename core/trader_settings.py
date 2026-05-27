"""Trader-specific settings (env-driven).

Hack B (план 01 §6j): clamp equity на shared VST-аккаунте.
Снимется с переходом на отдельный VST-аккаунт под трейдер-бота.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


class TraderEquitySettings(BaseSettings):
    """``TRADER_EQUITY_BASELINE`` из .env (gitignored).

    Если задан — equity для RiskEngine/просадки клампится к этому
    числу (фиксированный депозит трейдера), чтобы чужие позиции на
    том же VST-аккаунте не контаминировали расчёты.
    """

    model_config = SettingsConfigDict(
        env_prefix="TRADER_",
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    equity_baseline: Decimal | None = Field(default=None, gt=0)

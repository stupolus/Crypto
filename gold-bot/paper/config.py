"""Конфиг paper-runner'а: pydantic-модель + загрузка из YAML.

Числа риска сюда не дублируются — они в config/risk.yaml. Здесь только
параметры самого раннера (символы, таймфрейм, период опроса, cost-модель
для виртуальных fills, путь к SQLite-журналу).
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

_DEFAULT_PATH = Path(__file__).resolve().parent.parent / "config" / "paper.yaml"


class PaperConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exchange: str = Field(pattern=r"^(bingx|bybit)$")
    symbols: list[str] = Field(min_length=1)
    timeframe: str
    starting_equity: Decimal
    poll_interval_seconds: int = Field(ge=5, le=600)
    close_grace_seconds: int = Field(ge=0, le=300)
    taker_fee: Decimal = Field(ge=0)
    slippage_pct: Decimal = Field(ge=0)
    journal_path: str
    heartbeat_interval_seconds: int = Field(ge=30, le=3600)


def load_paper_config(path: Path | str | None = None) -> PaperConfig:
    target = Path(path) if path is not None else _DEFAULT_PATH
    with open(target, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return PaperConfig.model_validate(data)

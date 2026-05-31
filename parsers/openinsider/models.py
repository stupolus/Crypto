"""Pydantic-модели для OpenInsider парсера.

Колонки OpenInsider table `class="tinytable"`:
0  X (filing marker — обычно 'M' для multiple form)
1  Filing date+time (YYYY-MM-DD HH:MM:SS)
2  Trade date (YYYY-MM-DD)
3  Ticker (с onmouseover-tooltip — очищается)
4  Company name
5  Industry
6  Ins (insiders count — для cluster pages)
7  Trade type ('P - Purchase' / 'S - Sale' / ...)
8  Price ($X.XX)
9  Qty (signed: +X / -X)
10 Owned (после сделки)
11 ΔOwn (signed %: +/-X%)
12 Value (signed $: +/-$X)
13 1d fwd return (% или пусто)
14 1w fwd return
15 1m fwd return
16 6m fwd return
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# OpenInsider trade-type коды (буква перед « - » в колонке Trade Type).
# P = Purchase (open-market buy), S = Sale, A = Acquisition (не market buy),
# D = Disposition, F = Tax/insider-related, M = Option exercise/conversion,
# G = Gift, J = Other.
TradeType = Literal["P", "S", "A", "D", "F", "M", "G", "J"]


class InsiderTransaction(BaseModel):
    """Одна insider transaction из OpenInsider таблицы."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    filing_marker: str = Field(default="", description="X-маркер (M/A/...)")
    filing_datetime: datetime
    trade_date: date
    ticker: str
    company_name: str
    industry: str = ""
    insiders_count: int = Field(default=1, description="Кол-во insiders в одной filing")
    trade_type: TradeType
    trade_type_raw: str = Field(description="Сырая строка 'P - Purchase'")
    price: Decimal | None = None
    qty: int = Field(description="Подписанное кол-во акций (положительное для buy)")
    owned_after: int | None = None
    delta_own_pct: Decimal | None = Field(
        default=None, description="Подписанный % изменения holdings"
    )
    value_usd: Decimal | None = Field(
        default=None, description="Подписанная стоимость сделки в USD"
    )
    fwd_return_1d: Decimal | None = None
    fwd_return_1w: Decimal | None = None
    fwd_return_1m: Decimal | None = None
    fwd_return_6m: Decimal | None = None

"""Тесты OpenInsider HTML парсера на реальном фикстуре (snapshot 2026-05-31).

Фикстура — урезанные первые 10 строк страницы `latest-cluster-buys`
сохранены в `fixtures/latest_cluster_buys.html`. Это реальная структура
OpenInsider, не выдумка.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from parsers.openinsider.models import InsiderTransaction
from parsers.openinsider.parser import (
    _parse_number,
    _parse_trade_type,
    _strip_html,
    parse_transactions_table,
)

_FIXTURE = Path(__file__).parent / "fixtures" / "latest_cluster_buys.html"


@pytest.fixture
def fixture_html() -> str:
    return _FIXTURE.read_text(encoding="utf-8")


# ─── parse_transactions_table ──────────────────────────────────────────────


def test_parses_at_least_one_row(fixture_html: str) -> None:
    """Сниппет ≥ 10 строк = должны достать минимум 5 транзакций."""
    txs = parse_transactions_table(fixture_html)
    assert len(txs) >= 5


def test_first_row_has_expected_shape(fixture_html: str) -> None:
    """Первая строка фикстуры (snapshot 2026-05-31): WHF Whitehorse Finance."""
    txs = parse_transactions_table(fixture_html)
    assert len(txs) >= 1
    tx = txs[0]
    assert isinstance(tx, InsiderTransaction)
    assert tx.ticker == "WHF"
    assert tx.company_name == "Whitehorse Finance, Inc."
    assert tx.trade_type == "P"  # Purchase
    assert tx.trade_type_raw.startswith("P -")
    assert tx.price == Decimal("6.90")
    assert tx.qty == 108258
    assert tx.value_usd == Decimal("746650")
    assert tx.filing_datetime == datetime(2026, 5, 29, 18, 44, 28)
    assert tx.trade_date == date(2026, 5, 29)
    assert tx.insiders_count == 2  # cluster-buy с двумя insiders


def test_all_rows_have_positive_qty_for_purchases(fixture_html: str) -> None:
    """latest-cluster-buys = только Purchases → qty > 0 для всех."""
    txs = parse_transactions_table(fixture_html)
    purchase_txs = [t for t in txs if t.trade_type == "P"]
    assert len(purchase_txs) >= 5
    for tx in purchase_txs:
        assert tx.qty > 0, f"purchase with non-positive qty: {tx}"


def test_empty_html_returns_empty_list() -> None:
    assert parse_transactions_table("") == []
    assert parse_transactions_table("<html><body>no table here</body></html>") == []


def test_empty_table_returns_empty_list() -> None:
    """Таблица только с headers, без data-строк → []."""
    html = """<html><body>
        <table class="tinytable">
            <tr><th>only</th><th>headers</th></tr>
        </table>
    </body></html>"""
    assert parse_transactions_table(html) == []


# ─── helper тесты ──────────────────────────────────────────────────────────


def test_strip_html_removes_tags_and_normalizes_whitespace() -> None:
    assert _strip_html("<a href='x'>Hello</a>  World") == "Hello World"
    assert _strip_html("Pure text") == "Pure text"
    assert _strip_html("") == ""


def test_parse_number_handles_signed_decimal_dollar_percent() -> None:
    assert _parse_number("+108,258") == Decimal("108258")
    assert _parse_number("-50.5") == Decimal("-50.5")
    assert _parse_number("$6.90") == Decimal("6.90")
    assert _parse_number("+$746,650") == Decimal("746650")
    assert _parse_number("+39%") == Decimal("39")
    assert _parse_number("") is None
    assert _parse_number("   ") is None
    assert _parse_number("not-a-number") is None


def test_parse_trade_type_recognizes_known_codes() -> None:
    code, raw = _parse_trade_type("P - Purchase")
    assert code == "P"
    assert raw == "P - Purchase"

    code, _ = _parse_trade_type("S - Sale")
    assert code == "S"

    code, _ = _parse_trade_type("A - Grant")
    assert code == "A"


def test_parse_trade_type_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="unknown trade type"):
        _parse_trade_type("Z - Mystery")
    with pytest.raises(ValueError, match="unparseable"):
        _parse_trade_type("no dash here")


# ─── модель ──────────────────────────────────────────────────────────────


def test_insider_transaction_is_frozen() -> None:
    """Модель неизменяема — защита от случайной мутации."""
    tx = InsiderTransaction(
        filing_datetime=datetime(2026, 1, 1, 12, 0, 0),
        trade_date=date(2026, 1, 1),
        ticker="TEST",
        company_name="Test Inc.",
        trade_type="P",
        trade_type_raw="P - Purchase",
        qty=100,
    )
    with pytest.raises(ValueError):
        tx.ticker = "OTHER"  # type: ignore[misc]

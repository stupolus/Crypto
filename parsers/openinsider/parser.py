"""OpenInsider HTML → list[InsiderTransaction].

Стратегия парсинга: regex-based, без BeautifulSoup (минимум зависимостей).
Структура `<table class="tinytable">` стабильная (проверено на live).

Quirks:
- Ticker имеет onmouseover tooltip: `<a ... onmouseover="Tip('...')">TSLA</a>`.
  Нужно достать только текст после `>` финального тега.
- Числа со знаком: `+108,258` (qty), `+$746,650` (value), `+39%` (delta).
- Forward-returns могут отсутствовать (пустая ячейка) для свежих сделок.
- HTML-entity `&Delta;` в headers — игнорируем (мы парсим по позиции).
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser

from parsers.openinsider.models import InsiderTransaction, TradeType

_TABLE_RE = re.compile(
    r'<table[^>]*class="tinytable"[^>]*>(.*?)</table>',
    re.DOTALL,
)
_ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.DOTALL)
_CELL_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.DOTALL)
# Trade-type код = первая буква до « - »:  'P - Purchase' → 'P'.
_TRADE_TYPE_RE = re.compile(r"^\s*([A-Z])\s*-\s*", re.IGNORECASE)

_VALID_TRADE_TYPES: frozenset[str] = frozenset({"P", "S", "A", "D", "F", "M", "G", "J"})


class _TextExtractor(HTMLParser):
    """Stdlib HTML-парсер, выдёргивающий только текстовые узлы.

    Используется вместо regex-tag-stripping потому что OpenInsider
    ticker-ячейки содержат `<a onmouseover="Tip('...', DELAY, 1)"...>`
    с апострофами и `>` внутри JS-атрибута, что ломает наивный regex.
    """

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def text(self) -> str:
        return " ".join(" ".join(self._parts).split())


def _strip_html(s: str) -> str:
    """Убрать HTML-теги, normalize whitespace.

    Bullet-proof через stdlib `html.parser` — корректно обрабатывает
    атрибуты с произвольными символами (включая `>` внутри `onmouseover`).
    """
    p = _TextExtractor()
    p.feed(s)
    p.close()
    return p.text()


def _parse_number(raw: str, allow_signed: bool = True) -> Decimal | None:
    """Распарсить число формата '+108,258' / '$6.90' / '+$746,650' / '+39%' / ''.

    Возвращает None для пустой ячейки.
    """
    cleaned = raw.strip().replace(",", "").replace("$", "").replace("%", "")
    if not cleaned:
        return None
    if not allow_signed:
        cleaned = cleaned.lstrip("+")
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def _parse_int(raw: str) -> int | None:
    """Целое со знаком: '+108,258' → 108258."""
    val = _parse_number(raw)
    return int(val) if val is not None else None


def _parse_trade_type(raw: str) -> tuple[TradeType, str]:
    """'P - Purchase' → ('P', 'P - Purchase'). Невалидное → ValueError."""
    cleaned = _strip_html(raw)
    m = _TRADE_TYPE_RE.match(cleaned)
    if not m:
        raise ValueError(f"unparseable trade type: {cleaned!r}")
    code = m.group(1).upper()
    if code not in _VALID_TRADE_TYPES:
        raise ValueError(f"unknown trade type code: {code!r} (raw={cleaned!r})")
    return code, cleaned  # type: ignore[return-value]


def parse_transactions_table(html: str) -> list[InsiderTransaction]:
    """Распарсить HTML страницы OpenInsider в список транзакций.

    Возвращает пустой список если таблица не найдена или пустая
    (а не raise — caller сам решает, что делать).
    """
    m = _TABLE_RE.search(html)
    if not m:
        return []

    rows = _ROW_RE.findall(m.group(1))
    if len(rows) <= 1:
        return []  # только header или пусто

    transactions: list[InsiderTransaction] = []
    # Skipping headers row (index 0).
    for row_html in rows[1:]:
        cells = _CELL_RE.findall(row_html)
        if len(cells) < 13:
            # OpenInsider всегда 17 колонок; меньше = битая строка.
            continue
        try:
            tx = _parse_row(cells)
        except (ValueError, IndexError) as e:
            # Логировать и продолжать — одна битая строка не должна
            # ронять весь fetch.
            import logging

            logging.getLogger(__name__).warning(
                "skip malformed openinsider row: %s | row=%r", e, row_html[:200]
            )
            continue
        transactions.append(tx)

    return transactions


def _parse_row(cells: list[str]) -> InsiderTransaction:
    """Один <tr> → InsiderTransaction. Очищает HTML, кастует типы."""
    filing_marker = _strip_html(cells[0])
    filing_dt_str = _strip_html(cells[1])
    trade_date_str = _strip_html(cells[2])
    ticker = _strip_html(cells[3])
    company = _strip_html(cells[4])
    industry = _strip_html(cells[5])
    insiders_raw = _strip_html(cells[6])
    trade_type, trade_type_raw = _parse_trade_type(cells[7])
    price = _parse_number(_strip_html(cells[8]))
    qty = _parse_int(_strip_html(cells[9]))
    owned = _parse_int(_strip_html(cells[10]))
    delta_own = _parse_number(_strip_html(cells[11]))
    value = _parse_number(_strip_html(cells[12]))

    fwd_1d = _parse_number(_strip_html(cells[13])) if len(cells) > 13 else None
    fwd_1w = _parse_number(_strip_html(cells[14])) if len(cells) > 14 else None
    fwd_1m = _parse_number(_strip_html(cells[15])) if len(cells) > 15 else None
    fwd_6m = _parse_number(_strip_html(cells[16])) if len(cells) > 16 else None

    if qty is None:
        raise ValueError("missing quantity")

    return InsiderTransaction(
        filing_marker=filing_marker,
        filing_datetime=datetime.fromisoformat(filing_dt_str),
        trade_date=date.fromisoformat(trade_date_str),
        ticker=ticker,
        company_name=company,
        industry=industry,
        insiders_count=int(insiders_raw) if insiders_raw.isdigit() else 1,
        trade_type=trade_type,
        trade_type_raw=trade_type_raw,
        price=price,
        qty=qty,
        owned_after=owned,
        delta_own_pct=delta_own,
        value_usd=value,
        fwd_return_1d=fwd_1d,
        fwd_return_1w=fwd_1w,
        fwd_return_1m=fwd_1m,
        fwd_return_6m=fwd_6m,
    )

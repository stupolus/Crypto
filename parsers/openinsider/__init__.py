"""OpenInsider (http://openinsider.com) парсер.

Источник Form 4 (SEC insider trading) данных в готовом виде —
HTML-агрегатор без необходимости крафта парсера EDGAR.

План 48 (фазы 48.0 литобзор → 48.1 парсер). Edge ожидается скромный
(4–7%/год по литературе), использование — как overlay-фильтр для
GTAA-equity-legs, не standalone стратегия. См.
`retro/2026-05-31-план-48.0-литобзор.md`.

⚠️ В live до фазы 48.6 (cost-aware backtest пройден + явное «да»).
"""

from parsers.openinsider.models import InsiderTransaction, TradeType
from parsers.openinsider.parser import parse_transactions_table

__all__ = [
    "InsiderTransaction",
    "TradeType",
    "parse_transactions_table",
]

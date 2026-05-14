"""Макро-данные для Layer 3 Macro Analyst (план #17 §3.5).

Источники (все бесплатные):
- ``yfinance_adapter`` — DXY, VIX, S&P, NDX, gold, oil, 10Y yield через Yahoo
- ``fred_adapter`` — Fed Funds Rate, CPI, unemployment через FRED API
- (опционально) ``cme_adapter`` — futures cot reports

Все adapter'ы возвращают ``MacroSnapshot`` — pydantic-модель с TS+метриками
для подачи в Macro Analyst.
"""

from parsers.macro.context_builder import MacroContextBuilder
from parsers.macro.fred_adapter import FREDAdapter, FREDFetcher, FREDSnapshot
from parsers.macro.models import MacroSnapshot, YfinanceQuote
from parsers.macro.yfinance_adapter import YahooFetcher, YfinanceAdapter

__all__ = [
    "FREDAdapter",
    "FREDFetcher",
    "FREDSnapshot",
    "MacroContextBuilder",
    "MacroSnapshot",
    "YahooFetcher",
    "YfinanceAdapter",
    "YfinanceQuote",
]

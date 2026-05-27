"""Symbol translator: проектный формат ``BTC-USDT`` ↔ Bybit ``BTCUSDT``.

Проектная конвенция (CLAUDE.md, AGENTS.md): везде в стратегиях/risk/etc.
символы хранятся в формате ``<BASE>-<QUOTE>`` с дефисом. Адаптер
конвертирует на лету, в самой нижней точке (HTTP-вызов) — стратегии
ничего о Bybit-нотации не знают.

NB: Bybit V5 для USDT-перпов всегда требует ``category=linear``.
Этот модуль про **формат символа**, не про категорию.
"""

from __future__ import annotations


def to_project_format(bybit_symbol: str) -> str:
    """``BTCUSDT`` → ``BTC-USDT``.

    Эвристика: ищем правый суффикс ``USDT``/``USDC``/``BTC``/``ETH``
    (стандартные quotes на Bybit), остальное считаем base. Если ничего
    не подошло — возвращаем как есть (страховка для нестандартных
    символов; тесты ловят).
    """
    if "-" in bybit_symbol:
        # Уже в проектном формате — не трогаем.
        return bybit_symbol
    for quote in ("USDT", "USDC", "BTC", "ETH"):
        if bybit_symbol.endswith(quote) and len(bybit_symbol) > len(quote):
            base = bybit_symbol[: -len(quote)]
            return f"{base}-{quote}"
    return bybit_symbol


def from_project_format(project_symbol: str) -> str:
    """``BTC-USDT`` → ``BTCUSDT``. Просто убираем дефис."""
    return project_symbol.replace("-", "")

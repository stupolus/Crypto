"""Нормализация символов инструментов к канонической форме.

Разные биржи и источники называют один и тот же перп по-разному:
`BTC-USDT`, `BTCUSDT`, `BTC/USDT`, `BTC/USDT:USDT`. Внутри gold-bot работаем
с единой канонической формой ccxt для linear-перпов: `BASE/QUOTE:SETTLE`,
например `BTC/USDT:USDT`.
"""

from __future__ import annotations

# Порядок важен: более длинные котировки проверяются раньше (USDT раньше USD),
# иначе `BTCUSDT` ошибочно разберётся как BTC + USD + лишнее «T».
KNOWN_QUOTES: tuple[str, ...] = ("USDT", "USDC", "USD")


def _split_concatenated(s: str) -> tuple[str, str]:
    for quote in KNOWN_QUOTES:
        if s.endswith(quote) and len(s) > len(quote):
            return s[: -len(quote)], quote
    raise ValueError(f"не разобрать символ без разделителя: {s!r}")


def to_canonical(symbol: str, *, settle: str | None = None) -> str:
    """Привести символ к канонической форме `BASE/QUOTE:SETTLE`.

    settle по умолчанию равен котировке (linear USDT-перп). Явный аргумент
    settle имеет приоритет над settle, извлечённым из самого символа.
    """
    s = symbol.strip().upper()
    if not s:
        raise ValueError("пустой символ")

    explicit_settle: str | None = None
    if ":" in s:
        s, explicit_settle = s.split(":", 1)
        if not explicit_settle:
            raise ValueError(f"пустой settle в символе: {symbol!r}")

    s = s.replace("-", "/")
    if "/" in s:
        parts = s.split("/")
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise ValueError(f"не разобрать символ: {symbol!r}")
        base, quote = parts
    else:
        base, quote = _split_concatenated(s)

    final_settle = settle.strip().upper() if settle else (explicit_settle or quote)
    return f"{base}/{quote}:{final_settle}"

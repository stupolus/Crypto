"""Шаг 0: разведка реально доступных инструментов на BingX и Bybit.

Запускать на VPS (где есть сеть и, для приватной части, ключи). Из dev-контейнера
обычно недоступно — сеть до бирж закрыта политикой окружения.

Публичная часть (load_markets) ключей не требует и показывает, какие перпы
вообще листятся. Доступность КОНКРЕТНОМУ аккаунту с учётом KYC/юрисдикции
(резидент Испании/ЕЭЗ) публичный эндпоинт НЕ показывает — это проверяется
только авторизованным запросом и/или вручную в UI биржи.

Запуск из каталога gold-bot:
    python -m scripts.recon_universe                 # таблица в stdout
    python -m scripts.recon_universe --md FILE.md     # + сохранить markdown
"""

from __future__ import annotations

import argparse
import asyncio
from typing import Any

import ccxt.async_support as ccxt_async

# Что ищем (база инструмента). Тикеры не выдумываем — только матчим то, что листится.
_GOLD = ("XAU", "PAXG", "XAUT", "GOLD")
_SILVER = ("XAG", "SILVER")
_EQUITY = ("TSLA", "NVDA", "AAPL", "META", "MSFT", "GOOGL", "AMZN", "AMD", "NFLX", "COIN")


def _classify(base: str) -> str | None:
    b = base.upper()
    if any(k in b for k in _GOLD):
        return "GOLD"
    if any(k in b for k in _SILVER):
        return "SILVER"
    if b in _EQUITY:
        return "EQUITY"
    return None


def _row(cls: str, symbol: str, m: dict[str, Any]) -> dict[str, Any]:
    limits = m.get("limits", {}) or {}
    precision = m.get("precision", {}) or {}
    return {
        "class": cls,
        "symbol": symbol,
        "type": m.get("type"),
        "linear": m.get("linear"),
        "active": m.get("active"),
        "maker": m.get("maker"),
        "taker": m.get("taker"),
        "lev_max": (limits.get("leverage", {}) or {}).get("max"),
        "amt_min": (limits.get("amount", {}) or {}).get("min"),
        "price_prec": precision.get("price"),
    }


async def _scan(exchange_name: str, factory: Any) -> tuple[str, list[dict[str, Any]]]:
    client = factory({"enableRateLimit": True, "options": {"defaultType": "swap"}})
    try:
        markets: dict[str, Any] = await client.load_markets()
    except Exception as exc:  # сеть/доступность — логируем, не падаем
        return f"ERROR: {type(exc).__name__}: {str(exc)[:160]}", []
    finally:
        await client.close()

    rows: list[dict[str, Any]] = []
    for symbol, m in markets.items():
        cls = _classify(m.get("base") or "")
        if cls is None:
            continue
        if not (m.get("swap") or m.get("future") or m.get("contract")):
            continue
        rows.append(_row(cls, symbol, m))
    rows.sort(key=lambda r: (r["class"], r["symbol"]))
    return f"OK (всего инструментов: {len(markets)})", rows


def _render_md(results: dict[str, tuple[str, list[dict[str, Any]]]]) -> str:
    lines = ["# Шаг 0 — разведка инструментов (gold/silver/equity перпы)", ""]
    for exchange_name, (status, rows) in results.items():
        lines.append(f"## {exchange_name}: {status}")
        lines.append("")
        if not rows:
            lines.append("Совпадений нет (или сеть недоступна — см. статус).")
            lines.append("")
            continue
        lines.append(
            "| класс | symbol | type | active | linear | taker | maker | lev_max | amt_min | price_prec |"
        )
        lines.append("|---|---|---|---|---|---|---|---|---|---|")
        for r in rows:
            lines.append(
                f"| {r['class']} | {r['symbol']} | {r['type']} | {r['active']} | {r['linear']} | "
                f"{r['taker']} | {r['maker']} | {r['lev_max']} | {r['amt_min']} | {r['price_prec']} |"
            )
        lines.append("")
    lines.append(
        "> Публичный листинг ≠ доступность вашему аккаунту. KYC/юрисдикция (Испания/ЕЭЗ) "
        "проверяется авторизованным запросом или в UI биржи."
    )
    return "\n".join(lines)


async def _run(md_path: str | None) -> None:
    results: dict[str, tuple[str, list[dict[str, Any]]]] = {}
    for exchange_name, factory in (("bingx", ccxt_async.bingx), ("bybit", ccxt_async.bybit)):
        results[exchange_name] = await _scan(exchange_name, factory)
    md = _render_md(results)
    print(md)
    if md_path:
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md + "\n")
        print(f"\n[saved] {md_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Разведка инструментов BingX/Bybit (Шаг 0)")
    parser.add_argument("--md", default=None, help="путь для сохранения markdown-таблицы")
    args = parser.parse_args()
    asyncio.run(_run(args.md))


if __name__ == "__main__":
    main()

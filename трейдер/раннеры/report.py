"""Дневной отчёт бота «трейдер»: статус, сделки, equity, просадка.

Источники РЕАЛЬНЫХ данных (не outcomes-слой llm_runner):
- ``трейдер/журнал/journal.sqlite`` (OrderJournal) — ордера по статусам.
- BingX VST live: equity, realised_profit, открытые позиции.
- HWM-файл ``трейдер/журнал/hwm.txt`` — пик equity для расчёта просадки
  между запусками.

Запуск (из корня репо, venv):
    python -m трейдер.раннеры.report                 # в stdout
    python -m трейдер.раннеры.report --telegram       # + в Telegram

Telegram включается только если в .env есть TELEGRAM_BOT_TOKEN/CHAT_ID;
иначе тихий фолбэк в stdout (бот не падает).
"""

from __future__ import annotations

import argparse
import asyncio
import sqlite3
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast

_ROOT = Path(__file__).resolve().parents[2]
# Запуск как `python трейдер/раннеры/report.py` из корня репо: добавим
# корень в sys.path, чтобы lazy-импорты core/adapters резолвились.
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_JOURNAL = _ROOT / "трейдер/журнал/journal.sqlite"
_HWM = _ROOT / "трейдер/журнал/hwm.txt"
_HEARTBEAT = _ROOT / "трейдер/журнал/heartbeat"


def _heartbeat_age_min() -> float | None:
    """Возраст heartbeat в минутах (живость раннера). None — нет файла."""
    if not _HEARTBEAT.exists():
        return None
    age_s = datetime.now(UTC).timestamp() - _HEARTBEAT.stat().st_mtime
    return round(age_s / 60, 1)


def _journal_stats(db_path: Path) -> dict[str, object]:
    if not db_path.exists():
        return {"exists": False}
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        by_status = {
            r["status"]: r["n"]
            for r in con.execute("SELECT status, COUNT(*) n FROM orders GROUP BY status")
        }
        by_side = {
            r["side"]: r["n"]
            for r in con.execute("SELECT side, COUNT(*) n FROM orders GROUP BY side")
        }
        total = con.execute("SELECT COUNT(*) n FROM orders").fetchone()["n"]
        last24 = con.execute(
            "SELECT COUNT(*) n FROM orders WHERE updated_at_ms >= ?",
            (int((datetime.now(UTC).timestamp() - 86400) * 1000),),
        ).fetchone()["n"]
        failures = [
            dict(r)
            for r in con.execute(
                "SELECT symbol, side, failure_reason, updated_at_ms FROM orders "
                "WHERE status='failed' ORDER BY updated_at_ms DESC LIMIT 5"
            )
        ]
    finally:
        con.close()
    return {
        "exists": True,
        "total": total,
        "last24": last24,
        "by_status": by_status,
        "by_side": by_side,
        "failures": failures,
    }


async def _bingx_snapshot(symbol: str) -> dict[str, object]:
    """Снимок BingX. Баланс и позиции — РАЗДЕЛЬНО: троттл эндпоинта
    позиций (BingX 100410) не должен скрывать equity.
    """
    try:
        from adapters.bingx.client import BingXClient
        from adapters.bingx.private import PrivateAPI
        from adapters.bingx.settings import BingXSettings

        settings = BingXSettings()
        async with BingXClient(settings=settings) as client:
            api = PrivateAPI(client)
            out: dict[str, object] = {"ok": True, "env": settings.env}
            # Баланс (главное — equity).
            try:
                balances = await api.get_balance()
                bal = next((b for b in balances if b.asset in ("VST", "USDT")), None)
                out["equity"] = bal.equity if bal else None
                out["realised"] = bal.realised_profit if bal else None
                out["unrealised"] = bal.unrealized_profit if bal else None
            except Exception as e:
                out["ok"] = False
                out["error"] = f"balance: {type(e).__name__}: {e}"
            # Позиции (best-effort: троттл/ошибка не валит equity).
            try:
                positions = await api.get_positions(symbol=symbol)
                out["open_positions"] = [
                    {
                        "symbol": p.symbol,
                        "amount": str(p.position_amount),
                        "entry": str(p.average_price),
                        "upnl": str(p.unrealized_profit),
                    }
                    for p in positions
                    if p.position_amount != 0
                ]
            except Exception as e:
                out["positions_error"] = f"{type(e).__name__}: {e}"
            return out
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def _drawdown(equity: Decimal | None) -> dict[str, object]:
    if equity is None:
        return {}
    hwm = equity
    if _HWM.exists():
        try:
            hwm = max(Decimal(_HWM.read_text().strip()), equity)
        except Exception:
            hwm = equity
    _HWM.parent.mkdir(parents=True, exist_ok=True)
    _HWM.write_text(str(hwm))
    dd = (equity - hwm) / hwm * 100 if hwm > 0 else Decimal("0")
    return {"hwm": hwm, "drawdown_pct": dd}


def _render(symbol: str, j: dict[str, object], b: dict[str, object], dd: dict[str, object]) -> str:
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"📊 Трейдер-демо — {now}", f"Символ: {symbol}"]
    hb = _heartbeat_age_min()
    if hb is None:
        lines.append("Живость: ⚠️ heartbeat не найден (раннер не запускался?)")
    elif hb <= 40:  # 6h-бар + запас; touch каждые 30с
        lines.append(f"Живость: ✅ heartbeat {hb} мин назад")
    else:
        lines.append(f"Живость: ⚠️ heartbeat {hb} мин назад (раннер мог зависнуть)")
    if b.get("ok"):
        lines += [
            f"Контур: BingX {b.get('env')} · equity={b.get('equity')} VST",
            f"Realised P&L: {b.get('realised')} · uPnL: {b.get('unrealised')}",
        ]
        if dd.get("hwm") is not None:
            lines.append(f"Просадка от пика: {dd['drawdown_pct']:.2f}% (HWM {dd['hwm']})")
        if b.get("positions_error"):
            lines.append(f"Открытых позиций: н/д (BingX троттл: {b['positions_error']})")
        else:
            ops = cast("list[dict[str, str]]", b.get("open_positions") or [])
            lines.append(
                "Открытых позиций: "
                + (
                    ", ".join(f"{o['symbol']} {o['amount']} (uPnL {o['upnl']})" for o in ops)
                    if ops
                    else "нет"
                )
            )
    else:
        lines.append(f"⚠️ BingX недоступен: {b.get('error')}")
    if j.get("exists"):
        lines += [
            f"Ордеров всего: {j['total']} · за 24ч: {j['last24']}",
            f"По статусам: {j['by_status']}",
            f"По стороне: {j['by_side']}",
        ]
        failures = cast("list[object]", j.get("failures") or [])
        if failures:
            lines.append(f"⚠️ Последние ошибки ордеров: {len(failures)}")
        if j.get("total") == 0:
            lines.append(
                "0 сделок — ОЖИДАЕМО: liquidation_reversal редкая (в бэктесте "
                "единицы сделок). Тишина ≠ сбой, если живость ✅. См. DEMO_CRITERIA §1."
            )
    else:
        lines.append(
            "Журнал пуст (раннер ещё не писал ордера) — ожидаемо для редкой "
            "стратегии; ориентир на живость выше."
        )
    lines.append("\n(demo — не доказательство эджа; см. трейдер/DEMO_CRITERIA.md)")
    return "\n".join(lines)


async def _send_telegram(text: str) -> bool:
    from core.alerts.channels import TelegramAlerter
    from core.alerts.settings import TelegramSettings

    s = TelegramSettings()
    if not s.configured:
        return False
    assert s.bot_token is not None and s.chat_id is not None
    await TelegramAlerter(bot_token=s.bot_token, chat_id=s.chat_id).send_info(text)
    return True


async def _main_async(symbol: str, to_telegram: bool) -> None:
    j = _journal_stats(_JOURNAL)
    b = await _bingx_snapshot(symbol)
    dd = _drawdown(b.get("equity") if b.get("ok") else None)  # type: ignore[arg-type]
    text = _render(symbol, j, b, dd)
    print(text)
    if to_telegram:
        sent = await _send_telegram(text)
        if not sent:
            print("\n[telegram пропущен: TELEGRAM_* не заданы в .env]")


def main() -> None:
    parser = argparse.ArgumentParser(description="Дневной отчёт бота «трейдер»")
    parser.add_argument("--symbol", default="BTC-USDT")
    parser.add_argument("--telegram", action="store_true", help="Отправить отчёт в Telegram")
    args = parser.parse_args()
    asyncio.run(_main_async(args.symbol, args.telegram))


if __name__ == "__main__":
    main()

"""Ежедневный отчёт по demo GTAA-4 на BingX VST (план 47.3, наблюдение).

Читает ops/gtaa_vst.jsonl + state, опрашивает живые позиции на VST,
шлёт сводку в Telegram (или stdout без ключа). Запускается своим
systemd-таймером ПОСЛЕ исполнителя. Только чтение — ордеров не ставит.

Сводка: сработал ли таймер за 24ч (heartbeat), текущая аллокация
по 4 перпам, дата последнего ребаланса, ошибки за 24ч, статус HALT.
Цель — аудит ИСПОЛНЕНИЯ (DEMO_CRITERIA, план 47), не PnL.
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from adapters.bingx.client import BingXClient
from adapters.bingx.private import PrivateAPI
from adapters.bingx.settings import BingXSettings
from scripts.gtaa_vst_executor import _ASSETS, _HALT, _LOG, _STATE, _aclose


def _read_log_since(since_ts: int) -> list[dict[str, Any]]:
    """Строки jsonl с ts >= since_ts (битые строки пропускаем)."""
    if not _LOG.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in _LOG.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and int(row.get("ts", 0)) >= since_ts:
            out.append(row)
    return out


def build_report(
    now: datetime,
    fired_24h: int,
    last_eom: str | None,
    halted: bool,
    errors_24h: list[dict[str, Any]],
    positions: dict[str, Decimal],
    equity: Decimal | None,
) -> str:
    """Чистая. Текст отчёта из уже собранных фактов (тестируемо без сети)."""
    lines: list[str] = [f"GTAA-VST daily {now.strftime('%Y-%m-%d %H:%M')}Z"]
    hb = "OK" if fired_24h > 0 else "НЕТ СРАБАТЫВАНИЙ"
    lines.append(f"timer: {hb} ({fired_24h} прогонов/24ч)")
    if halted:
        lines.append("⚠️ HALT активен (ops/gtaa_HALT) — ордеров нет")
    lines.append(f"last_rebalance_eom: {last_eom or '—'}")
    if equity is not None:
        lines.append(f"equity: {equity}")
    if positions:
        alloc = ", ".join(
            f"{lbl}={'ON ' + str(q) if q != 0 else 'cash'}" for lbl, q in positions.items()
        )
        lines.append(f"alloc: {alloc}")
    else:
        lines.append("alloc: позиции не получены (BingX недоступен)")
    if errors_24h:
        lines.append(f"❌ ошибок/24ч: {len(errors_24h)}")
        for e in errors_24h[:4]:
            lines.append(f"  - {e.get('label', '?')}: {e.get('err', e.get('reason'))}")
    else:
        lines.append("ошибок/24ч: 0")
    return "\n".join(lines)


async def _run() -> None:
    from core.alerts.factory import build_alerter

    s = BingXSettings()
    now = datetime.now(tz=UTC)
    since = int(time.time()) - 86_400
    rows = _read_log_since(since)
    fired_24h = sum(1 for r in rows if r.get("action") == "fired")
    errors_24h = [r for r in rows if r.get("status") == "error" or r.get("action") == "skip"]
    state = json.loads(_STATE.read_text()) if _STATE.exists() else {}
    last_eom = state.get("last_rebalance_eom")

    positions: dict[str, Decimal] = {}
    equity: Decimal | None = None
    if s.env == "vst":
        try:
            async with BingXClient(settings=s) as c:
                api = PrivateAPI(c)
                bal = await api.get_balance()
                equity = next(
                    (Decimal(str(b.equity)) for b in bal if b.asset in ("USDT", "VST")),
                    Decimal(str(bal[0].equity)) if bal else None,
                )
                for a in _ASSETS:
                    poss = await api.get_positions(a.perp)
                    positions[a.label] = sum(
                        (Decimal(str(p.position_amount)) for p in poss), Decimal("0")
                    )
        except Exception as e:
            errors_24h.append({"label": "report", "err": f"BingX: {type(e).__name__}"})

    text = build_report(now, fired_24h, last_eom, _HALT.exists(), errors_24h, positions, equity)
    alerter = build_alerter(prefix="[gtaa-vst]")
    try:
        if errors_24h or fired_24h == 0:
            await alerter.send_warning(text)
        else:
            await alerter.send_info(text)
    finally:
        await _aclose(alerter)
    print(text)


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()

"""Генератор demo-вердикта GTAA-4 из логов (план 47, ШАГ 4).

Читает весь ops/gtaa_vst.jsonl + state и считает ФАКТЫ исполнения
(не PnL): сколько дней таймер срабатывал, сколько ошибок, пойман ли
хотя бы один месячный ребаланс. Печатает заполненный шаблон
DEMO_CRITERIA-вердикта — числа из логов, не из головы.

Запускать ПОСЛЕ demo-периода (≥4 недели). Вывод → retro/ вручную.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from scripts.gtaa_vst_executor import _ASSETS, _STATE
from scripts.gtaa_vst_report import _read_log_since

_REBALANCE_ACTS = {"open_long", "close", "rebalance"}


def build_verdict(now: datetime, rows: list[dict[str, Any]], state: dict[str, Any]) -> str:
    """Чистая. Шаблон вердикта, заполненный фактами из логов.

    rows — все строки jsonl за период. Вывод по DEMO_CRITERIA
    (plans/47): надёжность исполнения, НЕ PnL.
    """
    ts_all = [int(r["ts"]) for r in rows if "ts" in r]
    fired = [r for r in rows if r.get("action") == "fired"]
    days_fired = {datetime.fromtimestamp(int(r["ts"]), tz=UTC).date() for r in fired}
    errors = [r for r in rows if r.get("status") == "error"]
    skips = [r for r in rows if r.get("action") == "skip"]
    rebalanced = [r for r in rows if r.get("status") == "ok" and r.get("action") in _REBALANCE_ACTS]

    if ts_all:
        first = datetime.fromtimestamp(min(ts_all), tz=UTC).date()
        last = datetime.fromtimestamp(max(ts_all), tz=UTC).date()
        span_days = (last - first).days + 1
        period = f"{first} — {last} ({span_days} дн)"
    else:
        span_days = 0
        period = "нет данных"

    timer_ok = span_days > 0 and len(days_fired) >= span_days
    caught_rebalance = len(rebalanced) > 0
    no_errors = len(errors) == 0
    reliable = bool(timer_ok and no_errors and caught_rebalance)

    lines = [
        f"GTAA-VST DEMO ВЕРДИКТ (сгенерирован {now.strftime('%Y-%m-%d')})",
        f"период: {period}",
        f"1. Таймер: срабатываний-дней {len(days_fired)}/{span_days}"
        + ("  OK" if timer_ok else "  ⚠️ ПРОПУСКИ"),
        "2. SMA200: сверить вручную с Yahoo по полям idx_close/sma200 в логе",
        f"3/4/5. Ребалансов исполнено (ok): {len(rebalanced)}"
        + ("  (полный цикл пойман)" if caught_rebalance else "  ⚠️ ещё не было"),
        f"6. Ошибок исполнения: {len(errors)}; skip-прогонов: {len(skips)}",
    ]
    for e in errors[:8]:
        lines.append(f"   ❌ {e.get('label', '?')}: {e.get('err', '?')}")
    lines.append(f"state.last_rebalance_eom: {state.get('last_rebalance_eom', '—')}")
    lines.append("ИСПОЛНЕНИЕ: НАДЁЖНО" if reliable else "ИСПОЛНЕНИЕ: НЕ ПОДТВЕРЖДЕНО (см. выше)")
    lines.append(
        "PnL: НЕ оценивается — 4 недели = ~1 ребаланс, статистически "
        "недоказательно (нужен трек в месяцы)."
    )
    lines.append("GO/NO-GO к реальным деньгам: по надёжности исполнения + явное «да» владельца.")
    if not caught_rebalance:
        lines.append(
            f"NB: за период не зафиксировано ни одного ребаланса по {len(_ASSETS)} "
            "активам — вердикт по исполнению неполный, продлить наблюдение."
        )
    return "\n".join(lines)


def main() -> None:
    rows = _read_log_since(0)
    state = json.loads(_STATE.read_text()) if _STATE.exists() else {}
    print(build_verdict(datetime.now(tz=UTC), rows, state))


if __name__ == "__main__":
    main()

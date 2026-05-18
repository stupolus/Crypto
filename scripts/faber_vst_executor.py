"""Faber на BingX VST — demo-исполнение (план 41.2). НЕ LIVE.

Сигнал Faber 200SMA по индексу (Yahoo ^NDX, без look-ahead) →
реконсиляция позиции перпа на BingX VST к target (LONG / flat),
идемпотентно от ФАКТИЧЕСКОЙ позиции. HARD-assert env==vst.
`--dry` — решение без ордера. Лог ops/faber_vst.jsonl.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
import urllib.request
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from adapters.bingx.client import BingXClient
from adapters.bingx.private import PrivateAPI
from adapters.bingx.private_models import OrderRequest
from adapters.bingx.settings import BingXSettings
from core.risk import RiskEngine, RiskInputs, RiskRejection, RiskTier, Side

_INDEX = "%5ENDX"
_PERP = "NCSINASDAQ1002USD-USDT"
_SMA = 200
_RISK = Decimal("0.01")  # B-tier 1.0% эквити (бизнес/риск-профиль.md)
_MAX_LEV = Decimal("3")  # B-tier потолок плеча (бизнес/риск-профиль.md;
#                          5x — только A+/абсолютный, не для Faber B-tier)
_TOL = Decimal("0.15")  # |факт−target|/target < 15% → уже в target
_LOG = Path("ops/faber_vst.jsonl")
_HALT = Path("ops/faber_HALT")  # kill-switch: файл есть → не торгуем
_STATE = Path("ops/faber_vst_state.json")  # период-стейт для брейкеров


def is_halted() -> bool:
    """Kill-switch: наличие ops/faber_HALT → НИ ОДНОГО ордера
    (биржевой стоп открытой позиции продолжает защищать)."""
    return _HALT.exists()


def period_keys(now: datetime) -> tuple[str, str, str]:
    """(день, ISO-неделя, месяц) — чистая, тестируемая."""
    iso = now.isocalendar()
    return (
        now.strftime("%Y-%m-%d"),
        f"{iso[0]}-W{iso[1]:02d}",
        now.strftime("%Y-%m"),
    )


def roll_state(
    prev: dict[str, str], equity: Decimal, keys: tuple[str, str, str]
) -> tuple[dict[str, str], Decimal, Decimal, Decimal]:
    """Прокат периодов (чистая, тестируемая). На смене дня —
    сброс day_trades/consecutive_losses (риск-профиль «до завтра»)
    и day_start. Возвращает (state, day_pnl, week_pnl, month_pnl)
    в валюте (current − start)."""
    d, w, m = keys
    st = dict(prev)
    if st.get("day") != d:
        st["day"] = d
        st["day_start_equity"] = str(equity)
        st["day_trades"] = "0"
        st["consecutive_losses"] = "0"
    if st.get("week") != w:
        st["week"] = w
        st["week_start_equity"] = str(equity)
    if st.get("month") != m:
        st["month"] = m
        st["month_start_equity"] = str(equity)
    day_pnl = equity - Decimal(st.get("day_start_equity", str(equity)))
    week_pnl = equity - Decimal(st.get("week_start_equity", str(equity)))
    month_pnl = equity - Decimal(st.get("month_start_equity", str(equity)))
    return st, day_pnl, week_pnl, month_pnl


def _signal() -> tuple[str, float, float]:
    u = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{_INDEX}"
        f"?period1=0&period2={int(time.time())}&interval=1d"
    )
    req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as fh:
        d = json.load(fh)
    res = d["chart"]["result"][0]
    cl = [c for c in res["indicators"]["quote"][0]["close"] if c is not None]
    sma = sum(cl[-_SMA - 1 : -1]) / _SMA
    return ("LONG" if cl[-1] > sma else "CASH", float(cl[-1]), float(sma))


def _perp_price() -> float | None:
    u = (
        "https://open-api.bingx.com/openApi/swap/v3/quote/klines"
        f"?symbol={_PERP}&interval=1d&limit=1"
    )
    try:
        req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as fh:
            rows = json.load(fh).get("data") or []
        if not rows:
            return None
        last = rows[-1]
        return float(last["close"] if isinstance(last, dict) else last[4])
    except Exception:
        return None


def decide(signal: str, cur_qty: Decimal, target_qty: Decimal) -> str:
    """Чистое решение (тестируемо без сети). cur_qty — знаковая
    позиция перпа; target_qty ≥ 0 (LONG-only стратегия)."""
    if signal == "CASH":
        return "noop" if cur_qty == 0 else "close"
    # signal LONG
    if cur_qty <= 0:
        return "open_long"
    if target_qty > 0 and abs(cur_qty - target_qty) / target_qty < _TOL:
        return "noop"
    return "rebalance"


def _log(row: dict[str, object]) -> None:
    _LOG.parent.mkdir(parents=True, exist_ok=True)
    with _LOG.open("a") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


async def _run(dry: bool) -> None:
    s = BingXSettings()
    if s.env != "vst":  # defense-in-depth поверх конфиг-изоляции
        print(f"STOP: BINGX_ENV={s.env!r} != 'vst'. Только demo. Не live.")
        return
    if is_halted():
        _log({"date": datetime.now(tz=UTC).strftime("%Y-%m-%d"),
              "ts": int(time.time()), "action": "HALTED",
              "reason": f"{_HALT} существует — kill-switch"})  # fmt: skip
        print(f"HALTED: {_HALT} существует. Ордеров нет (стоп позиции жив).")
        return
    sig, idx_c, sma = _signal()
    pp = _perp_price()
    today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    base: dict[str, object] = {
        "date": today, "ts": int(time.time()), "env": s.env,
        "signal": sig, "idx_close": idx_c, "sma200": sma, "perp_price": pp,
    }  # fmt: skip
    if pp is None or pp <= 0:
        _log({**base, "action": "skip", "reason": "нет цены перпа"})
        print("skip: нет цены перпа")
        return
    async with BingXClient(settings=s) as c:
        api = PrivateAPI(c)
        bal = await api.get_balance()
        equity = next(
            (Decimal(str(b.equity)) for b in bal if b.asset in ("USDT", "VST")),
            Decimal(str(bal[0].equity)) if bal else Decimal("0"),
        )
        poss = await api.get_positions(_PERP)
        cur_qty = sum((Decimal(str(p.position_amount)) for p in poss), Decimal("0"))
        # Стоп = собственный выход Faber (уровень SMA200) на перпе.
        pp_d = Decimal(str(pp))
        stop_px = (pp_d * Decimal(str(sma)) / Decimal(str(idx_c))).quantize(Decimal("0.01"))
        # Период-стейт + RiskEngine: liq-buffer, дневной/недельный/
        # месячный брейкеры, макс сделок/день, consecutive losses,
        # сайзинг от риска — единый источник (бизнес/риск-профиль.md).
        prev = json.loads(_STATE.read_text()) if _STATE.exists() else {}
        st, day_pnl, week_pnl, month_pnl = roll_state(
            prev, equity, period_keys(datetime.now(tz=UTC))
        )
        target_qty = Decimal("0")
        reject: str | None = None
        if sig == "LONG" and pp_d > stop_px:
            decision = RiskEngine().evaluate(
                RiskInputs(
                    equity=equity,
                    day_pnl=day_pnl,
                    week_pnl=week_pnl,
                    month_pnl=month_pnl,
                    day_trades_count=int(st.get("day_trades", "0")),
                    consecutive_losses=int(st.get("consecutive_losses", "0")),
                    side=Side.LONG,
                    entry_price=pp_d,
                    stop_price=stop_px,
                    tier=RiskTier.B,
                )  # fmt: skip
            )
            if isinstance(decision, RiskRejection):
                reject = f"{decision.code}: {decision.reason}"
            else:
                # RiskEngine: stop_min/5x/liq/брейкеры. Доп. B-tier
                # клемп ≤3x (риск-профиль.md, строже абсолютного 5x).
                qmax = (equity * _MAX_LEV) / pp_d
                target_qty = min(decision.quantity, qmax).quantize(Decimal("0.01"))
        act = "noop" if reject else decide(sig, cur_qty, target_qty)
        base |= {
            "equity": equity, "cur_qty": cur_qty, "stop_px": stop_px,
            "day_pnl": day_pnl, "week_pnl": week_pnl,
            "target_qty": target_qty, "decision": act, "reject": reject,
        }  # fmt: skip
        if dry or act == "noop":
            if not dry:  # persist прокат периодов (брейкеры работают)
                _STATE.write_text(json.dumps(st))
            _log({**base, "action": f"{'DRY:' if dry else ''}{act}"})
            print(f"{today} sig={sig} eq={equity} cur={cur_qty} "
                  f"tgt={target_qty} → {act}{' BLOCKED:' + reject if reject else ''}"
                  f"{' (dry)' if dry else ''}")  # fmt: skip
            return
        try:
            if act in ("close", "rebalance"):
                op = Decimal(st.get("equity_at_open", str(equity)))
                cl = int(st.get("consecutive_losses", "0"))
                st["consecutive_losses"] = str(cl + 1 if equity < op else 0)
                await api.close_position(_PERP)
            if act in ("open_long", "rebalance") and target_qty > 0:
                req = OrderRequest(
                    symbol=_PERP, side="BUY", position_side="LONG",
                    order_type="MARKET", quantity=target_qty,
                    attached_stop_loss=stop_px,  # = выход Faber (SMA200)
                )  # hedge-режим: positionSide=LONG  # fmt: skip
                ack = await api.place_order(req)
                base["order_ack"] = getattr(ack, "order_id", str(ack))
                st["equity_at_open"] = str(equity)
            st["day_trades"] = str(int(st.get("day_trades", "0")) + 1)
            _STATE.write_text(json.dumps(st))
            _log({**base, "action": act, "status": "ok"})
            print(f"{today} VST {act}: eq={equity} tgt={target_qty} → ok")
        except Exception as e:
            _log({**base, "action": act, "status": "error",
                  "err": f"{type(e).__name__}: {str(e)[:200]}"})  # fmt: skip
            print(f"{today} VST {act} ERROR {type(e).__name__}: {str(e)[:160]}")


def main() -> None:
    dry = "--dry" in sys.argv
    asyncio.run(_run(dry))
    print("VST demo-исполнение (план 41). НЕ live. Вердикт — план 40/41.4.")


if __name__ == "__main__":
    main()

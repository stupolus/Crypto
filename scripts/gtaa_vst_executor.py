"""Faber 2007 GTAA-4 на BingX VST — demo-исполнение (план 47.2). НЕ LIVE.

4 актива FIXED (план 45.3): ^GSPC→NCSISP500, ^NDX→NCSINASDAQ100,
GC=F→NCCOGOLD, CL=F→NCCO1OILWTI. Сигнал Faber 200SMA на каждом
Yahoo-индексе (без look-ahead), equal-weight 1/4 эквити per ON,
ежемесячный ребаланс EOM. HARD-assert env==vst.

Идемпотентность: state.last_rebalance_eom; ребаланс только когда
максимальная Yahoo-EOM-дата по 4 активам > state. Daily-timer
автоматически делает один ребаланс/месяц + догон при простое.

Stops: SMA200-уровень на индексе → перенесён на перп пропорцией.
RiskEngine per-asset с pre-entry liq (план 41.6).
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
import urllib.request
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from adapters.bingx.client import BingXClient
from adapters.bingx.private import PrivateAPI
from adapters.bingx.private_models import OrderRequest
from adapters.bingx.settings import BingXSettings
from core.risk import RiskEngine, RiskInputs, RiskRejection, RiskTier, Side
from scripts.faber_vst_executor import (
    decide,
    estimate_liq_price,
    period_keys,
    roll_state,
)


@dataclass(frozen=True)
class _Asset:
    label: str
    yahoo: str  # URL-encoded
    perp: str


_ASSETS: tuple[_Asset, ...] = (
    _Asset("GSPC", "%5EGSPC", "NCSISP5002USD-USDT"),
    _Asset("NDX", "%5ENDX", "NCSINASDAQ1002USD-USDT"),
    _Asset("GC", "GC%3DF", "NCCOGOLD2USD-USDT"),
    _Asset("CL", "CL%3DF", "NCCO1OILWTI2USD-USDT"),
)
_N = Decimal(len(_ASSETS))
_SMA = 200
_RISK = Decimal("0.01")  # B-tier 1% эквити (бизнес/риск-профиль.md)
_MAX_LEV = Decimal("3")  # B-tier потолок (применяется к доле 1/N)
_TOL = Decimal("0.15")  # толеранс reuse через faber.decide
_LOG = Path("ops/gtaa_vst.jsonl")
_HALT = Path("ops/gtaa_HALT")  # отдельный kill-switch от faber
_STATE = Path("ops/gtaa_vst_state.json")


def is_halted() -> bool:
    """Kill-switch: наличие ops/gtaa_HALT → НИ ОДНОГО ордера."""
    return _HALT.exists()


def _http_get_json(url: str, timeout: float = 30.0, retries: int = 3) -> Any:
    """GET с ретраями и экспоненциальным бэкоффом (2/4/8s). Browser UA.

    Сетевые обрывы на VPS — норма; ретрай делает прогон устойчивым.
    После исчерпания попыток пробрасывает последнее исключение
    (вызывающий решает: skip-прогон vs None)."""
    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as fh:
                return json.load(fh)
        except Exception as e:  # любой сбой сети ретраим
            last = e
            if attempt < retries - 1:
                time.sleep(2 ** (attempt + 1))
    assert last is not None
    raise last


def _fetch_yahoo_daily(yahoo_sym: str) -> list[tuple[date, float]]:
    """Daily adjclose Yahoo (с ретраями). Сорт по дате."""
    u = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_sym}"
        f"?period1=0&period2={int(time.time())}&interval=1d"
    )
    d = _http_get_json(u)
    res = d["chart"]["result"][0]
    ts = res["timestamp"]
    adj = res["indicators"].get("adjclose") or [{}]
    cl = adj[0].get("adjclose") if adj else None
    if cl is None:
        cl = res["indicators"]["quote"][0]["close"]
    out: list[tuple[date, float]] = []
    for t, c in zip(ts, cl, strict=True):
        if c is not None and c > 0:
            out.append((datetime.fromtimestamp(t, tz=UTC).date(), float(c)))
    out.sort(key=lambda x: x[0])
    return out


def latest_eom_with_sma(
    rows: list[tuple[date, float]], sma_n: int = _SMA
) -> tuple[date, float, float] | None:
    """Чистая. Последняя EOM-дата в данных + close + SMA(sma_n) на этот день.

    EOM = последний наблюдаемый день в (year, month) бакете. Это honest
    для бэктеста/исполнения: ровно тот close, который мы можем
    использовать как сигнал."""
    if len(rows) < sma_n + 1:
        return None
    # Группировка по (year, month), берём индекс последнего дня каждой группы.
    last_idx_per_month: dict[tuple[int, int], int] = {}
    for i, (d, _c) in enumerate(rows):
        last_idx_per_month[(d.year, d.month)] = i
    # Последний bucket = max key
    if not last_idx_per_month:
        return None
    last_bucket = max(last_idx_per_month)
    i_eom = last_idx_per_month[last_bucket]
    if i_eom < sma_n - 1:
        return None
    closes = [c for (_d, c) in rows]
    sma = sum(closes[i_eom - sma_n + 1 : i_eom + 1]) / sma_n
    return rows[i_eom][0], rows[i_eom][1], sma


def _perp_price(perp_symbol: str) -> float | None:
    """Текущая цена перпа через swap v3 klines (last close, с ретраями)."""
    u = (
        "https://open-api.bingx.com/openApi/swap/v3/quote/klines"
        f"?symbol={perp_symbol}&interval=1d&limit=1"
    )
    try:
        rows = _http_get_json(u).get("data") or []
        if not rows:
            return None
        last = rows[-1]
        return float(last["close"] if isinstance(last, dict) else last[4])
    except Exception:
        return None


def should_rebalance(target_eom: date, last_eom_str: str | None) -> bool:
    """Чистая. Ребалансируем если target_eom строго новее state.

    last_eom_str = state["last_rebalance_eom"] или None при первом запуске.
    None → ребалансируем. Иначе сравниваем ISO-даты."""
    if not last_eom_str:
        return True
    return target_eom > date.fromisoformat(last_eom_str)


def _log(row: dict[str, object]) -> None:
    _LOG.parent.mkdir(parents=True, exist_ok=True)
    with _LOG.open("a") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


@dataclass(frozen=True)
class AssetPlan:
    """Решение по одному активу (чистый расчёт, без сетевых вызовов)."""

    label: str
    perp: str
    signal: str  # LONG | CASH
    idx_close: float
    sma200: float
    perp_price: Decimal
    stop_px: Decimal
    liq_est: Decimal | None
    cur_qty: Decimal
    target_qty: Decimal
    reject: str | None
    action: str  # open_long | close | rebalance | noop


def plan_asset_action(
    asset: _Asset,
    idx_close: float,
    sma200: float,
    perp_price: Decimal,
    cur_qty: Decimal,
    equity_share: Decimal,
    engine: RiskEngine,
    mmr: Decimal,
    pnls: tuple[Decimal, Decimal, Decimal],
    day_trades: int,
    consecutive_losses: int,
) -> AssetPlan:
    """Чистая. Сигнал Faber → стоп (SMA200 на перпе) → target_qty
    (RiskEngine на доле 1/N, клемп ≤3x) → решение реконсиляции.

    Тестируемо без сети — ядро DEMO_CRITERIA 3 (сигнал) и 4 (доли 1/N).
    """
    day_pnl, week_pnl, month_pnl = pnls
    sig_on = idx_close > sma200
    sig_str = "LONG" if sig_on else "CASH"
    stop_px = (perp_price * Decimal(str(sma200)) / Decimal(str(idx_close))).quantize(
        Decimal("0.01")
    )
    target_qty = Decimal("0")
    reject: str | None = None
    liq_est: Decimal | None = None
    if sig_on and perp_price > stop_px:
        liq_est = estimate_liq_price(perp_price, Side.LONG, _MAX_LEV, mmr)
        decision = engine.evaluate(
            RiskInputs(
                equity=equity_share,
                day_pnl=day_pnl, week_pnl=week_pnl, month_pnl=month_pnl,
                day_trades_count=day_trades,
                consecutive_losses=consecutive_losses,
                side=Side.LONG,
                entry_price=perp_price,
                stop_price=stop_px,
                tier=RiskTier.B,
                liquidation_price=liq_est,
            )
        )  # fmt: skip
        if isinstance(decision, RiskRejection):
            reject = f"{decision.code}: {decision.reason}"
        else:
            qmax = (equity_share * _MAX_LEV) / perp_price
            target_qty = min(decision.quantity, qmax).quantize(Decimal("0.01"))
    act = "noop" if reject else decide(sig_str, cur_qty, target_qty)
    return AssetPlan(
        label=asset.label, perp=asset.perp, signal=sig_str,
        idx_close=idx_close, sma200=sma200, perp_price=perp_price,
        stop_px=stop_px, liq_est=liq_est, cur_qty=cur_qty,
        target_qty=target_qty, reject=reject, action=act,
    )  # fmt: skip


def _plan_to_row(p: AssetPlan) -> dict[str, object]:
    """Лог-строка из плана (формат стабилен для аудита jsonl)."""
    return {
        "label": p.label, "perp": p.perp, "signal": p.signal,
        "idx_close": p.idx_close, "sma200": p.sma200,
        "perp_price": float(p.perp_price), "stop_px": str(p.stop_px),
        "liq_est": str(p.liq_est) if p.liq_est else None,
        "cur_qty": str(p.cur_qty), "target_qty": str(p.target_qty),
        "decision": p.action, "reject": p.reject,
    }  # fmt: skip


def format_rebalance_summary(target_eom: date, rows: list[dict[str, object]]) -> str:
    """Чистая. Человекочитаемая сводка ребаланса для Telegram/лога."""
    ok = sum(1 for r in rows if r.get("status") == "ok")
    parts = [
        f"{r.get('label')}:{r.get('signal')}→{r.get('action')}[{r.get('status')}]" for r in rows
    ]
    return f"GTAA-VST EOM={target_eom}: {ok}/{len(rows)} ok | " + ", ".join(parts)


async def _aclose(alerter: object) -> None:
    """Best-effort закрытие httpx-клиента TelegramAlerter (Stdout — no-op)."""
    fn = getattr(alerter, "aclose", None)
    if fn is not None:
        await fn()


async def _run(dry: bool) -> None:
    from core.alerts.factory import build_alerter

    s = BingXSettings()
    if s.env != "vst":
        # Heartbeat даже при stop — прогон зафиксирован для аудита.
        _log({"ts": int(time.time()), "action": "fired", "outcome": "env_stop",
              "env": s.env, "dry": dry})  # fmt: skip
        print(f"STOP: BINGX_ENV={s.env!r} != 'vst'. Только demo. Не live.")
        return

    alerter = build_alerter(prefix="[gtaa-vst]")
    # Heartbeat: каждый прогон таймера оставляет след (даже noop/halt) —
    # daily-report считает «fired» за 24ч, подтверждая что таймер живой.
    _log({"ts": int(time.time()), "action": "fired", "dry": dry})
    try:
        if is_halted():
            _log({
                "ts": int(time.time()), "action": "HALTED",
                "reason": f"{_HALT} существует — kill-switch",
            })  # fmt: skip
            await alerter.send_warning(f"HALTED: {_HALT} существует, ордеров нет")
            print(f"HALTED: {_HALT} существует.")
            return

        # 1. Yahoo сигналы для 4 индексов
        eoms: dict[str, tuple[date, float, float]] = {}
        for a in _ASSETS:
            try:
                rows = _fetch_yahoo_daily(a.yahoo)
            except Exception as e:
                _log({"ts": int(time.time()), "label": a.label, "action": "skip",
                      "reason": f"yahoo error: {type(e).__name__}"})  # fmt: skip
                await alerter.send_warning(
                    f"skip: Yahoo {a.label} недоступен после ретраев ({type(e).__name__})"
                )
                print(f"skip: yahoo {a.label} {type(e).__name__}")
                return
            e_eom = latest_eom_with_sma(rows)
            if e_eom is None:
                _log({"ts": int(time.time()), "label": a.label, "action": "skip",
                      "reason": "не хватает истории для SMA200"})  # fmt: skip
                print(f"skip: {a.label} no sma200 data")
                return
            eoms[a.label] = e_eom

        # 2. Триггер ребаланса: max EOM по 4 индексам vs state
        target_eom = max(d for (d, _c, _s) in eoms.values())
        prev = json.loads(_STATE.read_text()) if _STATE.exists() else {}
        if not should_rebalance(target_eom, prev.get("last_rebalance_eom")):
            _log({"ts": int(time.time()), "action": "noop",
                  "reason": "уже ребалансированы на этот EOM",
                  "target_eom": target_eom.isoformat()})  # fmt: skip
            print(f"noop: уже ребалансированы на {target_eom}")
            return

        # 3. Цены перпов
        perp_pxs: dict[str, float] = {}
        for a in _ASSETS:
            pp = _perp_price(a.perp)
            if pp is None or pp <= 0:
                _log({"ts": int(time.time()), "label": a.label, "action": "skip",
                      "reason": "нет цены перпа"})  # fmt: skip
                await alerter.send_warning(f"skip: нет цены перпа {a.perp}")
                print(f"skip: нет цены {a.perp}")
                return
            perp_pxs[a.label] = pp

        await _rebalance(s, dry, eoms, perp_pxs, prev, target_eom, alerter)
    finally:
        await _aclose(alerter)


async def _rebalance(
    s: BingXSettings,
    dry: bool,
    eoms: dict[str, tuple[date, float, float]],
    perp_pxs: dict[str, float],
    prev: dict[str, str],
    target_eom: date,
    alerter: Any,
) -> None:
    # 4. BingX session, эквити, period-state
    async with BingXClient(settings=s) as c:
        api = PrivateAPI(c)
        bal = await api.get_balance()
        equity = next(
            (Decimal(str(b.equity)) for b in bal if b.asset in ("USDT", "VST")),
            Decimal(str(bal[0].equity)) if bal else Decimal("0"),
        )
        equity_share = (equity / _N).quantize(Decimal("0.01"))
        st, day_pnl, week_pnl, month_pnl = roll_state(
            prev, equity, period_keys(datetime.now(tz=UTC))
        )
        engine = RiskEngine()
        mmr = Decimal(str(engine.config.limits.maintenance_margin_rate))

        # 5. Per-asset reconcile
        base_log: dict[str, object] = {
            "ts": int(time.time()), "env": s.env,
            "target_eom": target_eom.isoformat(),
            "equity": str(equity), "equity_share": str(equity_share),
        }  # fmt: skip
        rows_done: list[dict[str, object]] = []
        for a in _ASSETS:
            _idx_date, idx_close, sma200 = eoms[a.label]
            poss = await api.get_positions(a.perp)
            cur_qty = sum((Decimal(str(p.position_amount)) for p in poss), Decimal("0"))
            plan = plan_asset_action(
                a, idx_close, sma200, Decimal(str(perp_pxs[a.label])), cur_qty,
                equity_share, engine, mmr, (day_pnl, week_pnl, month_pnl),
                int(st.get("day_trades", "0")), int(st.get("consecutive_losses", "0")),
            )  # fmt: skip
            row = _plan_to_row(plan)
            if dry or plan.action == "noop":
                rows_done.append(
                    row | {"action": f"{'DRY:' if dry else ''}{plan.action}", "status": "ok"}
                )
                continue
            try:
                if plan.action in ("close", "rebalance"):
                    await api.close_position(a.perp)
                if plan.action in ("open_long", "rebalance") and plan.target_qty > 0:
                    req = OrderRequest(
                        symbol=a.perp, side="BUY", position_side="LONG",
                        order_type="MARKET", quantity=plan.target_qty,
                        attached_stop_loss=plan.stop_px,
                    )  # hedge-режим, фикс #164  # fmt: skip
                    ack = await api.place_order(req)
                    row["order_ack"] = getattr(ack, "order_id", str(ack))
                rows_done.append(row | {"action": plan.action, "status": "ok"})
                st["day_trades"] = str(int(st.get("day_trades", "0")) + 1)
            except Exception as e:
                rows_done.append(
                    row | {"action": plan.action, "status": "error",
                           "err": f"{type(e).__name__}: {str(e)[:200]}"}
                )  # fmt: skip

        # 6. Persist state + log all rows
        # В DRY не двигаем last_rebalance_eom (иначе реальный прогон в этом
        # месяце посчитает себя noop). State пишем только при боевом ребалансе.
        if not dry:
            st["last_rebalance_eom"] = target_eom.isoformat()
            _STATE.write_text(json.dumps(st))
        for r in rows_done:
            _log({**base_log, **r})
        ok_count = sum(1 for r in rows_done if r.get("status") == "ok")
        errors = [r for r in rows_done if r.get("status") == "error"]
        summary = format_rebalance_summary(target_eom, rows_done)
        if errors:
            await alerter.send_critical(
                summary
                + " | ОШИБКИ: "
                + "; ".join(f"{r.get('label')}={r.get('err')}" for r in errors)
            )
        elif not dry:
            await alerter.send_info(summary)
        print(
            f"{datetime.now(tz=UTC).strftime('%Y-%m-%d')} GTAA-VST rebalance "
            f"EOM={target_eom}: {ok_count}/{len(rows_done)} OK"
        )


def format_preflight(
    env: str,
    sig_rows: list[tuple[str, str, float, float, str]],
    bingx_ok: bool,
    equity: Decimal | None,
    errors: list[str],
) -> str:
    """Чистая. Текст preflight-проверки (тестируемо без сети).

    sig_rows: (label, eom_date, close, sma200, signal). Печатает по
    каждому активу для ручной сверки SMA200 с Yahoo (DEMO_CRITERIA 2/3).
    """
    lines = ["GTAA-VST preflight (read-only, без ордеров)"]
    lines.append(f"env: {env}" + ("" if env == "vst" else "  ⚠️ ОЖИДАЛОСЬ vst!"))
    for label, eom, close, sma, sig in sig_rows:
        lines.append(f"  {label}: EOM={eom} close={close:.2f} sma200={sma:.2f} → {sig}")
    lines.append(f"BingX VST: {'OK' if bingx_ok else 'НЕТ СВЯЗИ'}")
    if equity is not None:
        lines.append(f"equity: {equity}")
    if errors:
        lines.append("ОШИБКИ: " + "; ".join(errors))
    ok = env == "vst" and bingx_ok and not errors and len(sig_rows) == len(_ASSETS)
    lines.append("ИТОГ: ГОТОВ К ЗАПУСКУ" if ok else "ИТОГ: ЕСТЬ ПРОБЛЕМЫ (см. выше)")
    return "\n".join(lines)


async def _preflight() -> int:
    """Read-only проверка: сигналы по 4 активам + связь с BingX VST.
    Не ставит ордера, не пишет стейт, не шлёт алерты. exit 0 = готов."""
    s = BingXSettings()
    errors: list[str] = []
    sig_rows: list[tuple[str, str, float, float, str]] = []
    for a in _ASSETS:
        try:
            eom = latest_eom_with_sma(_fetch_yahoo_daily(a.yahoo))
        except Exception as e:
            errors.append(f"{a.label}: yahoo {type(e).__name__}")
            continue
        if eom is None:
            errors.append(f"{a.label}: нет истории для SMA200")
            continue
        d, close, sma = eom
        sig_rows.append((a.label, d.isoformat(), close, sma, "LONG" if close > sma else "CASH"))

    bingx_ok = False
    equity: Decimal | None = None
    if s.env == "vst":
        try:
            async with BingXClient(settings=s) as c:
                bal = await PrivateAPI(c).get_balance()
                equity = next(
                    (Decimal(str(b.equity)) for b in bal if b.asset in ("USDT", "VST")),
                    Decimal(str(bal[0].equity)) if bal else None,
                )
                bingx_ok = True
        except Exception as e:
            errors.append(f"BingX: {type(e).__name__}")

    text = format_preflight(s.env, sig_rows, bingx_ok, equity, errors)
    print(text)
    return 0 if text.endswith("ГОТОВ К ЗАПУСКУ") else 1


def main() -> None:
    if "--check" in sys.argv:
        sys.exit(asyncio.run(_preflight()))
    dry = "--dry" in sys.argv
    asyncio.run(_run(dry))
    print("VST demo-исполнение (план 47). НЕ live.")


if __name__ == "__main__":
    main()

"""Полная матрица DOLF на дневке (payoff: данные разблокированы $0).

Coinglass HOBBYIST на 1d отдаёт liq/OI/funding/CVD за ~2.5 года
(ноя-2023→). Цена — дневной Yahoo (BTC/ETH/SOL-USD). Прогон ВСЕХ
10 детекторов (план 23) через готовый харнес evaluate_detector,
IS/OOS, честный гейт.

⚠️ ~2.5 года = в осн. режим 2024-25 (медведя 2022 в данных
Coinglass нет — лимит источника, не тарифа). Достаточно для
≥30 сделок + IS/OOS + WF, но НЕ полный бык+медведь. Вердикт
честный в обе стороны, без подгона.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from decimal import Decimal

import httpx

from core.signals.composite import FundingProvider
from core.signals.dolf_backtest import Candle, evaluate_detector
from core.signals.dolf_setups import ALL_DETECTORS
from parsers.coinglass.backfill import backfill_providers
from parsers.coinglass.client import CoinglassClient

_SYMS = {"BTC-USDT": "BTC-USD", "ETH-USDT": "ETH-USD", "SOL-USDT": "SOL-USD"}
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


class _TimedFunding:
    """FundingProvider: ближайший funding ≤ ts из истории Coinglass."""

    def __init__(self, series: list[tuple[int, Decimal]]) -> None:
        self._s = sorted(series)

    def get_funding_rate(self, symbol: str, timestamp_ms: int) -> Decimal | None:
        prev: Decimal | None = None
        for ts, v in self._s:
            if ts > timestamp_ms:
                break
            prev = v
        return prev


def _daily_candles(yahoo_sym: str) -> list[Candle]:
    for _ in range(4):
        try:
            r = httpx.get(
                f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_sym}",
                params={"range": "5y", "interval": "1d"},
                headers={"User-Agent": _UA},
                timeout=20,
                follow_redirects=True,
            )
            if r.status_code == 200:
                q = r.json()["chart"]["result"][0]
                ts = q["timestamp"]
                o = q["indicators"]["quote"][0]
                out: list[Candle] = []
                for i, t in enumerate(ts):
                    if None in (o["high"][i], o["low"][i], o["close"][i]):
                        continue
                    out.append(
                        Candle(
                            open_time_ms=int(t) * 1000,
                            high=Decimal(str(o["high"][i])),
                            low=Decimal(str(o["low"][i])),
                            close=Decimal(str(o["close"][i])),
                            volume=Decimal(str(o["volume"][i] or 0)),
                        )
                    )
                return out
            time.sleep(3)
        except httpx.HTTPError:
            time.sleep(3)
    return []


def main() -> None:
    now = int(time.time() * 1000)
    start = now - int(2.6 * 365 * 24 * 3600 * 1000)
    cg = CoinglassClient()
    print("Матрица DOLF на дневке (Coinglass 2.5г + Yahoo daily)")
    print("Гейт: OOS PF>1.3 И Sharpe>0.8 И ≥30. ~2.5г, в осн. 2024-25.")
    print("=" * 78)
    pass_any = False
    for cg_sym, ysym in _SYMS.items():
        candles = _daily_candles(ysym)
        if len(candles) < 200:
            print(f"{cg_sym}: нет дневных цен Yahoo ({len(candles)})")
            continue
        liq, oi, delta = backfill_providers(
            cg_sym, "1d", start_time_ms=start, end_time_ms=now, client=cg
        )
        # funding из Coinglass → time-aware провайдер
        from parsers.coinglass.backfill import map_symbol

        m = map_symbol(cg_sym)
        fund: FundingProvider
        if m:
            exch, csym, _ = m
            fr = cg.get_funding_history(
                exchange=exch, symbol=csym, interval="1d",
                start_time_ms=start, end_time_ms=now, limit=1000,
            )  # fmt: skip
            fund = _TimedFunding(fr)
            lh = cg.get_liquidation_history(
                exchange=exch, symbol=csym, interval="1d",
                start_time_ms=start, end_time_ms=now, limit=1000,
            )  # fmt: skip
            tss = [x.timestamp_ms for x in lh]
            cg_lo, cg_hi = (min(tss), max(tss)) if tss else (0, 0)
        else:
            fund = _TimedFunding([])
            cg_lo, cg_hi = 0, 0
        # КРИТИЧНО: окно = РЕАЛЬНЫЙ диапазон данных Coinglass (ts истории
        # ликвидаций). Иначе IS-период без структурных данных = ложный
        # «OOS-only» прогон (баг первого запуска).
        if cg_lo == 0:
            print(f"\n### {cg_sym}: Coinglass liq ПУСТО — пропуск (проверь ключ)")
            continue
        covered = [c for c in candles if cg_lo <= c.open_time_ms <= cg_hi]
        if len(covered) < 120:
            print(f"\n### {cg_sym}: покрытие Coinglass <120 дн ({len(covered)}) — мало")
            continue
        c0, c1 = covered[0].open_time_ms, covered[-1].open_time_ms
        win = [c for c in candles if c0 <= c.open_time_ms <= c1]
        d0 = datetime.fromtimestamp(c0 / 1000, tz=UTC).date()
        d1 = datetime.fromtimestamp(c1 / 1000, tz=UTC).date()
        # B&H бенчмарк на OOS-половине окна
        half = len(win) // 2
        bh_oos = float(win[-1].close / win[half].close - 1) * 100
        print(
            f"\n### {cg_sym}  ОКНО Coinglass {d0}→{d1} ({len(win)} дн), "
            f"B&H OOS={bh_oos:+.0f}%  [IS=ранняя ½, OOS=поздняя ½ окна]"
        )
        for det in ALL_DETECTORS:
            name = det.__name__.replace("detect_", "")
            is_st = evaluate_detector(
                det, win[:half], liq=liq, oi=oi, delta=delta,
                funding=fund, symbol=cg_sym, horizon_bars=5, min_history=40,
            )  # fmt: skip
            oos_st = evaluate_detector(
                det, win[half:], liq=liq, oi=oi, delta=delta,
                funding=fund, symbol=cg_sym, horizon_bars=5, min_history=40,
            )  # fmt: skip
            # честный гейт: оба полупериода значимы (≥20 сделок) И OOS
            # проходит И IS не противоречит (PF>1) И есть выборка в IS
            ok = oos_st.passes and is_st.trades >= 20 and is_st.profit_factor > 1.0
            mark = "✓ПРОШЁЛ" if ok else "✗"
            if ok:
                pass_any = True
            print(
                f"  {name:24s} IS n{is_st.trades:3d} PF{is_st.profit_factor:5.2f} "
                f"Sh{is_st.sharpe:+5.2f} | OOS n{oos_st.trades:3d} "
                f"PF{oos_st.profit_factor:5.2f} Sh{oos_st.sharpe:+5.2f} {mark}"
            )
    cg.close()
    print("=" * 78)
    print(
        "ИТОГ: "
        + (
            "есть прошедшие OOS-гейт — кандидаты в композит (план 23.5)"
            if pass_any
            else "ни один детектор не прошёл OOS-гейт на доступных данных"
        )
    )


if __name__ == "__main__":
    main()

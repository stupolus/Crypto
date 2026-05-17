"""Режим-честная валидация тренд-крипты на ПОЛНЫХ циклах (план 22).

Источник: Yahoo BTC/ETH/SOL-USD недельно 2016+ (медведи 2018/2022
включены — BingX REST это резал на 720дн). Идея пользователя
«анализировать на глубокой истории» — реализована достижимым
источником (Binance/Bybit из среды гео-блок 451/403).

Правило — каноничное, недокрученное: цена выше 40-нед SMA
(≈200-дн) → лонг, иначе флэт. + трейлинг-вариант. Параметры НЕ
подгоняются.

КРИТИЧНЫЙ бенчмарк — buy&hold: в растущей крипте любое
лонг-смещение «прибыльно»; edge = ПОБИТЬ B&H по риску (Sharpe/DD),
иначе это просто бета. Гейт: Sharpe>0.8 И t>2 И бьёт B&H по Sharpe.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

import httpx

_SYMS = ["BTC-USD", "ETH-USD", "SOL-USD"]
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_SMA_W = 40  # недель ≈ 200 дн (каноничный трендовый фильтр)
_TRAIL = 0.20  # трейлинг 20% от пика (типовое для крипты, не подгон)
_COST = 0.002  # на смену позиции


def _weekly(sym: str) -> list[tuple[int, float]]:
    for _ in range(4):
        try:
            r = httpx.get(
                f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}",
                params={"range": "10y", "interval": "1wk"},
                headers={"User-Agent": _UA},
                timeout=20,
                follow_redirects=True,
            )
            if r.status_code == 200:
                res = r.json()["chart"]["result"][0]
                ts = res["timestamp"]
                cl = res["indicators"]["quote"][0]["close"]
                return [(int(t), float(c)) for t, c in zip(ts, cl, strict=False) if c]
        except httpx.HTTPError:
            pass
    return []


def _sma_long_flat(closes: list[float]) -> list[float]:
    """Доходность правила: в неделю t+1 лонг если close[t]>SMA40, иначе 0."""
    out: list[float] = []
    prev = 0
    for t in range(_SMA_W, len(closes) - 1):
        sma = sum(closes[t - _SMA_W : t]) / _SMA_W
        pos = 1 if closes[t] > sma else 0
        r = (closes[t + 1] / closes[t] - 1.0) * pos
        if pos != prev:
            r -= _COST
        out.append(r)
        prev = pos
    return out


def _trailing(closes: list[float]) -> list[float]:
    """Лонг при close>SMA40, выход по трейлингу _TRAIL от пика."""
    out: list[float] = []
    in_pos = False
    peak = 0.0
    for t in range(_SMA_W, len(closes) - 1):
        sma = sum(closes[t - _SMA_W : t]) / _SMA_W
        if not in_pos and closes[t] > sma:
            in_pos = True
            peak = closes[t]
            out.append(-_COST)
            continue
        if in_pos:
            peak = max(peak, closes[t])
            if closes[t] <= peak * (1 - _TRAIL):
                in_pos = False
                out.append(0.0)
                continue
            out.append(closes[t + 1] / closes[t] - 1.0)
        else:
            out.append(0.0)
    return out


def _bh(closes: list[float]) -> list[float]:
    return [closes[t + 1] / closes[t] - 1.0 for t in range(_SMA_W, len(closes) - 1)]


def _m(series: list[float], tag: str, bh_sharpe: float | None = None) -> str:
    if len(series) < 20:
        return f"{tag}: n={len(series)} (мало)"
    n = len(series)
    mean = sum(series) / n
    sd = math.sqrt(sum((x - mean) ** 2 for x in series) / (n - 1))
    sharpe = mean / sd * math.sqrt(52) if sd > 0 else 0.0
    t = mean / (sd / math.sqrt(n)) if sd > 0 else 0.0
    p = math.erfc(abs(t) / math.sqrt(2))
    eq = 1.0
    peak = 1.0
    mdd = 0.0
    for r in series:
        eq *= 1 + r
        peak = max(peak, eq)
        mdd = max(mdd, (peak - eq) / peak)
    beats = "" if bh_sharpe is None else (" БЬЁТ-B&H" if sharpe > bh_sharpe else " ХУЖЕ-B&H")
    gate = ""
    if bh_sharpe is not None:
        gate = " ✓" if (sharpe > 0.8 and t > 2.0 and sharpe > bh_sharpe) else " ✗"
    return (
        f"{tag}: n={n:3d} Sharpe={sharpe:+5.2f} t={t:+4.2f} p={p:.3f} "
        f"maxDD={mdd * 100:4.0f}% ret={(eq - 1) * 100:+8.0f}%{beats}{gate}"
    )


def _split_label(ts: list[int]) -> str:
    d0 = datetime.fromtimestamp(ts[0], tz=UTC).date()
    d1 = datetime.fromtimestamp(ts[-1], tz=UTC).date()
    return f"{d0}→{d1}"


def main() -> None:
    print("Тренд-крипта на ПОЛНЫХ циклах (Yahoo недельно, медведи вкл.)")
    print("Правило: close>SMA40 → лонг. Бенчмарк B&H обязателен.")
    print("=" * 74)
    port_rule_is: list[float] = []
    port_rule_oos: list[float] = []
    port_bh_is: list[float] = []
    port_bh_oos: list[float] = []
    port_tr_is: list[float] = []
    port_tr_oos: list[float] = []
    for sym in _SYMS:
        ser = _weekly(sym)
        if len(ser) < _SMA_W + 40:
            print(f"{sym}: Yahoo недоступен/мало ({len(ser)})")
            continue
        ts = [t for t, _ in ser]
        cl = [c for _, c in ser]
        rule = _sma_long_flat(cl)
        bh = _bh(cl)
        tr = _trailing(cl)
        h = len(rule) // 2
        port_rule_is += rule[:h]
        port_rule_oos += rule[h:]
        port_bh_is += bh[:h]
        port_bh_oos += bh[h:]
        port_tr_is += tr[:h]
        port_tr_oos += tr[h:]
        bhs_is = _bh_sharpe(bh[:h])
        bhs_oos = _bh_sharpe(bh[h:])
        print(f"{sym}  ({_split_label(ts)}):")
        print(f"  B&H    {_m(bh[:h], 'IS ')} | {_m(bh[h:], 'OOS')}")
        print(f"  RULE   {_m(rule[:h], 'IS ', bhs_is)} | {_m(rule[h:], 'OOS', bhs_oos)}")
        print(f"  TRAIL  {_m(tr[:h], 'IS ', bhs_is)} | {_m(tr[h:], 'OOS', bhs_oos)}")
    print("=" * 74)
    bhi = _bh_sharpe(port_bh_is)
    bho = _bh_sharpe(port_bh_oos)
    print(f"ПОРТФЕЛЬ B&H   IS {_m(port_bh_is, '')} | OOS {_m(port_bh_oos, '')}")
    print(f"ПОРТФЕЛЬ RULE  IS {_m(port_rule_is, '', bhi)} | OOS {_m(port_rule_oos, '', bho)}")
    print(f"ПОРТФЕЛЬ TRAIL IS {_m(port_tr_is, '', bhi)} | OOS {_m(port_tr_oos, '', bho)}")
    print("\nГейт: Sharpe>0.8 И t>2 И ПОБИТЬ B&H по Sharpe на OOS.")


def _bh_sharpe(series: list[float]) -> float:
    if len(series) < 2:
        return 0.0
    mean = sum(series) / len(series)
    sd = math.sqrt(sum((x - mean) ** 2 for x in series) / (len(series) - 1))
    return mean / sd * math.sqrt(52) if sd > 0 else 0.0


if __name__ == "__main__":
    main()

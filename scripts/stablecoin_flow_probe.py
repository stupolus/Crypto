"""РАЗВЕДКА (не валидация): стейбл-эмиссия → форвард-доходность BTC.

Структурно иной класс (вариант 3): ончейн-предложение стейблов
(USDT+USDC market cap ≈ circulating supply), НЕ цена/чарт.
Тезис: рост агрегата стейблов = приток ликвидности → буллиш;
сжатие → risk-off. Опережающий, не ценовой сигнал.

⚠️ CoinGecko free = только 365 дней = ОДИН режим. Это НЕ
валидация (один режим = ловушка, см. funding +524%/-61%).
Только разведка: есть ли вообще хоть какая-то связь, стоит ли
платить за глубокую историю. Вердикт по гейту тут невозможен.
"""

from __future__ import annotations

import math
import time

import httpx


def _cg(path: str) -> dict[str, list[list[float]]]:
    for a in range(5):
        try:
            r = httpx.get(f"https://api.coingecko.com/api/v3/{path}", timeout=20)
            if r.status_code == 200:
                return dict(r.json())
            time.sleep(3 * (a + 1))  # 429 throttle backoff
        except httpx.HTTPError:
            time.sleep(3 * (a + 1))
    return {}


def _daily_mcap(cid: str) -> dict[int, float]:
    j = _cg(f"coins/{cid}/market_chart?vs_currency=usd&days=365&interval=daily")
    out: dict[int, float] = {}
    for ts, v in j.get("market_caps", []):
        out[int(ts) // 86_400_000] = float(v)  # ключ — день
    return out


def _daily_price(cid: str) -> dict[int, float]:
    j = _cg(f"coins/{cid}/market_chart?vs_currency=usd&days=365&interval=daily")
    out: dict[int, float] = {}
    for ts, v in j.get("prices", []):
        out[int(ts) // 86_400_000] = float(v)
    return out


def main() -> None:
    usdt = _daily_mcap("tether")
    time.sleep(2)
    usdc = _daily_mcap("usd-coin")
    time.sleep(2)
    btc = _daily_price("bitcoin")
    if not (usdt and usdc and btc):
        print("CoinGecko недоступен/throttled — разведка не выполнена (no-op)")
        return
    days = sorted(set(usdt) & set(usdc) & set(btc))
    if len(days) < 120:
        print(f"мало общих дней: {len(days)}")
        return
    stbl = [usdt[d] + usdc[d] for d in days]
    px = [btc[d] for d in days]
    # Недельный шаг (7 дней). Сигнал: 4-нед изменение стейбл-supply.
    # Вход лонг BTC на след. неделю если стейблы расширяются, иначе флэт.
    W = 7
    LB = 4  # недель оглядки supply
    rets_sig: list[float] = []
    rets_bh: list[float] = []
    idx = list(range(0, len(days) - W, W))
    for n, i in enumerate(idx):
        if n < LB or i + W >= len(px):
            continue
        s_now = stbl[i]
        s_past = stbl[idx[n - LB]]
        fwd = px[i + W] / px[i] - 1.0
        rets_bh.append(fwd)
        expanding = s_past > 0 and (s_now / s_past - 1.0) > 0
        rets_sig.append(fwd if expanding else 0.0)

    def stats(r: list[float], tag: str) -> str:
        if len(r) < 8:
            return f"{tag}: n={len(r)} мало"
        n = len(r)
        m = sum(r) / n
        sd = math.sqrt(sum((x - m) ** 2 for x in r) / (n - 1))
        sh = m / sd * math.sqrt(52) if sd > 0 else 0.0
        t = m / (sd / math.sqrt(n)) if sd > 0 else 0.0
        p = math.erfc(abs(t) / math.sqrt(2))
        eq = 1.0
        for x in r:
            eq *= 1 + x
        return (
            f"{tag}: нед={n:3d} Sharpe={sh:+5.2f} t={t:+4.2f} "
            f"p={p:.3f} итогPnL={(eq - 1) * 100:+7.1f}%"
        )

    # корреляция Δsupply(4w) ↔ forward BTC return
    dsup = []
    fwd_list = []
    for n, i in enumerate(idx):
        if n < LB or i + W >= len(px):
            continue
        dsup.append(stbl[i] / stbl[idx[n - LB]] - 1.0)
        fwd_list.append(px[i + W] / px[i] - 1.0)
    if len(dsup) > 3:
        md = sum(dsup) / len(dsup)
        mf = sum(fwd_list) / len(fwd_list)
        cov = sum((dsup[k] - md) * (fwd_list[k] - mf) for k in range(len(dsup)))
        sdd = math.sqrt(sum((x - md) ** 2 for x in dsup))
        sdf = math.sqrt(sum((x - mf) ** 2 for x in fwd_list))
        corr = cov / (sdd * sdf) if sdd > 0 and sdf > 0 else 0.0
    else:
        corr = 0.0

    print("РАЗВЕДКА: стейбл-supply (USDT+USDC) → форвард BTC, 365 дней")
    print(f"Общих дней: {len(days)} | период покрыт ~1 режим (НЕ валидация)")
    print("-" * 64)
    print(stats(rets_bh, "BUY&HOLD BTC      "))
    print(stats(rets_sig, "ЛОНГ при ↑стейблов"))
    print(f"corr(Δsupply 4нед, фвд BTC 1нед) = {corr:+.3f}")
    print(
        "\n⚠️ 1 год = 1 режим. Любой плюс тут НЕ edge (ловушка одного\n"
        "режима, как funding). Это лишь индикатор: есть ли смысл\n"
        "платить за многолетнюю историю стейбл-потоков."
    )


if __name__ == "__main__":
    main()

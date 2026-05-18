"""Разведочный экран бота «трейдер» по списку символов.

НЕ валидация. Прогоняет liquidation_reversal + трейдер/стратегии/
композит-btc.yaml (oi_gate_enabled=false) на BingX 4h ~7 мес, сверяет
с трейдер/стратегии/экран-минимум.yaml. Запуск из корня репо в venv:

    python -m трейдер.стратегии.screen   # (или python трейдер/стратегии/screen.py)
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
THRESH = yaml.safe_load((ROOT / "трейдер/стратегии/экран-минимум.yaml").read_text("utf-8"))
STRAT_CFG = "трейдер/стратегии/композит-btc.yaml"
OUT_MD = ROOT / "трейдер/ретро/экран-favorites-2026-05-18.md"

# Крипто-перпы из избранного (BingX SYMBOL-USDT). Не-крипта вынесена в SKIP.
CRYPTO = [
    "BTC", "ETH", "SOL", "XRP", "BNB", "DOGE", "LINK", "ZEC", "AXS",
    "HYPE", "JUP", "GUN", "TNSR", "FARTCOIN", "PIPPIN", "ALTCOIN",
    "STABLE", "ACU", "RIVER", "XAUT",
]
SKIP = {
    "USDJPY": "FX — нет фида ликвидаций Coinglass",
    "GOLD(XAU)": "сырьё — нет фида",
    "Copper(XCU)": "сырьё — нет фида",
    "Heating Oil": "сырьё — нет фида",
    "NASDAQ100": "индекс — нет фида",
    "DowJones": "индекс — нет фида",
    "SP500": "индекс — нет фида",
    "NVDA": "токен-акция — нет фида",
    "GOOGL": "токен-акция — нет фида",
    "TSLA": "токен-акция — нет фида",
    "AAPL": "токен-акция — нет фида",
    "AAPLX": "токен-акция — нет фида",
    "MSTR": "токен-акция — нет фида",
    "META": "токен-акция — нет фида",
    "币安人生": "не идентифицирован тикер",
}


def run(cmd: list[str]) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=600)
    return p.returncode, p.stdout + p.stderr


def screen_one(sym: str) -> dict:
    pair = f"{sym}-USDT"
    rc, out = run([sys.executable, "-m", "scripts.download_klines",
                   "--symbol", pair, "--interval", "4h", "--months", "7"])
    candles = ROOT / f"data/candles/{pair.lower()}-4h.jsonl"
    if not candles.exists() or candles.stat().st_size == 0:
        return {"symbol": pair, "status": "Н/Д", "note": "нет свечей BingX"}
    n_candles = sum(1 for _ in candles.open())
    rc, out = run([sys.executable, "-m", "scripts.run_backtest",
                   "--strategy", "liquidation_reversal",
                   "--strategy-config", STRAT_CFG,
                   "--candles", str(candles), "--symbol", pair])
    m = re.search(r"ops/backtest-single-\d+\.json", out)
    if not m:
        return {"symbol": pair, "status": "ERR", "note": out.strip()[-200:]}
    s = json.loads((ROOT / m.group(0)).read_text())["summary"]
    t = int(s["total_trades"])
    if t == 0:
        return {"symbol": pair, "status": "Н/Д",
                "note": f"0 сделок ({n_candles} свечей; нет данных ликвидаций/сигналов)"}
    pf = float(s["profit_factor"]); sr = float(s["sharpe_ratio"])
    dd = float(s["max_drawdown_pct"]); pnl = float(s["total_pnl_pct"])
    ok = (t >= THRESH["min_trades"] and pf >= THRESH["min_profit_factor"]
          and sr >= THRESH["min_sharpe"] and dd <= THRESH["max_drawdown_pct"]
          and pnl > THRESH["min_total_pnl_pct"])
    return {"symbol": pair, "status": "PASS" if ok else "FAIL",
            "trades": t, "pf": pf, "sharpe": sr, "dd": dd, "pnl": pnl,
            "candles": n_candles}


def main() -> None:
    rows = [screen_one(s) for s in CRYPTO]
    lines = [
        "# Экран по избранному (favorites) — 2026-05-18",
        "",
        "⚠️ Разведочный экран, НЕ валидация (план 01 §6b). Без OI-гейта, "
        "BingX 4h ~7 мес, Coinglass liq на этом ключе ограничен.",
        "",
        f"Порог: сделок≥{THRESH['min_trades']}, PF≥{THRESH['min_profit_factor']}, "
        f"Sharpe≥{THRESH['min_sharpe']}, DD≤{THRESH['max_drawdown_pct']}%, P&L>0.",
        "",
        "| Символ | Статус | Сделок | PF | Sharpe | MaxDD% | P&L% | Прим. |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        if r["status"] in ("PASS", "FAIL"):
            lines.append(
                f"| {r['symbol']} | {r['status']} | {r['trades']} | "
                f"{r['pf']:.2f} | {r['sharpe']:.2f} | {r['dd']:.2f} | "
                f"{r['pnl']:.2f} | {r['candles']} свечей |")
        else:
            lines.append(
                f"| {r['symbol']} | {r['status']} | — | — | — | — | — | "
                f"{r.get('note','')} |")
    lines += ["", "## Вне зоны стратегии (нет фида ликвидаций Coinglass)", ""]
    for k, v in SKIP.items():
        lines.append(f"- **{k}** — {v}")
    OUT_MD.write_text("\n".join(lines) + "\n", "utf-8")
    print(f"written {OUT_MD}")
    print("\n".join(lines))


if __name__ == "__main__":
    main()

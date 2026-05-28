"""Скачать данные один раз в CSV, чтобы все модели бэктестились на
идентичном наборе. Запуск из venv, где есть yfinance (kronos_integration).

    kronos_integration/.venv/bin/pip install -q yfinance
    kronos_integration/.venv/bin/python forecast_bench/fetch_data.py BTC-USD
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import yfinance as yf

OUT = Path(__file__).resolve().parent / "data"


def main() -> None:
    symbol = sys.argv[1] if len(sys.argv) > 1 else "BTC-USD"
    period = sys.argv[2] if len(sys.argv) > 2 else "120d"
    raw = yf.download(symbol, period=period, interval="1h", progress=False, auto_adjust=False)
    raw.columns = [c[0].lower() if isinstance(c, tuple) else c.lower() for c in raw.columns]
    df = raw[["open", "high", "low", "close", "volume"]].dropna().reset_index()
    tcol = df.columns[0]
    df = df.rename(columns={tcol: "timestamp"})
    df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.tz_localize(None)
    OUT.mkdir(exist_ok=True)
    path = OUT / f"{symbol.replace('=', '').replace('^', '')}_1h.csv"
    df.to_csv(path, index=False)
    print(f"saved {len(df)} rows -> {path}")
    print(df.tail(2).to_string())


if __name__ == "__main__":
    main()

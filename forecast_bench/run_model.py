"""Walk-forward прогон одной модели на общем CSV. Запускается из venv
соответствующей песочницы.

    kronos_integration/.venv/bin/python  forecast_bench/run_model.py --model kronos  ...
    timesfm_integration/.venv/bin/python forecast_bench/run_model.py --model timesfm ...
    chronos_integration/.venv/bin/python forecast_bench/run_model.py --model chronos ...

Для каждого окна: контекст из LOOKBACK баров, прогноз close на HORIZON
вперёд. Пишет CSV: timestamp, last_close, target, pred_close.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OHLCV = ["open", "high", "low", "close", "volume"]


def predict_close_at_horizon(model_name, fc, df_ctx, ts_ctx, horizon):
    """Вернуть прогноз close на шаге `horizon` для заданного контекста."""
    if model_name == "kronos":
        x_df = df_ctx[OHLCV].reset_index(drop=True).astype("float64")
        x_ts = ts_ctx.reset_index(drop=True)
        step = ts_ctx.diff().median()
        y_ts = pd.Series([x_ts.iloc[-1] + step * (i + 1) for i in range(horizon)])
        p = fc.predict(
            df=x_df, x_timestamp=x_ts, y_timestamp=y_ts,
            pred_len=horizon, T=1.0, top_p=0.9, sample_count=1,
        )
        return float(p["close"].iloc[-1])
    if model_name == "timesfm":
        series = df_ctx["close"].to_numpy(dtype=np.float32)
        f = fc.forecast_one(series, freq=1)  # 1 = hourly
        return float(f.point[horizon - 1])
    if model_name == "chronos":
        series = df_ctx["close"].to_numpy(dtype=np.float32)
        f = fc.forecast_one(series, prediction_length=horizon)
        return float(f.point[horizon - 1])
    raise ValueError(model_name)


def load_model(model_name, lookback, horizon):
    if model_name == "kronos":
        sys.path.insert(0, str(ROOT / "kronos_integration"))
        from forecaster import KronosForecaster  # noqa: PLC0415
        return KronosForecaster(max_context=512, device="cpu")
    if model_name == "timesfm":
        sys.path.insert(0, str(ROOT / "timesfm_integration"))
        from forecaster import TimesFMForecaster  # noqa: PLC0415
        return TimesFMForecaster(horizon_len=horizon, context_len=lookback, backend="cpu")
    if model_name == "chronos":
        sys.path.insert(0, str(ROOT / "chronos_integration"))
        from forecaster import ChronosForecaster  # noqa: PLC0415
        return ChronosForecaster(device="cpu")
    raise ValueError(model_name)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, choices=["kronos", "timesfm", "chronos"])
    ap.add_argument("--csv", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--lookback", type=int, default=256)
    ap.add_argument("--horizon", type=int, default=12)
    ap.add_argument("--windows", type=int, default=120)
    args = ap.parse_args()

    df = pd.read_csv(args.csv, parse_dates=["timestamp"])
    close = df["close"].to_numpy()
    total = len(df)
    start_e = total - args.horizon - args.windows
    if start_e < args.lookback:
        raise SystemExit(f"мало данных: total={total}")

    fc = load_model(args.model, args.lookback, args.horizon)
    rows = []
    for k in range(args.windows):
        e = start_e + k
        ctx = slice(e - args.lookback, e)
        last_close = float(close[e - 1])
        target = float(close[e - 1 + args.horizon])
        pred = predict_close_at_horizon(
            args.model, fc, df.iloc[ctx], df["timestamp"].iloc[ctx], args.horizon
        )
        rows.append(
            {
                "timestamp": df["timestamp"].iloc[e - 1],
                "last_close": last_close,
                "target": target,
                "pred_close": pred,
            }
        )
        if (k + 1) % 20 == 0:
            print(f"  [{args.model}] {k + 1}/{args.windows}", flush=True)

    out = pd.DataFrame(rows)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.out, index=False)
    print(f"[{args.model}] saved {len(out)} -> {args.out}")


if __name__ == "__main__":
    main()

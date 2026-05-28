"""Smoke-тест Kronos-обёртки.

Запуск (из песочницы, после install.sh):
    kronos_integration/.venv/bin/python kronos_integration/example.py

Первый прогон скачает веса с HuggingFace (Kronos-small ~50 МБ +
Tokenizer-base), кэшируется в ``~/.cache/huggingface/``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from forecaster import OHLCV_COLS, KronosForecaster


def _synthetic_ohlcv(n: int, freq: str = "5min") -> pd.DataFrame:
    """Синтетические свечи: трендовая синусоида + шум, корректный OHLC."""
    rng = np.random.default_rng(42)
    t = np.arange(n)
    close = 100 + 0.02 * t + 3 * np.sin(2 * np.pi * t / 48) + rng.normal(0, 0.5, n)
    open_ = np.concatenate([[close[0]], close[:-1]])
    high = np.maximum(open_, close) + rng.uniform(0, 1, n)
    low = np.minimum(open_, close) - rng.uniform(0, 1, n)
    volume = rng.uniform(1000, 5000, n)
    amount = volume * close
    ts = pd.date_range("2024-01-01", periods=n, freq=freq)
    df = pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "amount": amount,
        }
    )
    return df, pd.Series(ts)


def main() -> None:
    lookback, pred_len = 400, 120
    print("Init Kronos (первый раз скачает веса с HuggingFace)...")
    fc = KronosForecaster(max_context=512, device="cpu")
    print(
        f"Device: {fc._device}, model={fc._model_name}, "
        f"tokenizer={fc._tokenizer_name}"
    )

    df, ts = _synthetic_ohlcv(lookback + pred_len)
    x_df = df.loc[: lookback - 1, OHLCV_COLS]
    x_timestamp = ts.loc[: lookback - 1]
    y_timestamp = ts.loc[lookback : lookback + pred_len - 1]

    print(f"\nЗапуск predict (lookback={lookback}, pred_len={pred_len})...")
    pred = fc.predict(
        df=x_df,
        x_timestamp=x_timestamp,
        y_timestamp=y_timestamp,
        pred_len=pred_len,
        T=1.0,
        top_p=0.9,
        sample_count=1,
    )

    print("Готово. Сводка прогноза:")
    print(f"  shape       = {pred.shape}")
    print(f"  columns     = {list(pred.columns)}")
    print(f"  close[:5]   = {pred['close'].head().round(2).tolist()}")
    print(f"  last input  = {x_df['close'].tail(3).round(2).tolist()}")

    assert len(pred) == pred_len, f"len(pred)={len(pred)}, ожидалось {pred_len}"
    assert "close" in pred.columns
    assert np.isfinite(pred["close"]).all(), "close содержит NaN/Inf"
    print("\nSmoke-тест: OK")


if __name__ == "__main__":
    main()

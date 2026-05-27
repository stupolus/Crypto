"""Smoke test: load TimesFM, forecast a synthetic price-like series.

Run: python timesfm_integration/example.py
First run downloads ~2 GB from HuggingFace.
"""

import warnings
warnings.filterwarnings("ignore")

import numpy as np

from forecaster import TimesFMForecaster, FREQ_HIGH


def main() -> None:
    np.random.seed(42)
    t = np.arange(200)
    btc_like = 30000 + 500 * np.sin(t / 10) + t * 50 + np.random.randn(200) * 200

    print("Loading TimesFM (first run downloads ~2 GB)...")
    fc = TimesFMForecaster(horizon_len=12)

    result = fc.forecast_one(btc_like, freq=FREQ_HIGH)

    print(f"Last historical value: {btc_like[-1]:.2f}")
    print(f"Forecast (12 steps):   {np.round(result.point, 2)}")
    print(f"P10 (pessimistic):     {np.round(result.p10, 2)}")
    print(f"P90 (optimistic):      {np.round(result.p90, 2)}")
    print("\nSmoke test OK.")


if __name__ == "__main__":
    main()

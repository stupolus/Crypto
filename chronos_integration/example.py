"""Smoke-тест Chronos-обёртки.

Запуск (из песочницы, после install.sh):
    chronos_integration/.venv/bin/python chronos_integration/example.py

Первый прогон скачает веса с HuggingFace (chronos-bolt-base),
кэшируется в ``~/.cache/huggingface/``.
"""

from __future__ import annotations

import numpy as np

from forecaster import ChronosForecaster


def main() -> None:
    print("Init Chronos (первый раз скачает веса с HuggingFace)...")
    fc = ChronosForecaster(device="cpu")
    print(f"Device: {fc._device}, model={fc._model_name}")

    rng = np.random.default_rng(42)
    t = np.arange(600)
    series = 100 + 0.05 * t + 5 * np.sin(2 * np.pi * t / 30) + rng.normal(0, 1, size=600)

    print("\nЗапуск forecast_one (horizon=24)...")
    f = fc.forecast_one(series.astype(np.float32), prediction_length=24)

    print("Готово. Сводка прогноза:")
    print(f"  point[0:5]  = {f.point[:5].round(2).tolist()}")
    print(f"  p10[0:5]    = {f.p10[:5].round(2).tolist()}")
    print(f"  p90[0:5]    = {f.p90[:5].round(2).tolist()}")
    print(f"  last input  = {series[-3:].round(2).tolist()}")

    assert f.point.shape == (24,), f"point.shape={f.point.shape}, ожидалось (24,)"
    assert np.isfinite(f.point).all(), "point содержит NaN/Inf"
    assert np.isfinite(f.p10).all() and np.isfinite(f.p90).all()
    print(f"  средняя ширина 80% интервала: {float((f.p90 - f.p10).mean()):.2f}")
    print("\nSmoke-тест: OK")


if __name__ == "__main__":
    main()

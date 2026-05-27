"""Smoke-тест TimesFM-обёртки.

Запуск: ``python timesfm_integration/example.py``

Первый прогон скачает ~2 ГБ с HuggingFace (`google/timesfm-2.0-500m-pytorch`),
кэшируется в `~/.cache/huggingface/`. Последующие запуски — мгновенно.
"""

from __future__ import annotations

import numpy as np

from forecaster import TimesFMForecaster


def main() -> None:
    print("Init TimesFM (первый раз скачает ~2 ГБ)...")
    fc = TimesFMForecaster(horizon_len=24, context_len=512, backend="cpu")
    print(f"Backend: {fc._backend}, horizon={fc._horizon_len}, context={fc._context_len}")

    # Синтетика: трендовая синусоида с шумом.
    rng = np.random.default_rng(42)
    t = np.arange(600)
    series = 100 + 0.05 * t + 5 * np.sin(2 * np.pi * t / 30) + rng.normal(0, 1, size=600)

    print("\nЗапуск forecast_one...")
    f = fc.forecast_one(series.astype(np.float32), freq=0)

    print("Готово. Сводка прогноза (горизонт 24):")
    print(f"  point[0:5]  = {f.point[:5].round(2).tolist()}")
    print(f"  p10[0:5]    = {f.p10[:5].round(2).tolist()}")
    print(f"  p90[0:5]    = {f.p90[:5].round(2).tolist()}")
    print(f"  point[-3:]  = {f.point[-3:].round(2).tolist()}")
    print(f"  last input  = {series[-3:].round(2).tolist()}")
    # Минимальные инварианты: shape + конечные числа. Соотношение
    # квантилей и point иногда нарушается в зонах низкой неопределённости
    # (mean-head ≠ quantile-head), поэтому строгое p10≤point≤p90 не
    # ассертим — печатаем средний интервал для глаз.
    assert f.point.shape == (24,), f"point.shape={f.point.shape}, ожидалось (24,)"
    assert f.p10.shape == (24,)
    assert f.p90.shape == (24,)
    assert np.isfinite(f.point).all(), "point содержит NaN/Inf"
    assert np.isfinite(f.p10).all() and np.isfinite(f.p90).all()
    interval_w = float((f.p90 - f.p10).mean())
    print(f"  средняя ширина 80% интервала: {interval_w:.2f}")
    print("\nSmoke-тест: OK")


if __name__ == "__main__":
    main()

"""Chronos forecaster — синглтон-обёртка над Amazon Chronos.

Песочница. Не интегрируется в основной код проекта до явного «да»
владельца — см. chronos_integration/README.md.

Chronos — universal (univariate) TSFM: прогнозирует один ряд (например,
``close``), не свечу целиком (в отличие от Kronos). По умолчанию
``amazon/chronos-bolt-base`` — быстрый CPU-вариант.
"""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Any, ClassVar

import numpy as np


@dataclass(frozen=True)
class Forecast:
    """Прогноз для одного ряда: point + квантили p10/p90."""

    point: np.ndarray  # shape (prediction_length,)
    p10: np.ndarray
    p90: np.ndarray


class ChronosForecaster:
    """Синглтон: пайплайн грузится один раз, переиспользуется."""

    _instance: ClassVar[ChronosForecaster | None] = None
    _lock: ClassVar[Lock] = Lock()

    def __new__(
        cls,
        model_name: str = "amazon/chronos-bolt-base",
        device: str = "cpu",
    ) -> ChronosForecaster:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    inst = super().__new__(cls)
                    inst._init_model(model_name, device)
                    cls._instance = inst
        return cls._instance

    def _init_model(self, model_name: str, device: str) -> None:
        # Импорты внутри: чтобы import модуля не падал, если chronos не
        # установлен (например, до install.sh).
        import torch  # noqa: PLC0415
        from chronos import BaseChronosPipeline  # noqa: PLC0415

        self._model_name = model_name
        self._device = device
        self._pipeline = BaseChronosPipeline.from_pretrained(
            model_name, device_map=device, torch_dtype=torch.float32
        )

    def forecast_one(self, series: np.ndarray, prediction_length: int = 24) -> Forecast:
        """Прогноз для одного ряда."""
        return self.forecast_batch([series], prediction_length=prediction_length)[0]

    def forecast_batch(
        self, series_list: list[np.ndarray], prediction_length: int = 24
    ) -> list[Forecast]:
        """Прогноз для батча рядов (point=median, + p10/p90)."""
        import torch  # noqa: PLC0415

        contexts = [
            torch.tensor(np.asarray(s, dtype=np.float32)) for s in series_list
        ]
        quantiles, _mean = self._pipeline.predict_quantiles(
            inputs=contexts,
            prediction_length=prediction_length,
            quantile_levels=[0.1, 0.5, 0.9],
        )
        # quantiles shape: (batch, prediction_length, 3) — p10, p50, p90.
        q = quantiles.cpu().numpy()
        out: list[Forecast] = []
        for i in range(len(series_list)):
            out.append(
                Forecast(
                    point=q[i][:, 1],  # median
                    p10=q[i][:, 0],
                    p90=q[i][:, 2],
                )
            )
        return out

    @property
    def pipeline(self) -> Any:
        """Доступ к raw-пайплайну (для отладки/расширенного API)."""
        return self._pipeline

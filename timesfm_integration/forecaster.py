"""TimesFM forecaster — синглтон-обёртка над Google TimesFM v2.0 (500M).

Песочница. Не интегрируется в основной код проекта до явного «да»
владельца — см. timesfm_integration/README.md.

Чекпоинт: ``google/timesfm-2.0-500m-pytorch`` (v2.0 требует
``num_layers=50``, ``use_positional_embedding=False``).
"""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Any, ClassVar

import numpy as np


@dataclass(frozen=True)
class Forecast:
    """Прогноз для одного ряда: point + квантили p10/p90."""

    point: np.ndarray  # shape (horizon_len,)
    p10: np.ndarray
    p90: np.ndarray


class TimesFMForecaster:
    """Синглтон: модель грузится один раз, переиспользуется."""

    _instance: ClassVar[TimesFMForecaster | None] = None
    _lock: ClassVar[Lock] = Lock()

    def __new__(
        cls,
        horizon_len: int = 24,
        context_len: int = 512,
        backend: str = "cpu",
    ) -> TimesFMForecaster:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    inst = super().__new__(cls)
                    inst._init_model(horizon_len, context_len, backend)
                    cls._instance = inst
        return cls._instance

    def _init_model(self, horizon_len: int, context_len: int, backend: str) -> None:
        # Импорты внутри: чтобы import модуля не падал, если timesfm не
        # установлен (например, при `uninstall.sh` без удаления файла).
        import timesfm  # noqa: PLC0415

        self._horizon_len = horizon_len
        self._context_len = context_len
        self._backend = backend
        self._model = timesfm.TimesFm(
            hparams=timesfm.TimesFmHparams(
                backend=backend,
                horizon_len=horizon_len,
                context_len=context_len,
                num_layers=50,  # v2.0 hard-требование
                use_positional_embedding=False,  # v2.0 hard-требование
            ),
            checkpoint=timesfm.TimesFmCheckpoint(
                huggingface_repo_id="google/timesfm-2.0-500m-pytorch",
            ),
        )

    def forecast_one(self, series: np.ndarray, freq: int = 0) -> Forecast:
        """Прогноз для одного ряда."""
        return self.forecast_batch([series], freq=freq)[0]

    def forecast_batch(
        self, series_list: list[np.ndarray], freq: int = 0
    ) -> list[Forecast]:
        """Прогноз для батча рядов. freq: 0=daily, 1=hourly, 2=intraday-mins."""
        inputs = [np.asarray(s, dtype=np.float32) for s in series_list]
        freqs = [freq] * len(inputs)
        point, quantiles = self._model.forecast(inputs, freq=freqs)
        # quantiles shape: (batch, horizon, 10) — 10%, 20%, ..., 90% (по
        # сетке 1..9 децилей). p10 = idx 0, p90 = idx 8.
        out: list[Forecast] = []
        for i in range(len(inputs)):
            out.append(
                Forecast(
                    point=np.asarray(point[i]),
                    p10=np.asarray(quantiles[i][:, 0]),
                    p90=np.asarray(quantiles[i][:, 8]),
                )
            )
        return out

    @property
    def model(self) -> Any:
        """Доступ к raw-модели (для отладки/расширенного API)."""
        return self._model

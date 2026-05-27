"""TimesFM wrapper for the Crypto bot.

Single import point for any module that wants probabilistic forecasts of
a univariate series (price, volume, funding rate, etc).

The model is heavy (~2 GB checkpoint, ~10s cold start on CPU) — instantiate
the forecaster ONCE per process and reuse it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
import timesfm


FREQ_HIGH = 0  # minutes, hours, daily candles
FREQ_MID = 1   # weekly
FREQ_LOW = 2   # monthly, quarterly


@dataclass
class Forecast:
    point: np.ndarray  # median forecast, shape (horizon,)
    p10: np.ndarray    # 10th percentile (pessimistic bound)
    p90: np.ndarray    # 90th percentile (optimistic bound)


class TimesFMForecaster:
    def __init__(
        self,
        horizon_len: int = 24,
        context_len: int = 512,
        backend: str = "cpu",
        batch_size: int = 8,
        repo_id: str = "google/timesfm-2.0-500m-pytorch",
    ):
        self.tfm = timesfm.TimesFm(
            hparams=timesfm.TimesFmHparams(
                backend=backend,
                per_core_batch_size=batch_size,
                horizon_len=horizon_len,
                context_len=context_len,
                num_layers=50,
                use_positional_embedding=False,
            ),
            checkpoint=timesfm.TimesFmCheckpoint(huggingface_repo_id=repo_id),
        )

    def forecast_one(self, series: Sequence[float], freq: int = FREQ_HIGH) -> Forecast:
        point, quantiles = self.tfm.forecast(
            [np.asarray(series, dtype=np.float32)], freq=[freq]
        )
        return Forecast(
            point=point[0],
            p10=quantiles[0][:, 1],
            p90=quantiles[0][:, 9],
        )

    def forecast_batch(
        self,
        series_list: Sequence[Sequence[float]],
        freq: int = FREQ_HIGH,
    ) -> list[Forecast]:
        arrays = [np.asarray(s, dtype=np.float32) for s in series_list]
        point, quantiles = self.tfm.forecast(arrays, freq=[freq] * len(arrays))
        return [
            Forecast(point=point[i], p10=quantiles[i][:, 1], p90=quantiles[i][:, 9])
            for i in range(len(arrays))
        ]

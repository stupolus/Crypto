"""Kronos forecaster — синглтон-обёртка над Kronos (foundation-модель
для финансовых свечей / K-line, OHLCV).

Песочница. Не интегрируется в основной код проекта до явного «да»
владельца — см. kronos_integration/README.md.

Чекпоинты по умолчанию: токенизатор ``NeoQuasar/Kronos-Tokenizer-base``
+ модель ``NeoQuasar/Kronos-small`` (24.7M). Альтернативы: ``Kronos-mini``
(+ ``Kronos-Tokenizer-2k``), ``Kronos-base``.

Kronos не pip-пакет: его API доступен только из исходников репозитория,
которые install.sh клонирует в ``kronos_integration/Kronos/``. Этот модуль
добавляет ту папку в ``sys.path`` перед импортом ``model``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from threading import Lock
from typing import Any, ClassVar

import pandas as pd

# OHLCV(+amount) — колонки, которые ждёт Kronos.predict.
OHLCV_COLS = ["open", "high", "low", "close", "volume", "amount"]

# Исходники Kronos (клонируются install.sh, в .gitignore).
_KRONOS_SRC = Path(__file__).resolve().parent / "Kronos"


def _ensure_kronos_on_path() -> None:
    if not _KRONOS_SRC.exists():
        raise RuntimeError(
            f"Исходники Kronos не найдены в {_KRONOS_SRC}. "
            "Сначала запусти kronos_integration/install.sh."
        )
    if str(_KRONOS_SRC) not in sys.path:
        sys.path.insert(0, str(_KRONOS_SRC))


class KronosForecaster:
    """Синглтон: токенизатор+модель грузятся один раз, переиспользуются."""

    _instance: ClassVar[KronosForecaster | None] = None
    _lock: ClassVar[Lock] = Lock()

    def __new__(
        cls,
        model_name: str = "NeoQuasar/Kronos-small",
        tokenizer_name: str = "NeoQuasar/Kronos-Tokenizer-base",
        max_context: int = 512,
        device: str | None = "cpu",
    ) -> KronosForecaster:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    inst = super().__new__(cls)
                    inst._init_model(model_name, tokenizer_name, max_context, device)
                    cls._instance = inst
        return cls._instance

    def _init_model(
        self,
        model_name: str,
        tokenizer_name: str,
        max_context: int,
        device: str | None,
    ) -> None:
        # Импорты внутри: чтобы import модуля не падал, если исходники
        # Kronos ещё не склонированы (например, до install.sh).
        _ensure_kronos_on_path()
        from model import Kronos, KronosPredictor, KronosTokenizer  # noqa: PLC0415

        self._model_name = model_name
        self._tokenizer_name = tokenizer_name
        self._max_context = max_context
        self._device = device

        tokenizer = KronosTokenizer.from_pretrained(tokenizer_name)
        model = Kronos.from_pretrained(model_name)
        self._predictor = KronosPredictor(
            model, tokenizer, device=device, max_context=max_context
        )

    def predict(
        self,
        df: pd.DataFrame,
        x_timestamp: pd.Series,
        y_timestamp: pd.Series,
        pred_len: int,
        *,
        T: float = 1.0,
        top_k: int = 0,
        top_p: float = 0.9,
        sample_count: int = 1,
        verbose: bool = False,
    ) -> pd.DataFrame:
        """Прогноз будущих свечей.

        :param df: контекст — DataFrame с колонками OHLCV (``open``,
            ``high``, ``low``, ``close``, ``volume``, опционально ``amount``).
        :param x_timestamp: метки времени контекста (len == len(df)).
        :param y_timestamp: метки времени горизонта (len == pred_len).
        :param pred_len: число будущих периодов.
        :param T: температура сэмплирования.
        :param top_k / top_p: nucleus-сэмплирование.
        :param sample_count: сколько траекторий усреднить.
        :return: DataFrame прогноза с теми же колонками, что и ``df``.
        """
        return self._predictor.predict(
            df=df,
            x_timestamp=x_timestamp,
            y_timestamp=y_timestamp,
            pred_len=pred_len,
            T=T,
            top_k=top_k,
            top_p=top_p,
            sample_count=sample_count,
            verbose=verbose,
        )

    @property
    def predictor(self) -> Any:
        """Доступ к raw KronosPredictor (для отладки/расширенного API)."""
        return self._predictor

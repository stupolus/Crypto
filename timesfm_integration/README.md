# TimesFM integration (sandbox)

Изолированная песочница для Google TimesFM v2.0 (500M) —
foundation-модели прогноза временных рядов
([github](https://github.com/google-research/timesfm)).

**Статус:** sandbox. **В основной код проекта НЕ интегрировано.** До
явного «да» владельца (с указанием конкретной точки кода) — обёртка
запускается только отдельно через `example.py`.

## Архитектура

Чтобы оставить главный проектный `.venv` чистым, песочница использует
**свой собственный venv** внутри папки — `timesfm_integration/.venv/`
(Python 3.11, в .gitignore). Удаление = `rm -rf timesfm_integration/`.

## Установка

Требуется `python3.11` в системе (TimesFM v1.2.x не поддерживает 3.12+).

```bash
python3.11 -m venv timesfm_integration/.venv
timesfm_integration/.venv/bin/pip install --upgrade pip
timesfm_integration/.venv/bin/pip install -r timesfm_integration/requirements.txt
```

Что тянет:
- `torch==2.12.0+cpu` (~700 МБ) с pytorch.org CPU-индекса.
- `timesfm` из тега [`v1.2.6`](https://github.com/google-research/timesfm/releases/tag/v1.2.6) (`v1.3.0` из ТЗ не существует ни на PyPI, ни на GitHub — взят самый свежий стабильный тег; package version 1.2.5).
- `jax[cpu]` — TimesFM импортирует `jax` безусловно даже на PyTorch-бэкенде (`xreg_lib`).
- HuggingFace-кэш модели `google/timesfm-2.0-500m-pytorch` (~2 ГБ) скачается при первом запуске в `~/.cache/huggingface/`.

## Smoke-тест

```bash
timesfm_integration/.venv/bin/python timesfm_integration/example.py
```
Печатает прогноз на синтетике + проверяет shape + конечность чисел.

## Использование (из песочницы)

```python
import numpy as np
from forecaster import TimesFMForecaster  # запуск из timesfm_integration/

fc = TimesFMForecaster(horizon_len=24, context_len=512, backend="cpu")
series = np.array([...], dtype=np.float32)  # одномерный ряд
f = fc.forecast_one(series, freq=0)  # 0=daily, 1=hourly, 2=intraday-mins
# f.point — точечный прогноз (np.ndarray, shape=(24,))
# f.p10, f.p90 — нижний/верхний дециль (для интервала неопределённости)
```

Batch:
```python
forecasts = fc.forecast_batch([series1, series2, ...], freq=0)
```

## Удаление (одна команда)

```bash
bash timesfm_integration/uninstall.sh && git rm -r timesfm_integration && git commit -m "Remove TimesFM"
```

Что делает `uninstall.sh`:
1. Удаляет HF-кэш модели (~2 ГБ): `~/.cache/huggingface/hub/models--google--timesfm-2.0-500m-pytorch`.
2. Печатает напоминание про `git rm -r timesfm_integration` для полной зачистки.

Главный проектный `.venv` НЕ трогается (TimesFM туда вообще не ставился).

## Жёсткое правило (CLAUDE.md п.1/4/6)

TimesFM здесь — **инфраструктура для эксперимента**, не валидированный
edge. Прежде чем кормить ей реальные данные проекта и использовать
прогноз в стратегии — отдельный план в `plans/`, бэктест, OOS+WF+cost.
Сейчас это только foundation-модель с предобученными весами Google.

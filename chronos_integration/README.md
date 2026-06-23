# Chronos integration (sandbox)

Изолированная песочница для **Chronos** (Amazon) — универсальной
foundation-модели прогноза временных рядов
([github](https://github.com/amazon-science/chronos-forecasting)).

В отличие от Kronos (свечи OHLCV целиком), Chronos — **univariate**:
прогнозирует один ряд (например, `close`). По умолчанию
`amazon/chronos-bolt-base` — быстрый CPU-вариант.

**Статус:** sandbox. **В основной код проекта НЕ интегрировано.** До
явного «да» владельца (с указанием конкретной точки кода) — обёртка
запускается только отдельно через `example.py`.

## Архитектура

Свой venv внутри папки — `chronos_integration/.venv/` (в .gitignore).
Chronos — pip-пакет (`chronos-forecasting`), клонировать ничего не нужно.
Удаление = `rm -rf chronos_integration/`.

## Установка

Требуется `python3.10`+.

```bash
bash chronos_integration/install.sh
```

Веса скачаются с HuggingFace при первом запуске в `~/.cache/huggingface/`.

## Smoke-тест

```bash
chronos_integration/.venv/bin/python chronos_integration/example.py
```

## Использование (из песочницы)

```python
import numpy as np
from forecaster import ChronosForecaster  # запуск из chronos_integration/

fc = ChronosForecaster(device="cpu")
series = np.array([...], dtype=np.float32)  # одномерный ряд (например close)
f = fc.forecast_one(series, prediction_length=24)
# f.point — медиана прогноза, f.p10/f.p90 — квантильный интервал
```

## Удаление (одна команда)

```bash
bash chronos_integration/uninstall.sh && git rm -r chronos_integration && git commit -m "Remove Chronos"
```

## Жёсткое правило (CLAUDE.md п.1/4/6)

Chronos здесь — **инфраструктура для эксперимента**, не валидированный
edge. Прежде чем использовать прогноз в стратегии — отдельный план в
`plans/`, бэктест, OOS+WF+cost.

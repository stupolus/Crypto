# TimesFM integration (sandbox)

Изолированная песочница для прогнозирования временных рядов с помощью
[Google TimesFM 2.0](https://github.com/google-research/timesfm).

Весь связанный код живёт **только в этой папке**. Основной код бота не
затронут — пока я сам не подключу `TimesFMForecaster` в нужное место.

## Установка

```bash
pip install -r timesfm_integration/requirements.txt
```

## Проверка работоспособности

```bash
python timesfm_integration/example.py
```

Первый запуск скачает чекпоинт `google/timesfm-2.0-500m-pytorch` (~2 ГБ).

## Использование в боте

```python
from timesfm_integration.forecaster import TimesFMForecaster, FREQ_HIGH

forecaster = TimesFMForecaster(horizon_len=24)   # один раз при старте процесса
fc = forecaster.forecast_one(closes, freq=FREQ_HIGH)

# fc.point — медианный прогноз
# fc.p10   — пессимистичная граница
# fc.p90   — оптимистичная граница
```

## Полное удаление (одной командой)

```bash
bash timesfm_integration/uninstall.sh && git add -A && git commit -m "Remove TimesFM"
```

Удалит: папку, pip-пакеты `timesfm` и `torch`, HuggingFace-кэш модели.

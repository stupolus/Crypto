# Kronos integration (sandbox)

Изолированная песочница для **Kronos** — первой open-source
foundation-модели для финансовых свечей (K-line / OHLCV), обученной на
данных 45+ бирж ([github](https://github.com/shiyu-coder/Kronos)).

В отличие от TimesFM (универсальный прогноз 1D-рядов), Kronos работает
именно с многомерными свечами OHLCV и возвращает прогноз будущих свечей.

**Статус:** sandbox. **В основной код проекта НЕ интегрировано.** До
явного «да» владельца (с указанием конкретной точки кода) — обёртка
запускается только отдельно через `example.py`.

## Архитектура

Чтобы оставить главный проектный `.venv` чистым, песочница использует
**свой собственный venv** внутри папки — `kronos_integration/.venv/`.

Kronos **не pip-пакет** (в репо нет `setup.py`/`pyproject.toml`): его API
(`from model import Kronos, KronosTokenizer, KronosPredictor`) доступен
только из исходников. Поэтому `install.sh` ещё и **клонирует** репозиторий
в `kronos_integration/Kronos/`, а `forecaster.py` добавляет эту папку в
`sys.path`. И `.venv/`, и `Kronos/` — в `.gitignore`.

Удаление = `rm -rf kronos_integration/`.

## Установка

Требуется `python3.10`+ и `git`.

```bash
bash kronos_integration/install.sh
# или с другим интерпретатором:
PYTHON=python3.11 bash kronos_integration/install.sh
```

Что делает `install.sh`:
1. Создаёт `kronos_integration/.venv/`.
2. Клонирует Kronos в `kronos_integration/Kronos/` (depth 1).
3. Ставит зависимости из `requirements.txt` (CPU-сборка `torch`).

Веса моделей скачаются с HuggingFace при первом запуске в
`~/.cache/huggingface/`.

## Чекпоинты

| Модель        | Tokenizer HF ID                  | Model HF ID               | Параметры |
|---------------|----------------------------------|---------------------------|-----------|
| Kronos-mini   | `NeoQuasar/Kronos-Tokenizer-2k`  | `NeoQuasar/Kronos-mini`   | 4.1M      |
| Kronos-small  | `NeoQuasar/Kronos-Tokenizer-base`| `NeoQuasar/Kronos-small`  | 24.7M     |
| Kronos-base   | `NeoQuasar/Kronos-Tokenizer-base`| `NeoQuasar/Kronos-base`   | 102.3M    |

По умолчанию обёртка берёт **Kronos-small** + **Tokenizer-base**.

## Smoke-тест

```bash
kronos_integration/.venv/bin/python kronos_integration/example.py
```
Прогноз на синтетических OHLCV + проверка shape и конечности чисел.

## Использование (из песочницы)

```python
import pandas as pd
from forecaster import KronosForecaster, OHLCV_COLS  # запуск из kronos_integration/

fc = KronosForecaster(max_context=512, device="cpu")

# df: контекст со свечами; колонки open/high/low/close/volume[/amount]
x_df = df.loc[:lookback-1, OHLCV_COLS]
x_timestamp = ts.loc[:lookback-1]
y_timestamp = ts.loc[lookback:lookback+pred_len-1]

pred = fc.predict(
    df=x_df,
    x_timestamp=x_timestamp,
    y_timestamp=y_timestamp,
    pred_len=pred_len,
    T=1.0, top_p=0.9, sample_count=1,
)
# pred — DataFrame будущих свечей (те же колонки, что и x_df)
```

## Удаление (одна команда)

```bash
bash kronos_integration/uninstall.sh && git rm -r kronos_integration && git commit -m "Remove Kronos"
```

`uninstall.sh` чистит только HF-кэш весов Kronos (~вне репо). Папка с
`.venv/` и исходниками удаляется через `git rm -r`. Главный проектный
`.venv` не трогается (Kronos туда не ставился).

## Жёсткое правило (CLAUDE.md п.1/4/6)

Kronos здесь — **инфраструктура для эксперимента**, не валидированный
edge. Прежде чем кормить ей реальные данные проекта и использовать
прогноз в стратегии — отдельный план в `plans/`, бэктест, OOS+WF+cost.
Сейчас это только foundation-модель с предобученными весами.

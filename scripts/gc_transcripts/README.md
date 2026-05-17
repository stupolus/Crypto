# GetCourse «КриптоГрамотность» — пайплайн транскриптов

Возобновляемый батч: видео-уроки курса → расшифровка → `raw/уроки/`.

## Как работает

`batch.py` идемпотентен и коммитит/пушит после **каждого** урока,
поэтому прогресс durable: если контейнер пересоздан — новый запуск
пропускает уже готовые уроки и продолжает с места.

Цепочка на урок: Playwright (авторизованная сессия GetCourse) → HLS
master → media 360 → скачивание `.bin`-чанков через браузерный контекст
(проходит TLS-перехват egress) → ffmpeg → 16k mono mp3 →
faster-whisper small (ru) → `NNN-<lid>.md` → git commit+push.

## Запуск

```bash
python3 scripts/gc_transcripts/batch.py            # все видео-уроки
ONLY_N=12,13 python3 scripts/gc_transcripts/batch.py   # только указанные
```

## Требования (эфемерные, в /tmp — не в git)

- `/tmp/yt_work/gc_state.json` — `storage_state` авторизованной сессии
  GetCourse. Получение: Playwright-логин на
  `cryptogramotnost.getcourse.ru/cms/system/login` (email+пароль,
  кнопка `#xdget282670...`), затем `context.storage_state(path=...)`.
  Если файла нет — батч останавливается с кодом 3 (нужен ре-логин).
- `/tmp/yt_work/fwsmall/` — модель faster-whisper-small (ct2). Если
  нет — `batch.py` сам скачивает через curl (HF xet-протокол виснет,
  поэтому только curl на `huggingface.co/Systran/faster-whisper-small`).

## Возобновление в новой сессии

1. Восстановить `gc_state.json` (повторный логин — нужен пароль).
2. `python3 scripts/gc_transcripts/batch.py` — продолжит сам.

## Автономная работа всю ночь

Запускать батч в фоне (`nohup … &`) + скилл `/loop` как надсмотрщик
(каждые ~15 мин: проверить процесс жив, добить коммиты, остановить
loop при `/tmp/yt_work/BATCH_COMPLETE`).

Карта уроков — `lessons_map.json` (41 запись; тесты/план/литература
пропускаются по маркерам в заголовке).

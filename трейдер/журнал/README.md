# Журнал бота «трейдер»

Куда `live_runner` пишет:
- `journal.sqlite` — OrderJournal (запросы/ответы биржи, fill-ы, ошибки).
- `metrics.jsonl` — MetricsWriter (slippage, latencies, аномалии).
- `heartbeat` — пустой файл, touch'ается каждые 30s (для healthcheck).

Файлы артефактов гитом игнорируются (см. `.gitignore`).

Полезные команды (запуск из корня репо в venv):

```bash
# Дневной отчёт по сделкам
python -m scripts.daily_summary --journal трейдер/журнал/journal.sqlite

# Недельный обзор
python -m scripts.weekly_review --journal трейдер/журнал/journal.sqlite

# Экспорт сделок в CSV
python -m scripts.journal_export --db трейдер/журнал/journal.sqlite --out трейдер/журнал/trades.csv
```

## Старт demo

См. `трейдер/раннеры/start_demo.sh` — обёртка над `python -m
runners.live_runner` со всеми путями и флагами трейдера. По умолчанию
запускается с `--dry-run` (ордера не отправляются, только лог).
Переключение на реальные demo-ордера BingX VST — закомментирована
строка `--dry-run` в скрипте.

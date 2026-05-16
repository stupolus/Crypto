# YT Transcripts — пайплайн снятия субтитров

Снятие сырых ASR-транскриптов YouTube без скачивания видео. Только текст
в git, никаких медиафайлов.

## Контекст / ограничения

- IP контейнера **заблокирован** для прямого скачивания timedtext.
  yt-dlp достаёт player-response с **подписанными** timedtext-URL —
  только их и берём.
- Сам timedtext качаем через **другой egress** — Tavily MCP
  `tavily_extract` (батчами по несколько URL).
- yt-dlp **всегда** с `--no-check-certificate`.
- Транскрипты — **сырой ASR**, черновик. Кладём в отдельную папку
  `бизнес/материалы/обработанное/транскрипты/<тема>/`. Работаем в
  ветке `claude/yt-extra-<тема>`; при ненужности — удаляем ветку
  целиком.

## Шаги

1. Установка:
   ```
   pip install "yt-dlp[default,curl-cffi]"
   ```

2. Сформировать `videos.json`:
   ```json
   [{"n": 1, "kind": "video", "id": "vTkZK8PK114", "title": ""}]
   ```

3. Подписанные caption-URL:
   ```
   python3 scripts/yt_transcripts/fetch_caption_urls.py videos.json manifest.json
   ```
   Берёт ручные субтитры, иначе auto-captions; язык по
   `LANG_PREF` (ru→en→первый); URL приводится к `fmt=json3`.

4. Прогнать `url` из manifest через Tavily MCP `tavily_extract`
   (батчами). Ответ по каждому видео сохранить в файл, в имени
   которого есть id видео, напр. `tavily/<id>.json`.

5. Парс в markdown:
   ```
   python3 scripts/yt_transcripts/parse_tavily.py manifest.json \
       <OUTDIR> tavily/*.json
   ```
   Понимает json3 и XML (srv1/srv3), снимает обёртку ответа Tavily,
   убирает rolling-дубликаты.

6. Индекс:
   ```
   python3 scripts/yt_transcripts/build_index.py <OUTDIR>
   ```

7. Коммитить пачками в ветку `claude/yt-extra-<тема>`. Только `.md`,
   `videos.json`, `manifest.json` — без сырых tavily-дампов и без
   медиа.

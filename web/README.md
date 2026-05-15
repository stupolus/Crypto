# Crypto Dashboard — Web UI

Wall Street terminal-style dashboard для crypto trading бота.

Frontend: **Vite + React 19 + TypeScript + Tailwind CSS v4**.
Backend: **FastAPI** в `core/dashboard/` (Python).

## Development

```bash
# 1. Запусти backend (в одном терминале):
cd ..
.venv/bin/python -m core.dashboard.server
# → http://127.0.0.1:8081

# 2. Запусти dev server (в другом терминале):
cd web
npm install
npm run dev
# → http://localhost:5173 (с hot reload, /api прокси на backend)
```

Откроется автоматически. Hot reload работает.

## Production build

```bash
npm run build
# → web/dist/ (static files, можно отдать nginx'ом)
```

Deploy на VPS — см. план в репо. Артефакты `dist/` отдаются nginx'ом на том же домене где FastAPI на `/api`.

## Pages

- `/` — Overview (top stats, open positions, equity curve)
- `/agents` — карточки 5 LLM-агентов с их последними decision'ами
- `/trades` — таблица всех сделок с filter open/closed/all
- `/trades/:id` — детали одной сделки + все 5 LLM payloads (JSON)

## Tech

- Tailwind CSS v4 с custom palette в `src/index.css` (`@theme`)
- React Router 7 (file-routes только в `main.tsx`)
- Polling каждые 5-10 секунд (без WebSocket пока — Phase 7)
- iOS Safari optimizations: viewport-fit cover, safe-area insets, theme-color
- JetBrains Mono для цифр (tabular nums)

## iOS PWA (опционально)

Добавь иконки в `public/` (180×180 apple-touch-icon.png) и manifest.json
чтобы можно было «Add to Home Screen» из Safari.

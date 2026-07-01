# exe-contract — лендинг Exemera

Премиум-редизайн лендинга **Exemera** (контрактное производство инъекционной эстетики).
Полная переработка оригинала `exemera-lnd-plqzh7o6.manus.space` с сохранением айдентики,
контента и ассетов.

## Стек

- **React 19 + Vite 7 + TypeScript**
- **Tailwind CSS v4** (CSS-first `@theme`, дизайн-токены в `src/index.css`)
- **Framer Motion** — скролл-ревилы, параллакс, счётчики, маркиза, модал видео
- Свой лёгкий **i18n** (`src/i18n.tsx`) без зависимостей: EN мастер + глубокое слияние
  частичных словарей с фолбэком. Языки: **EN / RU / ES / ZH / KO / AR** (AR — RTL).

## Разработка

```bash
npm install
npm run dev      # http://localhost:5173
npm run build    # tsc -b && vite build  → dist/
npm run preview  # предпросмотр прод-сборки
```

## Структура

```
src/
  App.tsx              — сборка секций + прогресс-бар скролла
  i18n.tsx             — контекст языков, RTL, deep-merge фолбэк
  assets.ts            — пути к картинкам + CDN-URL видео
  locales/             — en(master) ru es zh ko ar + types
  components/
    ui.tsx             — Reveal, Counter, SectionHeading, LogoMark, варианты анимаций
    Nav Hero Stats Services Advantages Products
    Quality VideoSection Timeline Exhibitions Contact Footer
public/assets/img/     — оптимизированные webp
brand/                 — исходные ассеты, айдентика, манифест (ASSETS.md)
```

## Заметки

- Дизайн-токены (палитра/шрифты/тени) — в `@theme` внутри `src/index.css`.
- Форма контакта пока без бэкенда: показывает подтверждение на клиенте. Подключить к CRM/почте.
- Тяжёлое видео (63 МБ) стримится с CloudFront, не хранится в репо (см. `brand/ASSETS.md`).
- `prefers-reduced-motion` уважается — анимации отключаются.

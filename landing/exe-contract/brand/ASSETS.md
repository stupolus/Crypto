# Exemera — бренд-ассеты (источники и айдентика)

Всё скачано с оригинального лендинга `https://exemera-lnd-plqzh7o6.manus.space`
(React-SPA на manus.space, ассеты на CloudFront). CDN-база:

```
https://d2xsxph8kpxj0f.cloudfront.net/310419663028289097/PLqzh7o66gZyRQYpm9qXpX/
```

## Айдентика

- **Логотип:** вордмарк «exemera» (строчными). Файл `.svg` на CDN отдаёт 403 (закрытый ACL),
  поэтому реконструирован из инлайнового React-компонента `ExemeraLogo.tsx` →
  `assets/logo/exemera-logo.svg` (7 фигур = 7 букв, `viewBox="0 0 1606.45 237.1"`).
- **Палитра (из бандла):**
  - Эспрессо `#2c2420` (основной тёмный), глубокий `#201a16` / `#191512`
  - Шампань-золото `#c4a97d`, мягкое `#d9c39c`, тёмное `#a89279` / `#96816a`
  - Крем `#f5f0eb`, бумага `#fafaf8`, тауп `#b8a99a`, клинический стил `#8ba3b8`
- **Шрифт оригинала:** Inter. В редизайне добавлен дисплейный сериф **Fraunces** для заголовков.

## Изображения (оптимизированы в webp → `public/assets/img`)

| Файл | Источник (CDN suffix) |
|------|------------------------|
| hero_6r_half.webp | `hero_6r_half-oC7qX6ybj57xrLqb6jGtnh.webp` |
| abstract_molecules.webp | `abstract_molecules-FdUNTeuVUVGYse6cfJzvsD.webp` |
| lab_quality.webp | `lab_quality-Z2H5J3HCTzCT4ej75Fdnqi.webp` |
| corridor_gmp_v1.webp | `corridor_gmp_v1_49af4e0e.png` |
| building_sign_on_red_panel.webp | `building_sign_on_red_panel_bd790116.png` |
| production1–4.webp | `production{1..4}_*.jpg` |
| amwc / imcas / cosmoprof / cosmoprof-asia-red / dubai-derma / beautyworld-me / beautyistanbul-logo-new / in-cosmetics-asia | логотипы выставок |

## Тяжёлое медиа (не в git — стримится с CDN, см. `.gitignore`)

| Файл | URL |
|------|-----|
| production-video-with-audio.mp4 (63 МБ) | `…/production-video-with-audio_c2f202b7.mp4` |
| video1.gif (5.5 МБ) | `…/video1_07631a62.gif` |
| video2.gif (5.2 МБ) | `…/video2_09baf71e.gif` |

Локально они лежат в `brand/assets/video/` (gitignored). Чтобы вернуть — скачать по URL выше.
На сайте видео проигрывается прямо с CloudFront (`src/assets.ts` → `media.productionVideo`).

## Оригинал для справки

`brand/reference/original-index.html` — исходный HTML лендинга (контент майнился из JS-бандла).

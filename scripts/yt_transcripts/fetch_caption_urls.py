#!/usr/bin/env python3
"""Извлечь подписанные timedtext-URL субтитров через yt-dlp.

IP контейнера заблокирован для скачивания timedtext, но player-response
с подписанными URL yt-dlp достаёт. Эти URL потом прогоняются через
другой egress (Tavily extract). yt-dlp всегда с --no-check-certificate.

Usage:
    python3 fetch_caption_urls.py videos.json manifest.json

videos.json: [{"n":1,"kind":"video","id":"abc","title":"..."}]
manifest.json: [{"n","id","title","lang","source","url"}]
"""

import json
import subprocess
import sys
from typing import Any

# Порядок предпочтения языка дорожки субтитров.
LANG_PREF = ("en", "en-US", "en-GB", "ru", "ru-RU")


def _lang_rank(lang: str) -> int:
    base = lang.replace("-orig", "")
    for i, pref in enumerate(LANG_PREF):
        if base == pref:
            return i
    return len(LANG_PREF)


def pick_track(
    tracks: dict[str, Any],
) -> tuple[str, str] | tuple[None, None]:
    """Выбрать дорожку: оригинальный ASR в приоритете над переводом.

    Машинный перевод (`tlang=` в URL) — и не настоящий ASR, и часто
    не тянется через прокси-экстрактор. Берём трек, чей json3-URL
    без `tlang=` (исходная речь), предпочитая язык по LANG_PREF.
    Перевод — только если оригинала нет вовсе.
    """
    if not tracks:
        return None, None
    originals: list[tuple[str, str]] = []
    translated: list[tuple[str, str]] = []
    for lang, fmts in tracks.items():
        chosen = next(
            (f for f in fmts if f.get("ext") == "json3" and f.get("url")),
            None,
        ) or next((f for f in fmts if f.get("url")), None)
        if not chosen:
            continue
        url = chosen["url"]
        (translated if "tlang=" in url else originals).append((lang, url))
    pool = originals or translated
    if not pool:
        return None, None
    pool.sort(key=lambda lu: (_lang_rank(lu[0]), lu[0]))
    return pool[0]


def to_json3(url: str) -> str:
    """Привести timedtext-URL к формату json3 (стабильно парсится)."""
    if "fmt=" in url:
        import re

        return re.sub(r"fmt=[^&]*", "fmt=json3", url)
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}fmt=json3"


def fetch_one(video_id: str) -> dict[str, Any] | None:
    # IP под bot-челленджем YouTube: web/ios/android-клиенты режутся
    # «Sign in to confirm you're not a bot». Клиент `tv` стену проходит,
    # форматов видео нет — поэтому --ignore-no-formats-error (нам нужны
    # только caption-URL из player-response, не сами форматы).
    cmd = [
        "yt-dlp",
        "--no-check-certificate",
        "--skip-download",
        "--ignore-no-formats-error",
        "--no-warnings",
        "--dump-single-json",
        "--extractor-args",
        "youtube:player_client=tv",
        "--",
        video_id,
    ]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        print(f"  ! timeout {video_id}", file=sys.stderr)
        return None
    if out.returncode != 0:
        print(
            f"  ! yt-dlp rc={out.returncode} {video_id}: {out.stderr.strip()[:300]}",
            file=sys.stderr,
        )
        return None
    try:
        info = json.loads(out.stdout)
    except json.JSONDecodeError:
        print(f"  ! bad json {video_id}", file=sys.stderr)
        return None

    # Сначала ручные субтитры, потом авто-ASR.
    for source in ("subtitles", "automatic_captions"):
        lang, url = pick_track(info.get(source) or {})
        if not url:
            continue
        return {
            "lang": lang,
            "source": source,
            "url": to_json3(url),
            "title": info.get("title") or "",
        }
    return None


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    with open(sys.argv[1], encoding="utf-8") as fh:
        videos = json.load(fh)
    manifest = []
    for v in videos:
        vid = v["id"]
        print(f"[{v['n']}] {vid} …", file=sys.stderr)
        got = fetch_one(vid)
        entry = {
            "n": v["n"],
            "id": vid,
            "title": v.get("title") or "",
        }
        if got:
            entry.update(
                {
                    "lang": got["lang"],
                    "source": got["source"],
                    "url": got["url"],
                }
            )
            if not entry["title"]:
                entry["title"] = got["title"]
            print(
                f"    ok lang={got['lang']} src={got['source']}",
                file=sys.stderr,
            )
        else:
            entry["url"] = None
            print("    NO CAPTIONS", file=sys.stderr)
        manifest.append(entry)

    with open(sys.argv[2], "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    ok = sum(1 for e in manifest if e.get("url"))
    print(f"\n{ok}/{len(manifest)} с URL → {sys.argv[2]}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

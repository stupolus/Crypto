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

# Порядок предпочтения языка дорожки субтитров.
LANG_PREF = ("ru", "ru-RU", "en", "en-US", "en-GB")


def pick_track(tracks: dict) -> tuple[str, list] | tuple[None, None]:
    """Выбрать языковую дорожку по LANG_PREF, иначе первую доступную."""
    if not tracks:
        return None, None
    for lang in LANG_PREF:
        if lang in tracks:
            return lang, tracks[lang]
    first = sorted(tracks)[0]
    return first, tracks[first]


def to_json3(url: str) -> str:
    """Привести timedtext-URL к формату json3 (стабильно парсится)."""
    if "fmt=" in url:
        import re

        return re.sub(r"fmt=[^&]*", "fmt=json3", url)
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}fmt=json3"


def fetch_one(video_id: str) -> dict | None:
    cmd = [
        "yt-dlp",
        "--no-check-certificate",
        "--skip-download",
        "--no-warnings",
        "--dump-single-json",
        "--",
        video_id,
    ]
    try:
        out = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120
        )
    except subprocess.TimeoutExpired:
        print(f"  ! timeout {video_id}", file=sys.stderr)
        return None
    if out.returncode != 0:
        print(
            f"  ! yt-dlp rc={out.returncode} {video_id}: "
            f"{out.stderr.strip()[:300]}",
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
        lang, fmts = pick_track(info.get(source) or {})
        if not fmts:
            continue
        # Берём json3, иначе любой с url.
        chosen = next(
            (f for f in fmts if f.get("ext") == "json3" and f.get("url")),
            None,
        ) or next((f for f in fmts if f.get("url")), None)
        if not chosen:
            continue
        return {
            "lang": lang,
            "source": source,
            "url": to_json3(chosen["url"]),
            "title": info.get("title") or "",
        }
    return None


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    videos = json.loads(open(sys.argv[1], encoding="utf-8").read())
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

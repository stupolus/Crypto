#!/usr/bin/env python3
"""Extract YouTube auto-caption track URLs via yt-dlp metadata.

This datacenter IP is bot-blocked by YouTube's timedtext endpoint, but
yt-dlp metadata extraction (player API) still works. We grab the signed
caption URLs here, then fetch the actual caption JSON from a different
egress (Tavily) in a second step.

Usage: fetch_caption_urls.py videos.json manifest.json
"""

import json
import subprocess
import sys
import time
from pathlib import Path

LANG_PRIORITY = ("ru-orig", "ru", "en-orig", "en")


def pick_track(info):
    auto = info.get("automatic_captions") or {}
    subs = info.get("subtitles") or {}
    for src_name, src in (("subtitles", subs), ("automatic", auto)):
        for lang in LANG_PRIORITY:
            if lang in src:
                for f in src[lang]:
                    if f.get("ext") == "json3":
                        return lang, src_name, f["url"]
    # fallback: any *-orig first, then anything
    for src_name, src in (("subtitles", subs), ("automatic", auto)):
        for lang in sorted(src, key=lambda k: (not k.endswith("-orig"), k)):
            for f in src[lang]:
                if f.get("ext") == "json3":
                    return lang, src_name, f["url"]
    return None, None, None


def extract(vid):
    cmd = [
        "yt-dlp",
        "--no-check-certificate",
        "--skip-download",
        "-J",
        "--extractor-args",
        "youtube:player_client=android,tv,ios,mweb",
        f"https://www.youtube.com/watch?v={vid}",
    ]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if p.returncode != 0 or not p.stdout.strip():
        raise RuntimeError((p.stderr or "no output")[-300:])
    return json.loads(p.stdout)


def main():
    videos = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    out_path = Path(sys.argv[2])
    manifest = []
    for v in videos:
        rec = {"n": v["n"], "kind": v["kind"], "id": v["id"], "title": v["title"]}
        for attempt in (1, 2):
            try:
                info = extract(v["id"])
                lang, src, url = pick_track(info)
                rec["duration"] = info.get("duration")
                rec["yt_title"] = info.get("title")
                if url:
                    rec.update(lang=lang, caption_source=src, url=url, status="ok")
                else:
                    rec["status"] = "no_captions"
                break
            except Exception as e:
                rec["status"] = "error"
                rec["error"] = str(e)
                if attempt == 1:
                    time.sleep(5)
        manifest.append(rec)
        out_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
        print(
            f"[{v['n']:>3}/{len(videos)}] {v['id']} -> {rec.get('status')} {rec.get('lang', '')}",
            flush=True,
        )
        time.sleep(1)


if __name__ == "__main__":
    main()

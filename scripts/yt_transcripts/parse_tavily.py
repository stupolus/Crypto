#!/usr/bin/env python3
"""Turn Tavily-fetched timedtext JSON into transcript .md files.

Usage: parse_tavily.py manifest.json OUTDIR tavily_result_1.json [...]

Each Tavily result's raw_content is the YouTube json3 caption payload
(sometimes wrapped in a markdown code fence). We map it back to a video
via the v=<id> param in the result URL.
"""
import json
import re
import sys
from pathlib import Path

BASE_URL = "https://www.youtube.com/watch?v="


def load_json3(raw):
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1].rsplit("```", 1)[0]
    i = s.find("{")
    if i > 0:
        s = s[i:]
    return json.loads(s)


def to_text(j):
    out = []
    for e in j.get("events", []):
        line = "".join(seg.get("utf8", "") for seg in (e.get("segs") or []))
        line = line.strip()
        if line:
            out.append(line)
    text = " ".join(out)
    text = re.sub(r"\s+", " ", text).replace(" .", ".").strip()
    # soft-wrap into sentence-ish paragraphs for readability
    sentences = re.split(r"(?<=[.!?])\s+", text)
    paras, buf = [], []
    for sn in sentences:
        buf.append(sn)
        if len(buf) >= 4:
            paras.append(" ".join(buf))
            buf = []
    if buf:
        paras.append(" ".join(buf))
    return "\n\n".join(paras), len(text)


def vid_from_url(url):
    m = re.search(r"[?&]v=([A-Za-z0-9_-]{6,})", url)
    return m.group(1) if m else None


def fmt_dur(sec):
    if not sec:
        return "неизвестно"
    sec = int(sec)
    return f"{sec // 60:02d}:{sec % 60:02d}"


def main():
    manifest = {r["id"]: r for r in json.load(open(sys.argv[1]))}
    outdir = Path(sys.argv[2])
    outdir.mkdir(parents=True, exist_ok=True)
    done = []
    for tf in sys.argv[3:]:
        data = json.load(open(tf))
        for res in data.get("results", []):
            vid = vid_from_url(res.get("url", ""))
            rec = manifest.get(vid)
            if not rec:
                print(f"SKIP unmatched url {res.get('url','')[:80]}")
                continue
            try:
                j = load_json3(res.get("raw_content", ""))
                body, n_chars = to_text(j)
            except Exception as e:  # noqa: BLE001
                print(f"FAIL parse {vid}: {e}")
                continue
            if n_chars < 20:
                print(f"EMPTY {vid}")
                continue
            n = rec["n"]
            fname = f"{n:03d}-{vid}.md"
            title = rec.get("yt_title") or rec["title"]
            header = (
                f"# {title}\n\n"
                f"**Канал:** [[материалы/каналы/dmitry-shukin-crypto]]\n"
                f"**Источник:** {BASE_URL}{vid}\n"
                f"**Тип:** {rec['kind']}\n"
                f"**Длительность:** {fmt_dur(rec.get('duration'))}\n"
                f"**Язык субтитров:** {rec.get('lang','?')} "
                f"({rec.get('caption_source','?')})\n"
                f"**Статус:** сырой транскрипт (auto-caption, без вычитки)\n\n"
                f"---\n\n"
            )
            (outdir / fname).write_text(header + body + "\n",
                                        encoding="utf-8")
            done.append((n, vid, n_chars))
            print(f"WROTE {fname} ({n_chars} chars)")
    print(f"\nTotal written: {len(done)}")


if __name__ == "__main__":
    main()

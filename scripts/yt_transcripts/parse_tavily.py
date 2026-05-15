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
from typing import Any

BASE_URL = "https://www.youtube.com/watch?v="


def _strip(raw: str) -> str:
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1].rsplit("```", 1)[0]
    i = s.find("{")
    if i > 0:
        s = s[i:]
    return s


def load_json3(raw: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(_strip(raw))
    return data


def salvage_segments(raw: str) -> list[str]:
    """Regex-recover caption text when the json3 is not strictly valid
    (Tavily occasionally mangles a backslash in 4MB+ payloads)."""
    out: list[str] = []
    for m in re.finditer(r'"utf8"\s*:\s*"((?:\\.|[^"\\])*)"', _strip(raw)):
        chunk = m.group(1)
        try:
            text = json.loads(f'"{chunk}"')
        except json.JSONDecodeError:
            text = re.sub(r"\\.", " ", chunk)
        if text.strip():
            out.append(str(text))
    return out


def extract_text(raw: str) -> tuple[str, int]:
    try:
        return to_text(load_json3(raw))
    except (json.JSONDecodeError, ValueError):
        segs = salvage_segments(raw)
        if not segs:
            raise
        return finalize(" ".join(s.strip() for s in segs if s.strip()))


def finalize(text: str) -> tuple[str, int]:
    text = re.sub(r"\s+", " ", text).replace(" .", ".").strip()
    # soft-wrap into sentence-ish paragraphs for readability
    sentences = re.split(r"(?<=[.!?])\s+", text)
    paras: list[str] = []
    buf: list[str] = []
    for sn in sentences:
        buf.append(sn)
        if len(buf) >= 4:
            paras.append(" ".join(buf))
            buf = []
    if buf:
        paras.append(" ".join(buf))
    return "\n\n".join(paras), len(text)


def to_text(j: dict[str, Any]) -> tuple[str, int]:
    out: list[str] = []
    for e in j.get("events", []):
        line = "".join(seg.get("utf8", "") for seg in (e.get("segs") or []))
        line = line.strip()
        if line:
            out.append(line)
    return finalize(" ".join(out))


def vid_from_url(url: str) -> str | None:
    m = re.search(r"[?&]v=([A-Za-z0-9_-]{6,})", url)
    return m.group(1) if m else None


def fmt_dur(sec: float | None) -> str:
    if not sec:
        return "неизвестно"
    s = int(sec)
    return f"{s // 60:02d}:{s % 60:02d}"


def main() -> None:
    raw_manifest: list[dict[str, Any]] = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    manifest: dict[str, dict[str, Any]] = {r["id"]: r for r in raw_manifest}
    outdir = Path(sys.argv[2])
    outdir.mkdir(parents=True, exist_ok=True)
    done: list[tuple[int, str, int]] = []
    for tf in sys.argv[3:]:
        data: dict[str, Any] = json.loads(Path(tf).read_text(encoding="utf-8"))
        for res in data.get("results", []):
            vid = vid_from_url(res.get("url", ""))
            rec = manifest.get(vid) if vid else None
            if not rec or not vid:
                print(f"SKIP unmatched url {res.get('url', '')[:80]}")
                continue
            try:
                body, n_chars = extract_text(res.get("raw_content", ""))
            except Exception as e:
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
                f"**Язык субтитров:** {rec.get('lang', '?')} "
                f"({rec.get('caption_source', '?')})\n"
                f"**Статус:** сырой транскрипт (auto-caption, без вычитки)\n\n"
                f"---\n\n"
            )
            (outdir / fname).write_text(header + body + "\n", encoding="utf-8")
            done.append((n, vid, n_chars))
            print(f"WROTE {fname} ({n_chars} chars)")
    print(f"\nTotal written: {len(done)}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Распарсить выгрузку Tavily (timedtext) в .md транскрипты.

Tavily extract тянет подписанные timedtext-URL с другого egress и
отдаёт сырой контент (json3 или XML srv1/srv3). Здесь он чистится в
плоский текст и раскладывается по <n>-<id>.md.

Usage:
    python3 parse_tavily.py manifest.json OUTDIR tavily1.json [tavily2 …]

Файл tavily должен содержать id видео в имени (…<id>….{json,txt,xml}).
"""
import json
import re
import sys
from html import unescape
from pathlib import Path


def load_payload(path: Path) -> str:
    """Достать сырой timedtext-текст из файла Tavily.

    Понимает: голый json3/XML, обёртку ответа Tavily (results→raw_content).
    """
    raw = path.read_text(encoding="utf-8", errors="replace").strip()
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return raw  # XML или текст как есть
    if isinstance(obj, dict) and "events" in obj:
        return raw  # это уже json3
    # Обёртка Tavily: {"results":[{"raw_content": "...", "url": "..."}]}
    if isinstance(obj, dict):
        results = obj.get("results") or obj.get("response") or []
        if isinstance(results, list):
            parts = [
                r.get("raw_content") or r.get("content") or ""
                for r in results
                if isinstance(r, dict)
            ]
            joined = "\n".join(p for p in parts if p)
            if joined:
                return joined
        for key in ("raw_content", "content", "text"):
            if obj.get(key):
                return obj[key]
    return raw


def from_json3(text: str) -> list[str] | None:
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return None
    events = obj.get("events")
    if not isinstance(events, list):
        return None
    lines: list[str] = []
    for ev in events:
        segs = ev.get("segs")
        if not segs:
            continue
        s = "".join(seg.get("utf8", "") for seg in segs)
        s = s.replace("\n", " ").strip()
        if s:
            lines.append(s)
    return lines


def from_xml(text: str) -> list[str]:
    # srv1: <text start=".." dur="..">escaped</text>
    chunks = re.findall(r"<text[^>]*>(.*?)</text>", text, re.S)
    if not chunks:
        # srv3/ttml: <p ...>text</p>
        chunks = re.findall(r"<p[^>]*>(.*?)</p>", text, re.S)
    out = []
    for c in chunks:
        c = re.sub(r"<[^>]+>", " ", c)
        c = unescape(c).replace("\n", " ").strip()
        c = re.sub(r"\s+", " ", c)
        if c:
            out.append(c)
    return out


def dedupe(lines: list[str]) -> list[str]:
    """Убрать подряд идущие точные дубликаты (rolling-captions ASR)."""
    out: list[str] = []
    for ln in lines:
        if out and out[-1] == ln:
            continue
        out.append(ln)
    return out


def wrap(text: str, width: int = 100) -> str:
    words = text.split()
    out, cur = [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width:
            out.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        out.append(cur)
    return "\n".join(out)


def main() -> int:
    if len(sys.argv) < 4:
        print(__doc__)
        return 2
    manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    outdir = Path(sys.argv[2])
    outdir.mkdir(parents=True, exist_ok=True)
    tfiles = [Path(p) for p in sys.argv[3:]]

    written = 0
    for entry in manifest:
        vid = entry["id"]
        if not entry.get("url"):
            print(f"[{entry['n']}] {vid}: нет URL — пропуск", file=sys.stderr)
            continue
        match = next((p for p in tfiles if vid in p.name), None)
        if not match:
            print(f"[{entry['n']}] {vid}: нет tavily-файла", file=sys.stderr)
            continue
        payload = load_payload(match)
        lines = from_json3(payload)
        if lines is None:
            lines = from_xml(payload)
        lines = dedupe([ln for ln in lines if ln])
        if not lines:
            print(f"[{entry['n']}] {vid}: пусто после парса", file=sys.stderr)
            continue

        body = wrap(" ".join(lines))
        title = entry.get("title") or vid
        n = entry["n"]
        fn = outdir / f"{n:02d}-{vid}.md"
        header = (
            f"# {title}\n\n"
            f"- video: https://youtu.be/{vid}\n"
            f"- lang: {entry.get('lang', '?')}\n"
            f"- source: {entry.get('source', '?')} (сырой ASR, черновик)\n\n"
            f"---\n\n"
        )
        fn.write_text(header + body + "\n", encoding="utf-8")
        written += 1
        print(f"[{n}] {vid} → {fn.name} ({len(lines)} сегм.)",
              file=sys.stderr)

    print(f"\n{written} транскрипт(ов) в {outdir}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

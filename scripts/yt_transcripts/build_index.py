#!/usr/bin/env python3
"""Build INDEX.md for the transcript folder. Usage: build_index.py OUTDIR manifest.json"""
import json
import re
import sys
from pathlib import Path

outdir = Path(sys.argv[1])
manifest = {r["id"]: r for r in json.load(open(sys.argv[2]))}
rows, present = [], {}
for p in sorted(outdir.glob("[0-9]*-*.md")):
    m = re.match(r"(\d+)-([A-Za-z0-9_-]+)\.md", p.name)
    if m:
        present[int(m.group(1))] = (m.group(2), p.name)

lines = [
    "# Транскрипты — Дмитрий Щукин | Crypto Trading",
    "",
    "Сырые авто-субтитры (YouTube ASR), без вычитки. Канал: "
    "[[материалы/каналы/dmitry-shukin-crypto]].",
    "",
    f"Получено: {len(present)} из {len(manifest)} публикаций.",
    "",
    "| # | Тип | Транскрипт | Видео |",
    "|---|---|---|---|",
]
for rec in sorted(manifest.values(), key=lambda r: r["n"]):
    n = rec["n"]
    if n in present:
        _, fname = present[n]
        link = f"[{fname}]({fname})"
    else:
        link = f"_нет ({rec.get('status','?')})_"
    url = f"https://www.youtube.com/watch?v={rec['id']}"
    title = (rec.get("yt_title") or rec["title"]).replace("|", "\\|")
    lines.append(f"| {n} | {rec['kind']} | {link} | [{title}]({url}) |")

(outdir / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"INDEX.md: {len(present)}/{len(manifest)} present")

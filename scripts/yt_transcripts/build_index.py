#!/usr/bin/env python3
"""Собрать INDEX.md по каталогу транскриптов.

Usage:
    python3 build_index.py OUTDIR
"""

import re
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    outdir = Path(sys.argv[1])
    files = sorted(p for p in outdir.glob("*.md") if p.name != "INDEX.md")

    rows = []
    for p in files:
        text = p.read_text(encoding="utf-8")
        m = re.search(r"^# (.+)$", text, re.M)
        title = m.group(1).strip() if m else p.stem
        vid = ""
        mv = re.search(r"youtu\.be/([\w-]+)", text)
        if mv:
            vid = mv.group(1)
        body = text.split("---", 1)[-1]
        words = len(body.split())
        rows.append((p.name, title, vid, words))

    lines = [
        "# Транскрипты — youtube-trading",
        "",
        "Черновой сырой ASR (auto-captions). Возможно-ненужный материал, "
        "ветка при необходимости удаляется целиком.",
        "",
        f"Всего файлов: {len(rows)}",
        "",
        "| # | Файл | Видео | Слов | Заголовок |",
        "|---|---|---|---|---|",
    ]
    for i, (fn, title, vid, words) in enumerate(rows, 1):
        link = f"https://youtu.be/{vid}" if vid else ""
        safe = title.replace("|", "\\|")
        lines.append(f"| {i} | [{fn}]({fn}) | {link} | {words} | {safe} |")

    (outdir / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"INDEX.md: {len(rows)} записей", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

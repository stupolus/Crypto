#!/usr/bin/env python3
"""Build INDEX.md for the transcript folder.

Usage: build_index.py OUTDIR manifest.json
"""

import json
import re
import sys
from pathlib import Path
from typing import Any


def main() -> None:
    outdir = Path(sys.argv[1])
    raw_manifest: list[dict[str, Any]] = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    manifest: dict[str, dict[str, Any]] = {r["id"]: r for r in raw_manifest}
    present: dict[int, tuple[str, str]] = {}
    for p in sorted(outdir.glob("[0-9]*-*.md")):
        m = re.match(r"(\d+)-([A-Za-z0-9_-]+)\.md", p.name)
        if m:
            present[int(m.group(1))] = (m.group(2), p.name)

    lines: list[str] = [
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
    for rec in sorted(manifest.values(), key=lambda r: int(r["n"])):
        n = rec["n"]
        if n in present:
            _, fname = present[n]
            link = f"[{fname}]({fname})"
        else:
            link = f"_нет ({rec.get('status', '?')})_"
        url = f"https://www.youtube.com/watch?v={rec['id']}"
        title = (rec.get("yt_title") or rec["title"]).replace("|", "\\|")
        lines.append(f"| {n} | {rec['kind']} | {link} | [{title}]({url}) |")

    (outdir / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"INDEX.md: {len(present)}/{len(manifest)} present")


if __name__ == "__main__":
    main()

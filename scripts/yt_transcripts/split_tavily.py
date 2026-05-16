#!/usr/bin/env python3
"""Разложить ответ(ы) Tavily extract по файлам tavily/<id>.json.

Tavily возвращает {"results":[{"url","raw_content"}], "failed_results":[…]}.
Здесь по параметру v=<id> из URL раскладываем raw_content в отдельные
файлы (их потом ест parse_tavily.py) и печатаем, какие id ещё не сняты.

Usage:
    python3 split_tavily.py manifest.json tavily/ tavily_resp1.json […]
"""

import json
import re
import sys
from pathlib import Path

VID_RE = re.compile(r"[?&]v=([\w-]{11})")


def main() -> int:
    if len(sys.argv) < 4:
        print(__doc__)
        return 2
    manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    tdir = Path(sys.argv[2])
    tdir.mkdir(parents=True, exist_ok=True)

    saved: set[str] = set()
    for resp_path in sys.argv[3:]:
        d = json.loads(Path(resp_path).read_text(encoding="utf-8"))
        for r in d.get("results", []):
            m = VID_RE.search(r.get("url", ""))
            content = r.get("raw_content") or r.get("content")
            if not (m and content):
                continue
            vid = m.group(1)
            (tdir / f"{vid}.json").write_text(content, encoding="utf-8")
            saved.add(vid)

    have = {p.stem for p in tdir.glob("*.json")}
    need = [e["id"] for e in manifest if e.get("url") and e["id"] not in have]
    print(f"сохранено в этом прогоне: {len(saved)}", file=sys.stderr)
    print(f"всего на диске: {len(have)}/{len(manifest)}", file=sys.stderr)
    if need:
        print("ОСТАЛОСЬ снять (id):", file=sys.stderr)
        for e in manifest:
            if e["id"] in need:
                print(f"  {e['n']:2d} {e['id']}  {e['url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

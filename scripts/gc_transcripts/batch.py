#!/usr/bin/env python3
"""Resumable batch: GetCourse «КриптоГрамотность» video lessons -> transcripts.

Idempotent. Commits+pushes after every lesson, so progress is durable even
if the container is reclaimed. A fresh run skips lessons already written.

Pipeline per lesson:
  Playwright (authed session) -> HLS master -> 360 media playlist
  -> download .bin segments via browser ctx (passes TLS-intercept egress)
  -> ffmpeg concat -> 16k mono mp3 -> faster-whisper (ru) -> .md + git push

Requires:
  /tmp/yt_work/gc_state.json   authenticated GetCourse storage_state
  /tmp/yt_work/fwsmall/        faster-whisper-small ct2 model (auto-curl)
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

WORK = Path("/tmp/yt_work")
REPO = Path("/home/user/Crypto")
OUTDIR = REPO / "бизнес/материалы/курс-криптограмотность/raw/уроки"
STATE = WORK / "gc_state.json"
MODEL = WORK / "fwsmall"
LESSONS = Path(__file__).with_name("lessons_map.json")
BASE = "https://cryptogramotnost.getcourse.ru"
BRANCH = "claude/crypto-video-transcripts-PnCMQ"
SKIP_MARK = ("Есть задание", "тестирование", "Учебный план", "Список литературы")
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

_MODEL: Any = None


def log(m: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def ensure_model() -> None:
    if (MODEL / "model.bin").exists():
        return
    MODEL.mkdir(parents=True, exist_ok=True)
    for f in ("config.json", "tokenizer.json", "vocabulary.txt", "model.bin"):
        subprocess.run(
            [
                "curl",
                "-sL",
                "--fail",
                "--retry",
                "3",
                "--max-time",
                "1200",
                "-o",
                str(MODEL / f),
                f"https://huggingface.co/Systran/faster-whisper-small/resolve/main/{f}",
            ],
            check=True,
        )
    log("model downloaded")


def fetch_audio(lid: str) -> str | None:
    """Return path to mp3, "NO_VIDEO", or None if already transcribed."""
    mp3 = WORK / f"{lid}.mp3"
    if mp3.exists() and mp3.stat().st_size > 10000:
        return str(mp3)
    txt = WORK / f"{lid}.txt"
    if txt.exists() and txt.stat().st_size > 200:
        return None
    from playwright.sync_api import sync_playwright

    got: dict[str, str | None] = {"u": None}
    ts = WORK / f"{lid}.ts"
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(
            storage_state=str(STATE),
            ignore_https_errors=True,
            locale="ru-RU",
            user_agent=UA,
        )
        pg = ctx.new_page()
        pg.on(
            "request",
            lambda r: (
                got.__setitem__("u", r.url)
                if "/api/playlist/master/" in r.url and not got["u"]
                else None
            ),
        )
        pg.goto(
            f"{BASE}/teach/control/lesson/view/id/{lid}",
            wait_until="domcontentloaded",
            timeout=60000,
        )
        pg.wait_for_timeout(12000)
        if not got["u"]:
            ctx.close()
            b.close()
            return "NO_VIDEO"
        master = pg.request.get(got["u"]).text()
        media = next(
            (
                ln.strip()
                for ln in master.splitlines()
                if ln.strip().startswith("http") and "/media/" in ln and "/360?" in ln
            ),
            None,
        )
        if not media:
            ctx.close()
            b.close()
            return "NO_VIDEO"
        segs = [
            ln.strip()
            for ln in pg.request.get(media).text().splitlines()
            if ln.strip().startswith("http")
        ]
        with open(ts, "wb") as f:
            for s in segs:
                f.write(pg.request.get(s, timeout=60000).body())
        ctx.close()
        b.close()
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(ts),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "libmp3lame",
            "-q:a",
            "5",
            str(mp3),
        ],
        check=True,
        timeout=900,
    )
    ts.unlink(missing_ok=True)
    return str(mp3)


def transcribe(lid: str, mp3: str) -> str:
    txt = WORK / f"{lid}.txt"
    if txt.exists() and txt.stat().st_size > 200:
        return txt.read_text(encoding="utf-8")
    global _MODEL
    if _MODEL is None:
        from faster_whisper import WhisperModel

        _MODEL = WhisperModel(str(MODEL), device="cpu", compute_type="int8", cpu_threads=4)
    segments, _ = _MODEL.transcribe(
        mp3,
        language="ru",
        beam_size=1,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
    )
    parts: list[str] = []
    with open(txt, "w", encoding="utf-8") as f:
        for s in segments:
            parts.append(s.text.strip())
            f.write(s.text.strip() + " ")
    return " ".join(parts)


def soft_wrap(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    sents = re.split(r"(?<=[.!?])\s+", text)
    out: list[str] = []
    buf: list[str] = []
    for s in sents:
        buf.append(s)
        if len(buf) >= 4:
            out.append(" ".join(buf))
            buf = []
    if buf:
        out.append(" ".join(buf))
    return "\n\n".join(out)


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True)


def commit_push(path: Path, n: int, title: str) -> bool:
    git("add", str(path))
    git(
        "-c",
        "core.pager=cat",
        "commit",
        "-q",
        "-m",
        f"курс Криптограмотность: транскрипт урок №{n} — {title[:60]}\n\n"
        f"https://claude.ai/code/session_0161wmhxuWzdWNGzL9vpos16",
    )
    r = git("status")
    for attempt in range(4):
        git("pull", "--rebase", "origin", BRANCH)
        r = git("push", "origin", BRANCH)
        if r.returncode == 0:
            return True
        time.sleep(2**attempt)
    log(f"PUSH FAILED n={n}: {r.stderr[-200:]}")
    return False


def main() -> None:
    if not STATE.exists():
        log("FATAL: no gc_state.json (need re-login). STOPPING.")
        sys.exit(3)
    ensure_model()
    OUTDIR.mkdir(parents=True, exist_ok=True)
    lessons: list[dict[str, Any]] = json.loads(LESSONS.read_text(encoding="utf-8"))
    vids = [x for x in lessons if not any(m in x["t"] for m in SKIP_MARK)]
    only = os.environ.get("ONLY_N")
    if only:
        keep = {int(v) for v in only.split(",")}
        vids = [x for x in vids if x["n"] in keep]
    log(f"{len(vids)} video lessons to ensure")
    done = skipped = failed = 0
    for x in vids:
        n, lid, title = x["n"], x["lid"], x["t"]
        md = OUTDIR / f"{n:03d}-{lid}.md"
        if md.exists() and md.stat().st_size > 400:
            skipped += 1
            continue
        log(f"=== n={n} lid={lid} {title[:50]}")
        try:
            mp3 = fetch_audio(lid)
            if mp3 == "NO_VIDEO":
                md.write_text(
                    f"# {title}\n\n**Урок:** {BASE}/teach/control/"
                    f"lesson/view/id/{lid}\n**Статус:** без видео "
                    f"(текстовый/тест) — расшифровка не требуется\n",
                    encoding="utf-8",
                )
                commit_push(md, n, title)
                skipped += 1
                continue
            t1 = time.time()
            raw = transcribe(lid, str(mp3))
            body = soft_wrap(raw)
            header = (
                f"# {title}\n\n"
                f"**Курс:** Криптограмотность (модуль {x.get('module', '?')})\n"
                f"**Урок:** {BASE}/teach/control/lesson/view/id/{lid}\n"
                f"**№ в курсе:** {n}\n"
                f"**Статус:** сырой транскрипт (faster-whisper small, ru, "
                f"без вычитки)\n\n---\n\n"
            )
            md.write_text(header + body + "\n", encoding="utf-8")
            (WORK / f"{lid}.mp3").unlink(missing_ok=True)
            commit_push(md, n, title)
            done += 1
            log(f"OK n={n} ({len(raw)} chars, {time.time() - t1:.0f}s)")
        except Exception as e:
            failed += 1
            log(f"FAIL n={n}: {type(e).__name__}: {str(e)[:200]}")
            with (WORK / "batch_failures.log").open("a") as fh:
                fh.write(f"{n} {lid} {e}\n")
            continue
    log(f"BATCH DONE done={done} skipped={skipped} failed={failed}")
    (WORK / "BATCH_COMPLETE").write_text(f"done={done} skipped={skipped} failed={failed}\n")


if __name__ == "__main__":
    main()

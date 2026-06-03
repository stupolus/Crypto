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

import contextlib
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
OUTDIR = REPO / os.environ.get("GC_OUT_SUBDIR", "бизнес/материалы/курс-криптограмотность/raw/уроки")
STATE = WORK / "gc_state.json"
MODEL = WORK / "fwsmall"
LESSONS = Path(os.environ.get("GC_LESSONS_MAP", str(Path(__file__).with_name("lessons_map.json"))))
BASE = "https://cryptogramotnost.getcourse.ru"
COMMIT_PREFIX = os.environ.get("GC_COMMIT_PREFIX", "курс Криптограмотность")
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
        pg.wait_for_timeout(6000)
        # The GetCourse/Kinescope player only requests the HLS master
        # after the play button is engaged. Click into the sign-player
        # iframe to start it, then wait for the master request. Reload
        # once and retry — a cold browser (first lesson after a restart)
        # can be too slow on the first pass, which must NOT be mistaken
        # for "no video" (it would write a false stub).
        for cycle in range(2):
            for _ in range(5):
                if got["u"]:
                    break
                for fr in pg.frames:
                    if "sign-player" in (fr.url or ""):
                        with contextlib.suppress(Exception):
                            fr.locator("body").first.click(timeout=4000)
                        break
                pg.wait_for_timeout(9000)
            if got["u"] or cycle == 1:
                break
            with contextlib.suppress(Exception):
                pg.reload(wait_until="domcontentloaded", timeout=60000)
            pg.wait_for_timeout(8000)
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
    tmp = WORK / f"{lid}.txt.partial"
    with open(tmp, "w", encoding="utf-8") as f:
        for s in segments:
            parts.append(s.text.strip())
            f.write(s.text.strip() + " ")
    tmp.replace(txt)
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
        f"{COMMIT_PREFIX}: транскрипт урок №{n} — {title[:60]}\n\n"
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


PROGRESS = WORK / "progress.json"
RETRY = 3  # in-run attempts per video (backoff between)
MAX_RUNS = 5  # runs after which a video is marked failed-permanently


def load_progress() -> dict[str, dict[str, Any]]:
    if PROGRESS.exists():
        data: dict[str, dict[str, Any]] = json.loads(PROGRESS.read_text(encoding="utf-8"))
        return data
    return {}


def save_progress(prog: dict[str, dict[str, Any]]) -> None:
    PROGRESS.write_text(json.dumps(prog, ensure_ascii=False, indent=1), encoding="utf-8")


def now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def transcribe_one(x: dict[str, Any]) -> str:
    """One video with in-run retries+backoff. Returns done/novideo;
    raises on exhaustion."""
    n, lid, title = x["n"], x["lid"], x["t"]
    md = OUTDIR / f"{n:03d}-{lid}.md"
    last = ""
    for attempt in range(1, RETRY + 1):
        try:
            mp3 = fetch_audio(lid)
            if mp3 == "NO_VIDEO":
                md.write_text(
                    f"# {title}\n\n**Урок:** {BASE}/teach/control/"
                    f"lesson/view/id/{lid}\n**Статус:** без видео "
                    f"(текстовый/тест) — расшифровка не требуется\n",
                    encoding="utf-8",
                )
                return "novideo"
            t1 = time.time()
            raw = transcribe(lid, str(mp3))
            header = (
                f"# {title}\n\n"
                f"**Урок:** {BASE}/teach/control/lesson/view/id/{lid}\n"
                f"**№:** {n}\n"
                f"**Статус:** сырой транскрипт (faster-whisper small, ru, "
                f"без вычитки)\n\n---\n\n"
            )
            md.write_text(header + soft_wrap(raw) + "\n", encoding="utf-8")
            (WORK / f"{lid}.mp3").unlink(missing_ok=True)
            log(f"OK n={n} ({len(raw)} chars, {time.time() - t1:.0f}s)")
            return "done"
        except Exception as e:
            last = f"{type(e).__name__}: {str(e)[:200]}"
            log(f"retry {attempt}/{RETRY} n={n}: {last}")
            (WORK / f"{lid}.txt.partial").unlink(missing_ok=True)
            time.sleep(min(5 * 2**attempt, 120))
    raise RuntimeError(last)


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
    prog = load_progress()
    log(f"{len(vids)} video lessons to ensure")
    done = skipped = failed = 0
    for x in vids:
        n, lid, title = x["n"], x["lid"], x["t"]
        md = OUTDIR / f"{n:03d}-{lid}.md"
        if md.exists() and md.stat().st_size > 400:
            skipped += 1
            continue
        rec = prog.get(lid, {"attempts": 0})
        if rec.get("status") == "failed_permanent":
            skipped += 1
            continue
        log(f"=== n={n} lid={lid} {title[:50]}")
        try:
            status = transcribe_one(x)
            prog[lid] = {"status": status, "n": n, "ts": now()}
            commit_push(md, n, title)
            done += 1
        except Exception as e:  # all in-run retries exhausted this run
            runs = int(rec.get("attempts", 0)) + 1
            rec = {
                "status": "failed",
                "attempts": runs,
                "error": f"{type(e).__name__}: {str(e)[:200]}",
                "ts": now(),
            }
            failed += 1
            log(f"FAIL n={n} (run {runs}/{MAX_RUNS}): {rec['error']}")
            with (WORK / "batch_failures.log").open("a") as fh:
                fh.write(f"{now()} {n} {lid} run{runs} {rec['error']}\n")
            if runs >= MAX_RUNS:
                rec["status"] = "failed_permanent"
                md.write_text(
                    f"# {title}\n\n**Урок:** {BASE}/teach/control/"
                    f"lesson/view/id/{lid}\n**№:** {n}\n**Статус:** "
                    f"НЕ УДАЛОСЬ расшифровать после {runs} прогонов "
                    f"(причина: {rec['error']}). Перепроверить вручную.\n",
                    encoding="utf-8",
                )
                commit_push(md, n, title)
            prog[lid] = rec
        save_progress(prog)
    remaining = [x for x in vids if not (OUTDIR / f"{x['n']:03d}-{x['lid']}.md").exists()]
    log(f"BATCH PASS done={done} skipped={skipped} failed={failed} remaining={len(remaining)}")
    if not remaining:
        (WORK / "BATCH_COMPLETE").write_text(
            f"all {len(vids)} resolved; "
            f"failed_permanent="
            f"{sum(1 for v in prog.values() if v.get('status') == 'failed_permanent')}\n"
        )


if __name__ == "__main__":
    main()

# Skill: YouTube transcripts when the runtime IP is bot-blocked (Manus-ready)

Portable, platform-agnostic runbook. No Claude/Anthropic-specific tools
required. Hand this whole file to Manus (manus.im) as the task brief, or
keep it as a reusable skill. Everything here is plain shell + Python +
one outbound HTTP fetch from a non-blocked egress.

## Goal

Given a list of YouTube URLs (normal videos **and** Shorts), produce one
Markdown transcript file per video (raw auto-captions / ASR, no
proofreading) plus an `INDEX.md`.

## The core problem

Cloud / datacenter IPs are bot-blocked by YouTube's caption endpoint
`https://www.youtube.com/api/timedtext`. Symptoms:

- `youtube-transcript-api` → `IpBlocked` / `RequestBlocked`
- `yt-dlp` subtitle download → `HTTP Error 429: Too Many Requests`
- `yt-dlp` web client → `Sign in to confirm you're not a bot`

But **two things still work from the blocked IP**:

1. `yt-dlp` *metadata* extraction (the player API) — it returns the
   signed `timedtext` URLs. Only *downloading* those URLs is blocked.
2. Any HTTP fetch from a **different egress** (a web-crawl/extract
   service, a proxy, a browser tool running on different infra) can
   pull the `timedtext` JSON the blocked IP cannot.

So the trick is **split egress**: get the signed URL from the blocked
host, fetch its content from somewhere else.

## What "somewhere else" means on Manus

The original implementation used the Tavily `extract` API. On Manus use
whichever of these is available — they all fetch from infra that is not
the YouTube-blocked datacenter IP:

- Manus's built-in **browser / web tool** → open the `timedtext` URL,
  copy the raw JSON body.
- A generic web-extract / scrape API (Tavily, Firecrawl, Jina Reader
  `https://r.jina.ai/<url>`, ScrapingBee, etc.).
- An HTTP fetch routed through a **residential/rotating proxy**.
- As a last resort: paste the signed URL into any external fetch that
  is not on the same blocked IP.

The only requirement: the fetch must NOT originate from the same
datacenter IP that runs `yt-dlp`.

## Prerequisites

```bash
pip3 install -q "yt-dlp[default,curl-cffi]"
```

`yt-dlp` here needs `--no-check-certificate` only if the environment
does TLS interception (managed egress gateway). On a normal Manus box
you can drop that flag.

## Step 1 — build the input list

Create `videos.json`: a list of objects
`{"n": <int>, "kind": "video"|"short", "id": "<11-char-id>", "title": "<title>"}`.
The YouTube id is the `v=` value (Shorts: the id after `/shorts/`).

## Step 2 — extract signed caption URLs (runs on the blocked IP)

`fetch_caption_urls.py` (in this same folder) does this. Core call it
makes per video:

```bash
yt-dlp --no-check-certificate --skip-download -J \
  --extractor-args "youtube:player_client=android,tv,ios,mweb" \
  "https://www.youtube.com/watch?v=<ID>"
```

Then from the JSON it picks the `json3` caption track, language
priority `ru-orig, ru, en-orig, en`, then any `*-orig`, then any.
Output: `manifest.json` (one record per video with a signed `url`).

```bash
python3 fetch_caption_urls.py videos.json manifest.json
```

~10 s/video; run it over the whole list (background it for 100+).
Re-run for any `"status":"error"` rows (transient extractor flakiness).

## Step 3 — fetch the caption JSON from a non-blocked egress

The signed URLs expire in roughly a few hours — do this soon after
step 2. For each `url` in `manifest.json`, fetch the body (it is
`json3`: a JSON doc with an `events[].segs[].utf8` structure).

- If using a web-extract API: send the URLs in small batches, save each
  response to a file.
- If using the browser tool: open the URL, save the page body text.

Keep the mapping URL→video: every signed URL contains `&v=<ID>`.

## Step 4 — parse to transcripts

`parse_tavily.py` consumes the saved fetch responses. It accepts the
web-extract JSON shape `{results:[{url, raw_content}]}`, maps each back
to a video by the `v=<id>` param, decodes the `json3` (with a regex
salvage fallback for occasionally-mangled large payloads), and writes
`NNN-<id>.md` with a header + soft-wrapped body.

```bash
python3 parse_tavily.py manifest.json OUTPUT_DIR fetch_resp_1.json [fetch_resp_2.json ...]
python3 build_index.py OUTPUT_DIR manifest.json   # writes INDEX.md
```

If your fetch tool returns the raw `json3` directly (not wrapped in a
`{results:[...]}` envelope), wrap it yourself before calling the
parser, e.g.:

```python
import json, pathlib
raw = pathlib.Path("body.txt").read_text()           # the timedtext body
url = "https://www.youtube.com/api/timedtext?...&v=<ID>..."
json.dump({"results":[{"url":url,"raw_content":raw}]},
          open("fetch_resp_1.json","w"))
```

…then run `parse_tavily.py manifest.json OUTDIR fetch_resp_1.json`.

## Gotchas

- json3 may arrive wrapped in a ``` fence; the parser strips it.
- Very large payloads (60+ min videos, multi-MB) can come back with a
  broken backslash from some extract services — `parse_tavily.py` has a
  regex salvage path that recovers the text anyway.
- Shorts have auto-captions too; identical path, no special handling.
- These are machine ASR captions: numbers, levels and names are NOT
  reliable. Mark output as un-proofread.
- One signed URL = one language track. Re-extract (step 2) if a URL
  expired before you fetched it.

## Files in this folder

| File | Role |
|---|---|
| `fetch_caption_urls.py` | step 2 — blocked-IP metadata → signed URLs |
| `parse_tavily.py` | step 4 — caption JSON → Markdown transcripts |
| `build_index.py` | step 4 — INDEX.md |
| `MANUS_SKILL.md` | this portable runbook |

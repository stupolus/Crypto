#!/bin/bash
# Self-restarting runner for the VIP transcription batch.
# Survives python-level crashes: re-launches batch.py each pass until
# /tmp/yt_work/BATCH_COMPLETE exists (batch.py writes it when no video
# remains unresolved — real transcript, no-video stub, or failed_permanent).
# Does NOT survive container reclamation on idle (no scheduler here) —
# in that case a single nudge restarts this runner.
set -u
export GC_LESSONS_MAP=/home/user/Crypto/scripts/gc_transcripts/vip_lessons_map.json
export GC_OUT_SUBDIR="бизнес/материалы/курс-криптограмотность/raw/vip-встречи"
export GC_COMMIT_PREFIX="VIP Щукин"
cd /home/user/Crypto || exit 1
LOG=/tmp/yt_work/runner.log
i=0
while [ ! -f /tmp/yt_work/BATCH_COMPLETE ]; do
  i=$((i + 1))
  echo "[runner] pass $i start $(date -u +%H:%M:%S)" >>"$LOG"
  python3 scripts/gc_transcripts/batch.py >>/tmp/yt_work/vip.log 2>&1
  rc=$?
  echo "[runner] pass $i batch rc=$rc $(date -u +%H:%M:%S)" >>"$LOG"
  if [ "$rc" -eq 3 ]; then
    echo "[runner] gc_state.json missing -> need re-login, stopping" >>"$LOG"
    break
  fi
  [ -f /tmp/yt_work/BATCH_COMPLETE ] && break
  sleep 10
done
echo "[runner] FINISHED $(date -u +%H:%M:%S)" >>"$LOG"

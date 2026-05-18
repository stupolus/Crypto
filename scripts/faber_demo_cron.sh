#!/usr/bin/env bash
# Faber VST demo-исполнитель — ежедневно (план 41.3). НЕ LIVE.
# Hard-guard BINGX_ENV=vst в коде. Идемпотентно (реконсил от
# факт. позиции). Ошибки/действия → ops/faber_vst.jsonl.
set -euo pipefail
cd "$(dirname "$0")/.."
.venv/bin/python -m scripts.faber_vst_executor >> ops/faber_vst_cron.log 2>&1

#!/usr/bin/env bash
# Faber demo paper-runner — ежедневный запуск (план 40.3).
# PAPER-only: без реальных ордеров и торговых ключей.
# Идемпотентен: повторный запуск в тот же день — no-op.
# Лог: ops/faber_demo.jsonl (в .gitignore, копится ≥4 нед).
set -euo pipefail
cd "$(dirname "$0")/.."
.venv/bin/python -m scripts.faber_demo_runner >> ops/faber_demo_cron.log 2>&1

#!/usr/bin/env bash
# Запуск demo бота «трейдер» на BingX VST с Coinglass live-провайдерами.
#
# Зависит от:
#   - .env в корне репо: COINGLASS_API_KEY, BINGX_ENV=vst,
#     BINGX_VST_API_KEY, BINGX_VST_API_SECRET, опц. TELEGRAM_BOT_TOKEN,
#     TELEGRAM_CHAT_ID.
#   - venv .venv (Python 3.12+, pip install -e ".[dev]").
#
# Безопасность: ТОЛЬКО VST (demo). Live запрещён до 4+ недель demo
# и явного «да» (CLAUDE.md). Сначала рекомендуется --dry-run.

set -euo pipefail
cd "$(dirname "$0")/../.."        # корень репо

# shellcheck disable=SC1091
source .venv/bin/activate

mkdir -p трейдер/журнал

exec python -m runners.live_runner \
    --strategy liquidation_reversal \
    --strategy-config трейдер/стратегии/композит-btc-6h.yaml \
    --symbol BTC-USDT \
    --interval 6h \
    --warmup-candles 80 \
    --dry-run \
    --journal-db трейдер/журнал/journal.sqlite \
    --metrics-file трейдер/журнал/metrics.jsonl \
    --heartbeat-file трейдер/журнал/heartbeat \
    --log-level INFO

# Снять --dry-run = реальные demo-ордера BingX VST. Делать ТОЛЬКО после
# нескольких суток dry-run и проверки логов/журнала.

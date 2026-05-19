# Crypto bot Docker image — multi-stage build.
# Цель: минимальный slim-образ для запуска runner'а в изоляции от
# других контейнеров на VPS (Odoo и т.д.).
#
# Build:  docker build -t crypto-bot:latest -f scripts/deploy/Dockerfile .
# Run:    см. docker-compose.yml в этой же папке.

# ── Stage 1: builder (с компиляторами) ─────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Зависимости для сборки cffi / cryptography если понадобятся (gcc/libffi).
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        libffi-dev && \
    rm -rf /var/lib/apt/lists/*

# Только зависимости — кэшируется лучше.
COPY pyproject.toml ./
COPY adapters/ ./adapters/
COPY core/ ./core/
COPY strategies/ ./strategies/
COPY runners/ ./runners/
COPY scripts/ ./scripts/
COPY parsers/ ./parsers/

RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir --upgrade pip && \
    /opt/venv/bin/pip install --no-cache-dir -e ".[dev]"

# ── Stage 2: runtime (slim, без компиляторов) ──────────────────────────────
FROM python:3.12-slim AS runtime

# Non-root пользователь для безопасности (систему НЕ ломает даже при RCE).
RUN groupadd -r crypto && useradd -r -g crypto -d /app -s /sbin/nologin crypto

WORKDIR /app

# Готовый venv из builder stage.
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /build/adapters /app/adapters
COPY --from=builder /build/core /app/core
COPY --from=builder /build/strategies /app/strategies
COPY --from=builder /build/runners /app/runners
COPY --from=builder /build/scripts /app/scripts
COPY --from=builder /build/parsers /app/parsers
COPY pyproject.toml /app/

# Директории для journal/metrics — будут смонтированы как volume.
RUN mkdir -p /var/lib/crypto && \
    chown -R crypto:crypto /app /var/lib/crypto

USER crypto

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

# Healthcheck — runner async-таск раз в 30s touch'ает heartbeat файл.
# Если файл не обновлялся >2 мин — runner повис или умер, helath = fail.
# (Раньше проверяли metrics.jsonl — но он пишется только при ордерах,
#  поэтому в "тихие" дни без сделок healthcheck ложно реджектил.)
HEALTHCHECK --interval=60s --timeout=5s --start-period=60s --retries=3 \
    CMD test "$(find /var/lib/crypto/$BINGX_SYMBOL.heartbeat -mmin -2 2>/dev/null | wc -l)" -ge 1 || exit 1

# По умолчанию BTC; перекрывается через docker-compose env / args.
ENV BINGX_SYMBOL=BTC-USDT \
    BINGX_INTERVAL=15m \
    BINGX_STRATEGY=btc_breakout

CMD ["sh", "-c", "exec python -m runners.live_runner \
    --strategy ${BINGX_STRATEGY} \
    --symbol ${BINGX_SYMBOL} \
    --interval ${BINGX_INTERVAL} \
    --warmup-candles 100 \
    --metrics-file /var/lib/crypto/${BINGX_SYMBOL}-metrics.jsonl \
    --journal-db /var/lib/crypto/${BINGX_SYMBOL}.sqlite \
    --heartbeat-file /var/lib/crypto/${BINGX_SYMBOL}.heartbeat \
    --log-level INFO"]

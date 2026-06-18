# gold-bot paper-runner. Только paper-режим — image не имеет hooks для live.
# См. plan 07 + gold-bot/CLAUDE.md §6 (запрет live без paper + явного «да»).

FROM python:3.12-slim AS base

# Системные пакеты: ca-certificates для TLS к BingX, tzdata для UTC.
# `--no-install-recommends` чтобы не тащить лишнего.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates tzdata \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=UTC

# Непривилегированный пользователь — пишет в /var/lib/gold-bot с хост-volume.
RUN useradd --create-home --uid 1000 --shell /usr/sbin/nologin goldbot

WORKDIR /app

# Зависимости отдельным слоем — для кеширования pip-слоя при правках кода.
COPY pyproject.toml ./pyproject.toml
RUN pip install \
    "pydantic>=2.10,<3" \
    "pyarrow>=16" \
    "pyyaml>=6.0,<7" \
    "ccxt>=4.4,<5"

# Код проекта. Тесты в образ не кладём — Docker для production, не для CI.
COPY backtest ./backtest
COPY config ./config
COPY exchanges ./exchanges
COPY indicators ./indicators
COPY marketdata ./marketdata
COPY paper ./paper
COPY risk ./risk
COPY scripts ./scripts
COPY strategies ./strategies

# Журнал лежит на хост-volume.
RUN mkdir -p /var/lib/gold-bot && chown -R goldbot:goldbot /var/lib/gold-bot

USER goldbot
ENV PYTHONPATH=/app

# По умолчанию — paper-runner с настройками из config/paper.yaml.
# Никаких live-команд через CMD не доступно — модули даже не импортированы.
ENTRYPOINT ["python", "-m", "scripts.run_paper"]
CMD []

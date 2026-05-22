"""Фабрика alerter из .env (общая для runner'ов и demo-скриптов).

Telegram если в .env есть оба ключа (TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID),
иначе Stdout. Stdout всегда работает (journald на VPS). Отсутствие токена
НЕ роняет вызывающего — graceful degrade.
"""

from __future__ import annotations

import logging

from core.alerts.channels import Alerter, StdoutAlerter, TelegramAlerter

logger = logging.getLogger(__name__)


def build_alerter(prefix: str = "") -> Alerter:
    """Выбрать alerter: Telegram (оба ключа в .env) или Stdout.

    ``prefix`` — instance-tag (например ``"[gtaa-vst]"``) для разделения
    источников в общем Telegram-чате.
    """
    from core.alerts.settings import TelegramSettings

    settings = TelegramSettings()
    if settings.configured:
        assert settings.chat_id is not None  # configured ⇒ оба не None
        logger.info("Alerter: Telegram (chat=%s...)", settings.chat_id[:4])
        return TelegramAlerter(
            bot_token=settings.bot_token,
            chat_id=settings.chat_id,
            prefix=prefix,
        )
    logger.info("Alerter: Stdout (TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID не заданы)")
    return StdoutAlerter(prefix=prefix)

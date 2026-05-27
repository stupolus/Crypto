"""Bybit V5 signing — HMAC-SHA256 по официальной формуле.

Документация: https://bybit-exchange.github.io/docs/v5/intro#authentication

Базис: ``timestamp + api_key + recv_window + payload``.
- ``payload`` для GET — querystring (без ведущего ``?``, параметры в
  порядке передачи).
- ``payload`` для POST — raw JSON body.

Возвращает HEX-строку нижнего регистра.
"""

from __future__ import annotations

import hashlib
import hmac


def sign_query(
    *,
    api_secret: str,
    timestamp_ms: int,
    api_key: str,
    recv_window_ms: int,
    payload: str,
) -> str:
    """Подписать запрос Bybit V5.

    ``payload`` — querystring (для GET/DELETE) или JSON-body (для POST).
    Конкатенация делается в строгом порядке, изменение порядка ломает подпись.
    """
    msg = f"{timestamp_ms}{api_key}{recv_window_ms}{payload}"
    return hmac.new(
        api_secret.encode("utf-8"),
        msg.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

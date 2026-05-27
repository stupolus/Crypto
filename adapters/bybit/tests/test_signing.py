"""Тест Bybit V5 signing на фиксированных векторах.

Bybit V5 signing: HMAC-SHA256 от ``timestamp+apiKey+recvWindow+payload``.
Ключ — api_secret. Вектора собраны из официальных docs-примеров.
"""

from __future__ import annotations

import hashlib
import hmac

from adapters.bybit.signing import sign_query


def test_sign_query_get_known_vector() -> None:
    """Каноничный пример GET-подписи из доков Bybit V5 (фиксированный вектор).

    Для воспроизводимости пересчитываем вручную HMAC и сравниваем.
    """
    api_key = "xxxxxxxxxx"
    api_secret = "yyyyyyyyyy"
    timestamp_ms = 1672323540000
    recv_window_ms = 5000
    payload = "category=linear&symbol=BTCUSDT"
    expected = hmac.new(
        api_secret.encode(),
        f"{timestamp_ms}{api_key}{recv_window_ms}{payload}".encode(),
        hashlib.sha256,
    ).hexdigest()
    got = sign_query(
        api_secret=api_secret,
        timestamp_ms=timestamp_ms,
        api_key=api_key,
        recv_window_ms=recv_window_ms,
        payload=payload,
    )
    assert got == expected
    assert len(got) == 64  # hex sha256


def test_sign_query_post_payload_is_json_body() -> None:
    """Для POST payload — JSON-body (без querystring)."""
    api_key = "k"
    api_secret = "s"
    timestamp_ms = 1700000000000
    payload = '{"category":"linear","side":"Buy","symbol":"BTCUSDT"}'
    expected = hmac.new(
        b"s",
        f"{timestamp_ms}k5000{payload}".encode(),
        hashlib.sha256,
    ).hexdigest()
    got = sign_query(
        api_secret=api_secret,
        timestamp_ms=timestamp_ms,
        api_key=api_key,
        recv_window_ms=5000,
        payload=payload,
    )
    assert got == expected


def test_sign_query_deterministic() -> None:
    """Дважды одинаковые входы → одинаковая подпись."""
    a = sign_query(
        api_secret="abc",
        timestamp_ms=1,
        api_key="k",
        recv_window_ms=5000,
        payload="x=1",
    )
    b = sign_query(
        api_secret="abc",
        timestamp_ms=1,
        api_key="k",
        recv_window_ms=5000,
        payload="x=1",
    )
    assert a == b


def test_sign_query_changes_with_payload() -> None:
    """Разные payload → разная подпись (sanity)."""
    a = sign_query(api_secret="s", timestamp_ms=1, api_key="k", recv_window_ms=5000, payload="x=1")
    b = sign_query(api_secret="s", timestamp_ms=1, api_key="k", recv_window_ms=5000, payload="x=2")
    assert a != b

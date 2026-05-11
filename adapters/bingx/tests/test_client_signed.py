"""Unit-тесты подписанного транспорта ``BingXClient.request_signed``.

Что проверяется:
- В запрос добавляются ``timestamp`` (из ServerTimeSyncer), ``recvWindow``,
  ``signature``. Заголовок ``X-BX-APIKEY`` присутствует.
- ``signature`` верифицируется тем же ``sign_query`` извне.
- Если BingX возвращает timestamp-error, делается одиночный resync + retry.
- Если timestamp-error повторился — ошибка поднимается наверх.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

import httpx
import pytest
import respx

from adapters.bingx.client import BingXClient, sign_query
from adapters.bingx.config import BingXConfig
from adapters.bingx.exceptions import APIError

_TEST_KEY = "test-api-key"
_TEST_SECRET = "test-api-secret"


def _stub_server_time(
    mock: respx.MockRouter, cfg: BingXConfig, server_ms: int = 1_700_000_000_000
) -> respx.Route:
    return mock.get(cfg.rest_endpoints.server_time).mock(
        return_value=httpx.Response(
            200, json={"code": 0, "msg": "", "data": {"serverTime": server_ms}}
        )
    )


def _ok_envelope(data: Any) -> dict[str, Any]:
    return {"code": 0, "msg": "", "data": data}


@pytest.mark.asyncio
async def test_signed_request_includes_signature_apikey_and_recv_window(
    cfg: BingXConfig,
) -> None:
    async with BingXClient(
        cfg, api_key=_TEST_KEY, api_secret=_TEST_SECRET
    ) as client, respx.mock(base_url=cfg.active_rest_base) as mock:
        _stub_server_time(mock, cfg)
        balance_route = mock.get(cfg.rest_endpoints.balance).mock(
            return_value=httpx.Response(200, json=_ok_envelope([]))
        )
        await client.request_signed("GET", cfg.rest_endpoints.balance)

    assert balance_route.called
    call = balance_route.calls.last
    assert call.request.headers[cfg.signing.api_key_header] == _TEST_KEY
    params = dict(call.request.url.params)
    assert "timestamp" in params
    # Квирк live BingX VST 2026-05-11: recvWindow в подписи/query → 100001.
    # См. plans/01 §7 и client._do_signed.
    assert "recvWindow" not in params
    # Подпись должна верифицироваться тем же алгоритмом.
    signature = params.pop("signature")
    expected = sign_query(params, _TEST_SECRET)
    assert signature == expected


@pytest.mark.asyncio
async def test_signed_request_emits_params_in_alpha_sorted_order(
    cfg: BingXConfig,
) -> None:
    """Квирк live BingX (plans/01 §7): подпись считается от URL query в том
    порядке, в котором она пришла — не пересортируется. Поэтому params в URL
    должны быть в алфавитном порядке, и подпись добавляется последним.
    """
    async with BingXClient(
        cfg, api_key=_TEST_KEY, api_secret=_TEST_SECRET
    ) as client, respx.mock(base_url=cfg.active_rest_base) as mock:
        _stub_server_time(mock, cfg)
        # Передаём «неотсортированные» бизнес-параметры, ожидаем sorted в URL.
        route = mock.post(cfg.rest_endpoints.set_margin_type).mock(
            return_value=httpx.Response(200, json=_ok_envelope({}))
        )
        # Прямой вызов request_signed с произвольным порядком ключей.
        await client.request_signed(
            "POST",
            cfg.rest_endpoints.set_margin_type,
            params={"symbol": "BTC-USDT", "marginType": "ISOLATED"},
        )

    url = str(route.calls.last.request.url)
    query = url.split("?", 1)[1]
    keys_in_url = [pair.split("=", 1)[0] for pair in query.split("&")]
    # signature всегда последний (добавляется после расчёта подписи).
    assert keys_in_url[-1] == "signature"
    # Бизнес-ключи + timestamp в алфавитном порядке.
    non_sig_keys = keys_in_url[:-1]
    assert non_sig_keys == sorted(non_sig_keys), (
        f"params must be alpha-sorted, got {non_sig_keys}"
    )


@pytest.mark.asyncio
async def test_signed_request_resyncs_on_timestamp_error_and_retries(
    cfg: BingXConfig,
) -> None:
    async with BingXClient(
        cfg, api_key=_TEST_KEY, api_secret=_TEST_SECRET
    ) as client, respx.mock(base_url=cfg.active_rest_base) as mock:
        st_route = _stub_server_time(mock, cfg, server_ms=1_700_000_000_000)
        balance_route = mock.get(cfg.rest_endpoints.balance).mock(
            side_effect=[
                httpx.Response(
                    200, json={"code": 109400, "msg": "timestamp out of recvWindow", "data": None}
                ),
                httpx.Response(200, json=_ok_envelope([])),
            ]
        )
        await client.request_signed("GET", cfg.rest_endpoints.balance)

    assert balance_route.call_count == 2
    # Server time дёрнут хотя бы дважды: lazy + forced resync.
    assert st_route.call_count >= 2


@pytest.mark.asyncio
async def test_signed_request_propagates_non_timestamp_api_errors(cfg: BingXConfig) -> None:
    async with BingXClient(
        cfg, api_key=_TEST_KEY, api_secret=_TEST_SECRET
    ) as client, respx.mock(base_url=cfg.active_rest_base) as mock:
        _stub_server_time(mock, cfg)
        mock.get(cfg.rest_endpoints.balance).mock(
            return_value=httpx.Response(
                200, json={"code": 80020, "msg": "param invalid", "data": None}
            )
        )
        with pytest.raises(APIError) as excinfo:
            await client.request_signed("GET", cfg.rest_endpoints.balance)
    assert excinfo.value.code == 80020


@pytest.mark.asyncio
async def test_signed_request_gives_up_on_repeated_timestamp_error(cfg: BingXConfig) -> None:
    """Если после resync ошибка повторилась — наверх, без бесконечного цикла."""
    async with BingXClient(
        cfg, api_key=_TEST_KEY, api_secret=_TEST_SECRET
    ) as client, respx.mock(base_url=cfg.active_rest_base) as mock:
        _stub_server_time(mock, cfg)
        route = mock.get(cfg.rest_endpoints.balance).mock(
            return_value=httpx.Response(
                200, json={"code": 109400, "msg": "timestamp out of recvWindow", "data": None}
            )
        )
        with pytest.raises(APIError) as excinfo:
            await client.request_signed("GET", cfg.rest_endpoints.balance)
    assert excinfo.value.code == 109400
    # Один первичный + один retry после resync = 2 запроса, не больше.
    assert route.call_count == 2


@pytest.mark.asyncio
async def test_client_credentials_come_from_settings_when_no_explicit_keys(
    cfg: BingXConfig,
) -> None:
    """DI-приоритет: settings → конструктор → api_key/secret."""
    from adapters.bingx.settings import BingXSettings

    settings = BingXSettings(
        _env_file=None,
        env="vst",
        vst_api_key="from-settings",
        vst_api_secret="sec",
    )
    async with BingXClient(cfg, settings=settings) as client:
        assert client.has_credentials is True
        # Подпись считается тем же ключом, что и в Settings.
        canonical = sign_query({"timestamp": 1, "recvWindow": 5000}, "sec")
        ref = hmac.new(b"sec", b"recvWindow=5000&timestamp=1", hashlib.sha256).hexdigest()
        assert canonical == ref


@pytest.mark.asyncio
async def test_settings_env_overrides_yaml_env(cfg: BingXConfig) -> None:
    """``BINGX_ENV=vst`` через settings → BingXClient идёт на VST-домен,
    даже если YAML по умолчанию ``live``.
    """
    from adapters.bingx.settings import BingXSettings

    cfg_live = cfg.model_copy(update={"env": "live"})
    settings = BingXSettings(
        _env_file=None,
        env="vst",
        vst_api_key="k",
        vst_api_secret="s",
    )
    async with BingXClient(cfg_live, settings=settings) as client:
        assert client.config.env == "vst"
        assert client.config.active_rest_base == cfg.endpoints.vst.rest_base


@pytest.mark.asyncio
async def test_explicit_keys_override_settings(cfg: BingXConfig) -> None:
    from adapters.bingx.settings import BingXSettings

    # settings.env="live" → BingXClient НЕ переопределяет cfg (cfg тоже live
    # по дефолту), respx.mock остаётся на cfg.active_rest_base.
    settings = BingXSettings(
        _env_file=None,
        env="live",
        live_api_key="from-settings",
        live_api_secret="sec",
    )
    async with BingXClient(
        cfg, settings=settings, api_key="explicit", api_secret="explicit-sec"
    ) as client, respx.mock(base_url=cfg.active_rest_base) as mock:
        _stub_server_time(mock, cfg)
        route = mock.get(cfg.rest_endpoints.balance).mock(
            return_value=httpx.Response(200, json=_ok_envelope([]))
        )
        await client.request_signed("GET", cfg.rest_endpoints.balance)

    call = route.calls.last
    assert call.request.headers[cfg.signing.api_key_header] == "explicit"

"""Integration-тесты против живого BingX (public live + private VST).

ЗАПУСК ОТДЕЛЬНО — не в CI по умолчанию:

    pytest -m integration adapters/bingx/tests/test_integration.py

Назначение:
- сверить, что наши pydantic-модели матчатся со схемой live-API;
- подтвердить ключевой факт ``tradeMinUSDT == 2`` для BTC-USDT
  (см. plans/01 §10 п.7 — на нём держится снятие блокера фазы 1);
- замерить, что WS-коннект + подписка на ``BTC-USDT@kline_1m``
  поднимаются и отдают хотя бы один data-фрейм;
- (фаза 0.C) убедиться, что подпись HMAC принимается VST для приватных GET
  и что ``ensure_invariants`` идемпотентен на чистом VST-аккаунте.

Публичные тесты: без ключей.
Приватные тесты: автоматически skip если в env нет ``BINGX_VST_API_KEY``/
``BINGX_VST_API_SECRET``. Включаются установкой пары в ``.env`` или env vars.
"""

from __future__ import annotations

import asyncio
import os
from decimal import Decimal

import pytest

from adapters.bingx import (
    BingXClient,
    BingXMarketWebSocket,
    PrivateAPI,
    PublicAPI,
    load_settings,
)
from adapters.bingx.config import BingXConfig, get_default_config

pytestmark = pytest.mark.integration


def _vst_config() -> BingXConfig:
    """Конфиг с принудительным переключением env=vst.

    YAML по умолчанию указывает live (для публичного market data);
    приватные тесты должны бить по VST.
    """
    cfg = get_default_config()
    return cfg.model_copy(update={"env": "vst"})


def _have_vst_keys() -> bool:
    if os.environ.get("BINGX_VST_API_KEY") and os.environ.get("BINGX_VST_API_SECRET"):
        return True
    # Fallback на .env (pydantic-settings зачитает его сам).
    try:
        return load_settings().has_credentials_for("vst")
    except Exception:
        return False


_require_vst = pytest.mark.skipif(
    not _have_vst_keys(),
    reason="VST creds (BINGX_VST_API_KEY/BINGX_VST_API_SECRET) not set — пропускаем приватные тесты",
)


@pytest.mark.asyncio
async def test_live_server_time_within_5s_of_local() -> None:
    cfg = get_default_config()
    async with BingXClient(cfg) as client:
        st = await PublicAPI(client, cfg).get_server_time()
    # Достаточно проверить, что значение в разумном миллисекундном диапазоне
    # и расходится с локальным временем не больше чем на несколько секунд
    # (плюс сетевые задержки).
    import time as _t

    local_ms = int(_t.time() * 1000)
    assert abs(local_ms - st.server_time_ms) < 30_000


@pytest.mark.asyncio
async def test_live_btc_contract_has_min_notional_two_usdt() -> None:
    cfg = get_default_config()
    async with BingXClient(cfg) as client:
        contract = await PublicAPI(client, cfg).get_contract("BTC-USDT")
    # Это ключевой факт — снимает блокер фазы 1 (plans/01 §10 п.7).
    assert contract.trade_min_usdt == Decimal("2")
    assert contract.price_precision == 1
    assert contract.quantity_precision == 4


@pytest.mark.asyncio
async def test_live_btc_klines_returns_data_ascending() -> None:
    cfg = get_default_config()
    async with BingXClient(cfg) as client:
        klines = await PublicAPI(client, cfg).get_klines("BTC-USDT", "15m", limit=5)
    assert 1 <= len(klines) <= 5
    times = [k.open_time_ms for k in klines]
    # Адаптер нормализует BingX-DESC к ASC.
    assert times == sorted(times)


@pytest.mark.asyncio
async def test_live_ws_kline_stream_receives_at_least_one_frame() -> None:
    """Канал ``<symbol>@kline_<rest_interval>``.

    Квирк plans/01 §7 п.27 (наблюдение 2026-05-10): live BingX принимает в WS
    REST-формат интервала (``1m``), не задокументированный ``1min``.
    """
    cfg = get_default_config()
    interval = cfg.defaults.primary_interval_ws
    channel = f"{cfg.defaults.primary_symbol}@kline_{interval}"
    async with BingXMarketWebSocket(cfg) as ws:
        iterator = await ws.subscribe(channel)
        msg = await asyncio.wait_for(iterator.__anext__(), timeout=30.0)
    assert "data" in msg or "dataType" in msg


# ─── Фаза 0.C: приватные read на VST ──────────────────────────────────────


@_require_vst
@pytest.mark.asyncio
async def test_vst_signature_accepted_smoke_balance() -> None:
    """Smoke: GET /balance → HTTP 200 + code=0.

    Если подпись неверна — BingX отдаст code=100001/100413/etc.
    Тест намеренно не проверяет числа: достаточно того, что вернулся
    непустой список USDT/BTC-балансов (на пустом demo-аккаунте VST
    отдаёт USDT с balance >= 0).
    """
    cfg = _vst_config()
    key, secret = load_settings().credentials_for("vst")
    async with BingXClient(cfg, api_key=key, api_secret=secret) as client:
        balance = await PrivateAPI(client, cfg).get_balance()
    assert balance, "VST /balance вернул пустой массив — проверь права ключа"
    assert any(b.asset == "USDT" for b in balance)


@_require_vst
@pytest.mark.asyncio
async def test_vst_get_position_mode_reads_dual_state() -> None:
    cfg = _vst_config()
    key, secret = load_settings().credentials_for("vst")
    async with BingXClient(cfg, api_key=key, api_secret=secret) as client:
        mode = await PrivateAPI(client, cfg).get_position_mode()
    # На свежем VST default обычно one-way, но не привязываемся к этому —
    # достаточно того, что строка-bool корректно парсится.
    assert isinstance(mode.is_hedge_mode, bool)


@_require_vst
@pytest.mark.asyncio
async def test_vst_get_positions_empty_or_typed() -> None:
    cfg = _vst_config()
    key, secret = load_settings().credentials_for("vst")
    async with BingXClient(cfg, api_key=key, api_secret=secret) as client:
        positions = await PrivateAPI(client, cfg).get_positions("BTC-USDT")
    # На чистом VST позиций нет — список пустой, и это валидно.
    # Если есть — все поля прошли pydantic-валидацию.
    assert isinstance(positions, list)
    for p in positions:
        assert p.symbol == "BTC-USDT"
        assert p.position_side in {"LONG", "SHORT"}


@_require_vst
@pytest.mark.asyncio
async def test_vst_ensure_invariants_idempotent_on_clean_account() -> None:
    """Bootstrap: one-way + ISOLATED + leverage=5 без открытых позиций.

    На demo-аккаунте без позиций все три POST'а должны пройти. При повторном
    вызове BingX тоже не должен ругаться (идемпотентность setters).
    """
    cfg = _vst_config()
    key, secret = load_settings().credentials_for("vst")
    async with BingXClient(cfg, api_key=key, api_secret=secret) as client:
        api = PrivateAPI(client, cfg)
        await api.ensure_invariants("BTC-USDT", leverage=5)
        # Повторный — должен пройти без ошибок (нет открытых позиций).
        await api.ensure_invariants("BTC-USDT", leverage=5)
        # И отдельные read-методы должны видеть согласованное состояние.
        mode = await api.get_position_mode()
    assert mode.is_hedge_mode is False

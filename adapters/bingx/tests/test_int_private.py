"""Integration-тесты приватного API против реального BingX **VST**.

Запуск: ``pytest -m integration``. Тесты пропускаются (skip), если в
окружении не выставлены ``BINGX_VST_API_KEY`` / ``BINGX_VST_API_SECRET``.

Все тесты — на demo (VST), реальные деньги не задействованы. Никаких ордеров
здесь не размещается; только: read + idempotent setters параметров аккаунта.

Безопасность:
- ключ должен быть с правами «только торговля, без вывода средств»;
- IP whitelist на стороне BingX — обязателен (VPS-IP + рабочий IP);
- если у тебя на VST случайно есть открытая позиция — тест ``set_position_mode``
  будет пропущен (BingX не даёт переключить режим при открытых позициях).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from adapters.bingx.client import BingXClient
from adapters.bingx.config import BingXConfig, load_config
from adapters.bingx.private import PrivateAPI
from adapters.bingx.settings import BingXSettings

pytestmark = pytest.mark.integration


def _settings_or_skip() -> BingXSettings:
    """Загрузить BingXSettings, либо пропустить тест."""
    settings = BingXSettings()
    if not (settings.env == "vst" and settings.has_credentials()):
        pytest.skip("BINGX_VST_API_KEY / BINGX_VST_API_SECRET не заданы — пропускаем")
    return settings


@pytest.fixture(scope="module")
def vst_cfg() -> BingXConfig:
    """Конфиг YAML; ``BingXClient`` сам переключит env на vst по settings."""
    return load_config()


@pytest.fixture(scope="module")
def settings() -> BingXSettings:
    return _settings_or_skip()


@pytest.fixture
async def client(vst_cfg: BingXConfig, settings: BingXSettings) -> AsyncIterator[BingXClient]:
    async with BingXClient(vst_cfg, settings=settings) as c:
        yield c


@pytest.fixture
def api(client: BingXClient) -> PrivateAPI:
    return PrivateAPI(client)


@pytest.mark.asyncio
async def test_int_get_balance_returns_vst_or_usdt(api: PrivateAPI) -> None:
    """На VST аккаунте актив называется ``VST`` (виртуальный USDT). На live
    аккаунте — ``USDT``. Тест принимает оба варианта.
    """
    balances = await api.get_balance()
    assert balances, "ожидаем хотя бы один актив"
    assets = {b.asset for b in balances}
    assert assets & {"VST", "USDT"}, f"ни VST, ни USDT не найдены: {assets}"


@pytest.mark.asyncio
async def test_int_set_margin_isolated_btc_usdt_is_idempotent(
    api: PrivateAPI,
) -> None:
    """Дважды выставляем ISOLATED — не должно бросать."""
    await api.set_margin_mode("BTC-USDT", "ISOLATED")
    await api.set_margin_mode("BTC-USDT", "ISOLATED")


@pytest.mark.asyncio
async def test_int_set_leverage_btc_usdt_3x(api: PrivateAPI) -> None:
    """3x — точно входит в cap любого symbol."""
    await api.set_leverage("BTC-USDT", 3)


@pytest.mark.asyncio
async def test_int_set_position_mode_one_way(api: PrivateAPI) -> None:
    """Переключение в one-way. Если открыта позиция — BingX не даёт; пропускаем."""
    positions = await api.get_positions()
    if any(p.position_amount != 0 for p in positions):
        pytest.skip("на VST есть открытая позиция — переключение режима недоступно")
    await api.set_position_mode(one_way=True)


@pytest.mark.asyncio
async def test_int_get_positions_returns_list(api: PrivateAPI) -> None:
    positions = await api.get_positions()
    assert isinstance(positions, list)


@pytest.mark.asyncio
async def test_int_smoke_full_flow(api: PrivateAPI) -> None:
    """Полный smoke: set_margin → set_leverage → get_balance — без падений."""
    await api.set_margin_mode("BTC-USDT", "ISOLATED")
    await api.set_leverage("BTC-USDT", 3)
    balances = await api.get_balance()
    assert balances

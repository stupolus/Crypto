"""Загрузка и валидация ``adapters/bingx/config.yaml``.

Принципы:
- Все числа — в YAML, не в коде. Здесь только schema + загрузка.
- Pydantic строгий: лишние поля → ConfigError, чтобы YAML и Python не разъезжались.
- Один источник истины — рядом с этим модулем (``config.yaml``).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from adapters.bingx.exceptions import ConfigError

DEFAULT_CONFIG_PATH = Path(__file__).parent / "config.yaml"


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EnvUrls(_StrictModel):
    rest_base: str
    ws_market: str


class Endpoints(_StrictModel):
    live: EnvUrls
    vst: EnvUrls
    backup_rest_base: str


class RetryConfig(_StrictModel):
    max_attempts: int = Field(ge=1)
    backoff_initial_s: float = Field(gt=0)
    backoff_factor: float = Field(gt=1)
    backoff_max_s: float = Field(gt=0)
    retryable_statuses: tuple[int, ...]


class HttpConfig(_StrictModel):
    connect_timeout_s: float = Field(gt=0)
    read_timeout_s: float = Field(gt=0)
    total_timeout_s: float = Field(gt=0)
    retry: RetryConfig


class TokenBucketConfig(_StrictModel):
    capacity: int = Field(gt=0)
    window_s: float = Field(gt=0)


class RateLimitsConfig(_StrictModel):
    market_data: TokenBucketConfig
    place_order_per_sec: int
    cancel_order_per_sec: int
    set_leverage_per_sec: int
    set_margin_type_per_sec: int
    set_position_mode_per_sec: int


class SigningConfig(_StrictModel):
    algorithm: Literal["HMAC-SHA256"]
    api_key_header: str
    recv_window_ms: int = Field(gt=0)
    server_time_resync_interval_s: float = Field(gt=0)


class RestEndpoints(_StrictModel):
    # Public (фаза 0.B)
    server_time: str
    contracts: str
    ticker: str
    klines: str
    premium_index: str
    funding_rate_history: str
    open_interest: str
    # Private read (фаза 0.C)
    balance: str
    positions: str
    open_orders: str
    fills: str
    # Private setters (фаза 0.C, idempotent)
    set_margin_type: str
    set_leverage: str
    set_position_mode: str
    # Trade (фаза 0.D part 1)
    place_order: str
    cancel_order: str
    cancel_all_orders: str
    # Trade (фаза 0.D part 2)
    cancel_all_after: str
    user_data_stream: str


class KlinesConfig(_StrictModel):
    limit_default: int = Field(gt=0)
    limit_max: int = Field(gt=0)
    intervals_rest: tuple[str, ...]
    intervals_ws: tuple[str, ...]


class WsReconnectConfig(_StrictModel):
    initial_delay_s: float = Field(gt=0)
    factor: float = Field(gt=1)
    max_delay_s: float = Field(gt=0)


class WebSocketConfig(_StrictModel):
    compression: Literal["gzip"]
    ping_text: str
    pong_text: str
    ping_expected_interval_s: float = Field(gt=0)
    pong_deadline_s: float = Field(gt=0)
    watchdog_silence_s: float = Field(gt=0)
    reconnect: WsReconnectConfig
    max_topics_per_connection: int = Field(gt=0)
    max_connections_per_ip: int = Field(gt=0)
    subscribe_ack_timeout_s: float = Field(gt=0)


class PlaceOrderConfig(_StrictModel):
    compensating_check_delay_ms: int = Field(ge=0)
    compensating_check_attempts: int = Field(ge=1)
    compensating_check_backoff_factor: float = Field(gt=1)


class UserDataStreamConfig(_StrictModel):
    keep_alive_interval_s: float = Field(gt=0)
    reconnect_initial_delay_s: float = Field(gt=0)
    reconnect_max_delay_s: float = Field(gt=0)
    reconnect_factor: float = Field(gt=1)
    watchdog_silence_s: float = Field(gt=0)


class CancelAllAfterConfig(_StrictModel):
    default_window_ms: int = Field(gt=0)
    refresh_interval_s: float = Field(gt=0)


class DefaultsConfig(_StrictModel):
    primary_symbol: str
    primary_interval_rest: str
    primary_interval_ws: str
    smoke_klines_limit: int = Field(gt=0)


class InvariantsConfig(_StrictModel):
    position_mode: Literal["one_way"]
    margin_type: Literal["ISOLATED"]
    attached_stop_required: bool


class BingXConfig(_StrictModel):
    env: Literal["live", "vst"]
    endpoints: Endpoints
    http: HttpConfig
    rate_limits: RateLimitsConfig
    signing: SigningConfig
    rest_endpoints: RestEndpoints
    klines: KlinesConfig
    websocket: WebSocketConfig
    place_order: PlaceOrderConfig
    user_data_stream: UserDataStreamConfig
    cancel_all_after: CancelAllAfterConfig
    defaults: DefaultsConfig
    invariants: InvariantsConfig

    @property
    def active_rest_base(self) -> str:
        """REST-домен текущего окружения (live/vst)."""
        return self.endpoints.live.rest_base if self.env == "live" else self.endpoints.vst.rest_base

    @property
    def active_ws_market(self) -> str:
        return self.endpoints.live.ws_market if self.env == "live" else self.endpoints.vst.ws_market


def load_config(path: Path | None = None) -> BingXConfig:
    """Прочитать YAML и провалидировать. ``path=None`` → дефолтный config.yaml рядом."""
    target = path or DEFAULT_CONFIG_PATH
    try:
        raw = yaml.safe_load(target.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise ConfigError(f"BingX config not found: {target}") from e
    except yaml.YAMLError as e:
        raise ConfigError(f"BingX config YAML parse error in {target}: {e}") from e
    if not isinstance(raw, dict):
        raise ConfigError(f"BingX config root must be mapping, got {type(raw).__name__}")
    try:
        return BingXConfig.model_validate(raw)
    except ValidationError as e:
        raise ConfigError(f"BingX config validation failed: {e}") from e


@lru_cache(maxsize=1)
def get_default_config() -> BingXConfig:
    """Кэшированная загрузка дефолтного конфига для горячего пути."""
    return load_config(None)

"""Список зарегистрированных стратегий + их дефолтные конфиги.

Discovery утилита: когда пользователь хочет посмотреть какие стратегии
доступны, какой у каждой timeframe / symbol / risk tier — одной командой.

Запуск:
    .venv/bin/python -m scripts.list_strategies
    .venv/bin/python -m scripts.list_strategies --json  # для grep/jq

Не запускает ничего — только inspect.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from typing import Any


def _strategies() -> dict[str, Callable[[], Any]]:
    """Map имя → loader default config. Loader вызывается lazy."""
    from strategies.btc_breakout.config import get_default_config as btc_breakout
    from strategies.trend_ema_4h.config import get_default_config as trend_ema_4h
    from strategies.us_session_breakout.config import (
        get_default_config as us_session_breakout,
    )

    return {
        "btc_breakout": btc_breakout,
        "us_session_breakout": us_session_breakout,
        "trend_ema_4h": trend_ema_4h,
    }


def collect_info() -> list[dict[str, Any]]:
    """Загрузить дефолты всех стратегий → список info-dict'ов."""
    result: list[dict[str, Any]] = []
    for name, loader in _strategies().items():
        try:
            config = loader()
            result.append(
                {
                    "name": name,
                    "symbol": getattr(config, "symbol", "?"),
                    "timeframe": getattr(config, "timeframe", "?"),
                    "risk_tier": str(getattr(config, "risk_tier", "?")),
                    "config_fields": _config_to_dict(config),
                }
            )
        except Exception as e:
            result.append(
                {
                    "name": name,
                    "error": f"{type(e).__name__}: {e}",
                }
            )
    return result


def _config_to_dict(config: Any) -> dict[str, Any]:
    """Pydantic model → dict (без __fields_set__ и прочих internals)."""
    if hasattr(config, "model_dump"):
        # pydantic v2
        result: dict[str, Any] = config.model_dump(mode="json")
        return result
    # Fallback — vars()
    return {k: v for k, v in vars(config).items() if not k.startswith("_")}


def format_text(infos: list[dict[str, Any]]) -> str:
    """Human-readable текст."""
    lines: list[str] = ["Registered strategies:", ""]
    for info in infos:
        if "error" in info:
            lines.append(f"  ✗ {info['name']} — {info['error']}")
            continue
        lines.append(f"  • {info['name']}")
        lines.append(f"      symbol={info['symbol']} timeframe={info['timeframe']}")
        lines.append(f"      risk_tier={info['risk_tier']}")
        cfg = info["config_fields"]
        for key, val in sorted(cfg.items()):
            if key in {"symbol", "timeframe", "risk_tier"}:
                continue
            lines.append(f"        {key}: {val}")
        lines.append("")
    return "\n".join(lines)


def run(as_json: bool) -> int:
    infos = collect_info()
    if as_json:
        print(json.dumps(infos, indent=2, ensure_ascii=False, default=str))
    else:
        print(format_text(infos))
    # Exit code: 0 если все load'ились, 1 если хоть одна с ошибкой
    has_errors = any("error" in info for info in infos)
    return 1 if has_errors else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Список стратегий + дефолтные конфиги")
    parser.add_argument(
        "--json",
        action="store_true",
        help="JSON output (для скриптов / jq)",
    )
    args = parser.parse_args()
    sys.exit(run(args.json))


if __name__ == "__main__":
    main()

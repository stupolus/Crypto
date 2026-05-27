"""Bybit data-probe: эмпирически проверить, что Bybit даёт по BTCUSDT.

Read-only public REST endpoints V5. Без auth (опционально использует
``BYBIT_API_KEY`` для повышения rate-limit, но не обязательно).
**Никаких trading-методов** — этот скрипт нельзя превратить в bot
случайно (нет подписи запросов, нет /v5/order/*).

Запуск (с VPS — из cloud-контейнера Bybit гео-заблокирован):
    python scripts/bybit_data_probe.py
    python scripts/bybit_data_probe.py --symbols BTCUSDT,ETHUSDT
    python scripts/bybit_data_probe.py --json   # машиночитаемый вывод

Цель: получить таблицу глубины истории на 1m/5m/15m/1h/4h/6h/1d для
сравнения с BingX/Coinglass. По результату решаем, стоит ли вообще
проводить Bybit как источник в трейдер-бот (план 01 §6k).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

_BYBIT_BASE = "https://api.bybit.com"
# Bybit V5 kline intervals: 1,3,5,15,30,60,120,240,360,720 (мин), D, W, M.
_INTERVAL_MAP = {
    "1m": "1",
    "5m": "5",
    "15m": "15",
    "1h": "60",
    "4h": "240",
    "6h": "360",
    "1d": "D",
}
# OI history принимает только: 5min, 15min, 30min, 1h, 4h, 1d.
_OI_INTERVAL_MAP = {
    "5m": "5min",
    "15m": "15min",
    "1h": "1h",
    "4h": "4h",
    "1d": "1d",
}
_DEFAULT_SYMBOLS = ["BTCUSDT"]
_DEFAULT_TFS = ["1m", "5m", "15m", "1h", "4h", "6h", "1d"]
_CATEGORY = "linear"  # USDT-perp


@dataclass
class ProbeResult:
    endpoint: str
    symbol: str
    tf: str
    ok: bool
    points: int
    oldest_utc: str | None
    newest_utc: str | None
    error: str | None = None


def _headers() -> dict[str, str]:
    """Опционально подписываем заголовком ключ (для лимитов).

    Bybit публичные эндпоинты работают и без ключа; ключ не подписываем
    HMAC'ом — public-only, никаких signed requests.
    """
    key = os.environ.get("BYBIT_API_KEY")
    return {"X-BAPI-API-KEY": key} if key else {}


def _ts_fmt(ms: int | None) -> str | None:
    if ms is None:
        return None
    return datetime.fromtimestamp(ms / 1000, UTC).strftime("%Y-%m-%d %H:%M UTC")


def _get(client: httpx.Client, path: str, **params: str | int) -> dict[str, Any]:
    r = client.get(_BYBIT_BASE + path, params=params, headers=_headers(), timeout=20)
    return r.json()  # type: ignore[no-any-return]


def probe_klines(client: httpx.Client, symbol: str, tf: str, limit: int = 1000) -> ProbeResult:
    iv = _INTERVAL_MAP.get(tf)
    if iv is None:
        return ProbeResult("kline", symbol, tf, False, 0, None, None, "unsupported tf")
    data = _get(
        client,
        "/v5/market/kline",
        category=_CATEGORY,
        symbol=symbol,
        interval=iv,
        limit=limit,
    )
    if data.get("retCode") != 0:
        return ProbeResult("kline", symbol, tf, False, 0, None, None, data.get("retMsg", "err"))
    rows = (data.get("result") or {}).get("list") or []
    # Bybit kline rows: [startTime, open, high, low, close, volume, turnover],
    # сортировка от newest к oldest.
    ts = [int(r[0]) for r in rows]
    ts.sort()
    return ProbeResult(
        "kline",
        symbol,
        tf,
        True,
        len(rows),
        _ts_fmt(ts[0] if ts else None),
        _ts_fmt(ts[-1] if ts else None),
    )


def probe_open_interest(
    client: httpx.Client, symbol: str, tf: str, limit: int = 200
) -> ProbeResult:
    iv = _OI_INTERVAL_MAP.get(tf)
    if iv is None:
        return ProbeResult("oi", symbol, tf, False, 0, None, None, "tf not in OI map")
    data = _get(
        client,
        "/v5/market/open-interest",
        category=_CATEGORY,
        symbol=symbol,
        intervalTime=iv,
        limit=limit,
    )
    if data.get("retCode") != 0:
        return ProbeResult("oi", symbol, tf, False, 0, None, None, data.get("retMsg", "err"))
    rows = (data.get("result") or {}).get("list") or []
    ts = [int(r.get("timestamp", 0)) for r in rows]
    ts.sort()
    return ProbeResult(
        "oi",
        symbol,
        tf,
        True,
        len(rows),
        _ts_fmt(ts[0] if ts else None),
        _ts_fmt(ts[-1] if ts else None),
    )


def probe_funding(client: httpx.Client, symbol: str, limit: int = 200) -> ProbeResult:
    data = _get(
        client,
        "/v5/market/funding/history",
        category=_CATEGORY,
        symbol=symbol,
        limit=limit,
    )
    if data.get("retCode") != 0:
        return ProbeResult("funding", symbol, "8h", False, 0, None, None, data.get("retMsg", "err"))
    rows = (data.get("result") or {}).get("list") or []
    ts = [int(r.get("fundingRateTimestamp", 0)) for r in rows]
    ts.sort()
    return ProbeResult(
        "funding",
        symbol,
        "8h",
        True,
        len(rows),
        _ts_fmt(ts[0] if ts else None),
        _ts_fmt(ts[-1] if ts else None),
    )


def server_time(client: httpx.Client) -> dict[str, Any]:
    return _get(client, "/v5/market/time")


def main() -> None:
    p = argparse.ArgumentParser(description="Bybit V5 data depth probe (read-only)")
    p.add_argument("--symbols", default=",".join(_DEFAULT_SYMBOLS))
    p.add_argument("--tfs", default=",".join(_DEFAULT_TFS))
    p.add_argument("--json", action="store_true", help="JSON-вывод вместо таблицы")
    args = p.parse_args()
    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    tfs = [t.strip() for t in args.tfs.split(",") if t.strip()]

    with httpx.Client() as client:
        st = server_time(client)
        if st.get("retCode") != 0:
            print(f"⚠️ server/time failed: {st}", file=sys.stderr)
            sys.exit(1)
        print(
            f"Bybit server time: {st.get('result', {}).get('timeSecond')} "
            f"(retCode={st.get('retCode')})"
        )

        results: list[ProbeResult] = []
        for sym in symbols:
            for tf in tfs:
                results.append(probe_klines(client, sym, tf))
                if tf in _OI_INTERVAL_MAP:
                    results.append(probe_open_interest(client, sym, tf))
            results.append(probe_funding(client, sym))

    if args.json:
        print(json.dumps([asdict(r) for r in results], indent=2, ensure_ascii=False))
        return

    print(f"\n{'endpoint':10} {'symbol':10} {'tf':5} {'ok':3} {'pts':>5}  range")
    print("-" * 80)
    for r in results:
        line = (
            f"{r.endpoint:10} {r.symbol:10} {r.tf:5} "
            f"{'✓' if r.ok else '✗':3} {r.points:>5}  "
            f"{r.oldest_utc or '-'} .. {r.newest_utc or '-'}"
        )
        if r.error:
            line += f"  ERR={r.error}"
        print(line)


if __name__ == "__main__":
    main()

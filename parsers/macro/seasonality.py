"""Сезонность + рыночный режим для акций (план 24 фаза 24.1).

Источник паттернов — БАЗОВЫЙ актив (десятилетия истории Yahoo,
без ключа), НЕ короткий перп BingX. Используется как ФИЛЬТР/режим
над ценовой стратегией перпа (принцип №1: не триггер).

- ``month_bias(sym, month)`` → BULL/BEAR/NEUTRAL по 10-лет
  помесячной статистике (avg return + win-rate). Пороги — из
  данных/публичных аномалий (эффект сентября), не подгон.
- ``market_regime(index)`` → RISK_ON/RISK_OFF по индексу vs его
  10-мес SMA (≈200-дн): risk-off → не лонг акции.

Graceful: Yahoo заблокирован/429 → NEUTRAL/UNKNOWN (фильтр no-op,
бэктест/раннер не падает).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

import httpx

logger = logging.getLogger(__name__)

_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_TIMEOUT_S = 20.0
_RETRIES = 4

# Сильным сигналом считаем месяц с экстремальным win-rate за 10 лет.
# Сентябрь (эффект сентября) и июль (летнее ралли) — устойчивы на
# данных AAPL/S&P (план 24). Пороги документированы, не из перебора.
_BULL_WINRATE = 0.70
_BEAR_WINRATE = 0.40
_REGIME_SMA_MONTHS = 10  # ≈200 торговых дней


class MonthBias(StrEnum):
    BULL = "BULL"
    BEAR = "BEAR"
    NEUTRAL = "NEUTRAL"


class MarketRegime(StrEnum):
    RISK_ON = "RISK_ON"
    RISK_OFF = "RISK_OFF"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class MonthStat:
    month: int
    avg_return_pct: float
    win_rate: float
    samples: int


def _fetch_monthly_closes(
    symbol: str,
    *,
    years: int = 10,
    client: httpx.Client | None = None,
    backoff: float = 2.0,
) -> list[tuple[int, float]]:
    """[(timestamp_s, close)] помесячно. Пусто при блоке/ошибке."""
    owns = client is None
    cli = client or httpx.Client(timeout=_TIMEOUT_S, follow_redirects=True)
    try:
        for attempt in range(_RETRIES):
            try:
                resp = cli.get(
                    _CHART_URL.format(sym=symbol),
                    params={"range": f"{years}y", "interval": "1mo"},
                    headers={"User-Agent": _BROWSER_UA},
                )
                if resp.status_code == 200:
                    body = resp.json()
                    break
                time.sleep(backoff * (2**attempt))
            except httpx.HTTPError as e:
                logger.warning("Yahoo %s attempt %d: %s", symbol, attempt, e)
                time.sleep(backoff * (2**attempt))
        else:
            return []
    finally:
        if owns:
            cli.close()
    try:
        res = body["chart"]["result"][0]
        ts = res["timestamp"]
        closes = res["indicators"]["quote"][0]["close"]
    except (KeyError, IndexError, TypeError):
        return []
    return [(int(t), float(c)) for t, c in zip(ts, closes, strict=False) if c]


def compute_month_stats(
    symbol: str,
    *,
    years: int = 10,
    client: httpx.Client | None = None,
    backoff: float = 2.0,
) -> dict[int, MonthStat]:
    """Помесячная статистика close-to-close доходности базового актива."""
    series = _fetch_monthly_closes(symbol, years=years, client=client, backoff=backoff)
    if len(series) < 13:
        return {}
    by_month: dict[int, list[float]] = {}
    for i in range(1, len(series)):
        prev_c = series[i - 1][1]
        if prev_c <= 0:
            continue
        ret = (series[i][1] / prev_c - 1.0) * 100.0
        month = datetime.fromtimestamp(series[i][0], tz=UTC).month
        by_month.setdefault(month, []).append(ret)
    out: dict[int, MonthStat] = {}
    for month, rets in by_month.items():
        n = len(rets)
        wins = sum(1 for r in rets if r > 0)
        out[month] = MonthStat(
            month=month,
            avg_return_pct=sum(rets) / n,
            win_rate=wins / n,
            samples=n,
        )
    return out


def month_bias(stats: dict[int, MonthStat], month: int) -> MonthBias:
    """BULL/BEAR/NEUTRAL по win-rate + знаку среднего за 10 лет.

    BULL: win ≥ 0.70 и среднее > 0. BEAR: win ≤ 0.40 или
    (среднее < 0 и win < 0.5). Иначе NEUTRAL. Пороги из плана 24.
    """
    st = stats.get(month)
    if st is None or st.samples < 5:
        return MonthBias.NEUTRAL
    if st.win_rate >= _BULL_WINRATE and st.avg_return_pct > 0:
        return MonthBias.BULL
    if st.win_rate <= _BEAR_WINRATE or (st.avg_return_pct < 0 and st.win_rate < 0.5):
        return MonthBias.BEAR
    return MonthBias.NEUTRAL


def market_regime(
    index_symbol: str = "^GSPC",
    *,
    client: httpx.Client | None = None,
    backoff: float = 2.0,
) -> MarketRegime:
    """RISK_ON/RISK_OFF: индекс vs его 10-мес SMA. UNKNOWN при блоке."""
    series = _fetch_monthly_closes(index_symbol, years=3, client=client, backoff=backoff)
    if len(series) <= _REGIME_SMA_MONTHS:
        return MarketRegime.UNKNOWN
    closes = [c for _, c in series]
    sma = sum(closes[-_REGIME_SMA_MONTHS:]) / _REGIME_SMA_MONTHS
    return MarketRegime.RISK_ON if closes[-1] >= sma else MarketRegime.RISK_OFF


def regime_history(
    index_symbol: str = "^GSPC",
    *,
    years: int = 10,
    client: httpx.Client | None = None,
    backoff: float = 2.0,
) -> dict[tuple[int, int], MarketRegime]:
    """{(год, месяц): RISK_ON/OFF} по trailing 10-мес SMA.

    Look-ahead-safe: режим месяца M = close[M] vs SMA закрытий
    месяцев (M-9..M) — только прошлое. Для гейта в бэктесте:
    режим на момент входа берётся по (год, месяц) входа. Пусто
    при блоке Yahoo → гейт no-op.
    """
    series = _fetch_monthly_closes(index_symbol, years=years, client=client, backoff=backoff)
    if len(series) <= _REGIME_SMA_MONTHS:
        return {}
    out: dict[tuple[int, int], MarketRegime] = {}
    for i in range(_REGIME_SMA_MONTHS - 1, len(series)):
        window = [c for _, c in series[i - _REGIME_SMA_MONTHS + 1 : i + 1]]
        sma = sum(window) / _REGIME_SMA_MONTHS
        dt = datetime.fromtimestamp(series[i][0], tz=UTC)
        out[(dt.year, dt.month)] = (
            MarketRegime.RISK_ON if series[i][1] >= sma else MarketRegime.RISK_OFF
        )
    return out

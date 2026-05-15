"""Open-interest trend detector — gate методологии Щукина.

Открытый интерес (OI) — сумма всех открытых позиций по инструменту.
В методологии (см. бизнес/материалы/курсы/dmitry-shukin/правила-входа.md):

- SHORT-reversal: НЕ открывать пока OI растёт; вход когда OI начал
  падать (позиции принудительно закрываются после ликвидаций).
- LONG-reversal: подтверждение когда OI перестаёт падать / растёт
  (новые деньги в лонг).
- OI-breakout (сетап B): OI резко растёт ИЗ НИЗКОЙ БАЗЫ монотонно
  синхронно с ценой — ранний trend-entry.

Pure-function detector. BingX `/quote/openInterest` отдаёт snapshot,
поэтому caller накапливает ряд (периодический poll) и передаёт сюда.
Для бэктеста нужен исторический OI (Coinglass) — см. что-проверить.md B1.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

logger = logging.getLogger(__name__)

_HUNDRED = Decimal("100")


class OIState(StrEnum):
    RISING = "RISING"
    FALLING = "FALLING"
    FLAT = "FLAT"


@dataclass(frozen=True)
class OpenInterestConfig:
    """Пороги OI-детектора.

    ``rise_pct`` / ``fall_pct`` — изменение OI (в %) за ``lookback``
    точек, выше/ниже которого считаем RISING / FALLING. Между — FLAT.

    ``from_low_lookback`` — окно для проверки «из низкой базы»: текущий
    OI у минимума окна, затем резкий рост = breakout (сетап B).
    """

    rise_pct: Decimal = Decimal("3.0")
    fall_pct: Decimal = Decimal("3.0")
    lookback: int = 6
    from_low_lookback: int = 24
    min_history: int = 6


@dataclass(frozen=True)
class OpenInterestSignal:
    """Состояние OI на текущем срезе.

    ``state`` — RISING / FALLING / FLAT за lookback.
    ``change_pct`` — изменение OI за lookback (в %).
    ``breakout_from_low`` — True если OI рос из низкой базы окна
    from_low_lookback (кандидат на сетап B OI-breakout).
    """

    state: OIState
    change_pct: Decimal
    breakout_from_low: bool
    reason: str


def detect_oi_trend(
    oi_history: Sequence[Decimal],
    config: OpenInterestConfig | None = None,
) -> OpenInterestSignal | None:
    """Классифицировать тренд открытого интереса.

    Args:
        oi_history: ряд значений OI, ASC по времени (oldest → newest).
            Последний элемент — текущий OI.
        config: пороги (опц.).

    Returns:
        ``OpenInterestSignal`` или ``None`` если истории мало.

    Логика:
    - change_pct = (OI_now - OI_[lookback назад]) / OI_[lookback] * 100
    - >= rise_pct → RISING; <= -fall_pct → FALLING; иначе FLAT
    - breakout_from_low: OI_[from_low окно назад] был у минимума окна
      И сейчас RISING → ранний сетап B.
    """
    cfg = config or OpenInterestConfig()
    n = len(oi_history)
    if n < max(cfg.min_history, cfg.lookback + 1):
        logger.debug("oi_trend: history %d too short, skip", n)
        return None

    oi_now = oi_history[-1]
    oi_ref = oi_history[-1 - cfg.lookback]
    if oi_ref <= 0:
        return None

    change_pct = (oi_now - oi_ref) / oi_ref * _HUNDRED
    if change_pct >= cfg.rise_pct:
        state = OIState.RISING
    elif change_pct <= -cfg.fall_pct:
        state = OIState.FALLING
    else:
        state = OIState.FLAT

    breakout_from_low = False
    if state == OIState.RISING and n >= cfg.from_low_lookback:
        window = oi_history[-cfg.from_low_lookback :]
        window_min = min(window)
        window_max = max(window)
        if window_max > 0:
            # Старт окна был около минимума (низкая база), сейчас вышли вверх.
            start_val = window[0]
            span = window_max - window_min
            near_low = span > 0 and (start_val - window_min) <= span * Decimal("0.25")
            breakout_from_low = near_low

    return OpenInterestSignal(
        state=state,
        change_pct=change_pct,
        breakout_from_low=breakout_from_low,
        reason=(
            f"OI {state.value} {change_pct:+.2f}% за {cfg.lookback} срезов"
            + (" · breakout из низкой базы" if breakout_from_low else "")
        ),
    )

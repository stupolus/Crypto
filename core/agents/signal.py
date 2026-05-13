"""SignalCandidate — структурированный сигнал от Layer 2 для подачи в Layer 3.

Layer 2 (rule-based стратегии: btc_breakout, us_session_breakout, etc.)
выдают SignalCandidate когда их условие сработало. Это **кандидат**,
не финальный action — Layer 3 (AgentTeam) решит брать его или нет.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal

SignalAction = Literal["BUY", "SELL"]


@dataclass(frozen=True)
class SignalCandidate:
    """Сигнал-кандидат от стратегии Layer 2.

    Поля:
    - ``symbol`` — например "BTC-USDT"
    - ``action`` — направление кандидата (BUY/SELL)
    - ``timestamp_ms`` — когда сигнал сработал
    - ``strategy_name`` — какая стратегия выдала (для аудита)
    - ``confidence_raw`` — стратегия сама может оценить (0..1)
    - ``indicators`` — словарь индикаторов на момент сигнала
    - ``proposed_entry`` / ``proposed_sl`` / ``proposed_tp`` — стратегия
      может предложить уровни (Coordinator может их уточнить)
    """

    symbol: str
    action: SignalAction
    timestamp_ms: int
    strategy_name: str
    confidence_raw: float = 0.5
    indicators: dict[str, Any] = field(default_factory=dict)
    proposed_entry: Decimal | None = None
    proposed_sl: Decimal | None = None
    proposed_tp: tuple[Decimal, ...] = ()

    def to_context(self) -> dict[str, Any]:
        """Сериализация в dict для подачи в Coordinator promprt."""
        return {
            "symbol": self.symbol,
            "action": self.action,
            "timestamp_ms": self.timestamp_ms,
            "strategy": self.strategy_name,
            "confidence_raw": self.confidence_raw,
            "indicators": self.indicators,
            "proposed_entry": str(self.proposed_entry) if self.proposed_entry else None,
            "proposed_sl": str(self.proposed_sl) if self.proposed_sl else None,
            "proposed_tp": [str(p) for p in self.proposed_tp],
        }

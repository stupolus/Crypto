"""DashboardState — read-only сборщик данных для API.

Все данные тащим из существующих источников:
- TradeOutcomeLogger SQLite — trades + LLM payloads
- HaltFlag file — emergency halt status
- Heartbeat file (если runner с --heartbeat-file) — proof of life

В первой версии BingX live данные (current position, equity) НЕ
запрашиваем — это требует API keys в dashboard процессе, что усложняет
безопасность. Live equity подтянем через runner → периодический snapshot
в SQLite (отдельный PR).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from core.postmortem.logger import TradeOutcomeLogger
from core.postmortem.models import TradeOutcome

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HealthInfo:
    status: str  # "ok" | "stale" (heartbeat too old) | "halted"
    uptime_s: float | None  # время с последнего heartbeat touch
    runner_heartbeat_age_s: float | None
    halt_active: bool
    halt_reason: dict[str, str] | None


@dataclass(frozen=True)
class TradeSummary:
    """Слепок одной TradeOutcome для UI list view."""

    trade_id: str
    symbol: str
    side: str
    entry_time_ms: int
    entry_price: str
    exit_time_ms: int | None
    exit_price: str | None
    pnl_pct: str | None
    exit_reason: str | None
    holding_time_min: int | None
    is_closed: bool
    is_win: bool
    is_loss: bool


@dataclass(frozen=True)
class AgentSnapshot:
    """Последний decision одного из 5 LLM-агентов."""

    name: str  # "market_analyst" | "sentiment_analyst" | "risk_overseer" | "macro_analyst" | "coordinator"
    last_payload: dict[str, Any]
    last_trade_id: str
    last_decision_at_ms: int


class DashboardState:
    """Read-only фасад над outcomes journal + filesystem state.

    Используется FastAPI route'ами. Все методы быстрые (SQLite + filesystem).
    """

    def __init__(
        self,
        *,
        outcomes_db: Path | str | list[Path | str],
        halt_flag_file: Path | str | None = None,
        heartbeat_file: Path | str | None = None,
        runner_start_ts: float | None = None,
    ) -> None:
        # Accept либо одиночный путь, либо список путей. Список — для
        # multi-runner setup (отдельный outcomes-db per strategy).
        # Глоб типа "/var/lib/crypto/llm-*-outcomes.sqlite" разворачивается
        # вызывающим (server.py через CRYPTO_OUTCOMES_DBS env var).
        if isinstance(outcomes_db, list):
            self._outcomes_dbs = [Path(p) for p in outcomes_db]
        else:
            self._outcomes_dbs = [Path(outcomes_db)]
        # Backwards-compat поле для legacy кода (не используется внутри,
        # но тесты иногда читают).
        self._outcomes_db = self._outcomes_dbs[0]
        self._halt_flag_file = Path(halt_flag_file) if halt_flag_file else None
        self._heartbeat_file = Path(heartbeat_file) if heartbeat_file else None
        self._start_ts = runner_start_ts or time.time()

    # ── Health ──────────────────────────────────────────────────────────────

    def health(self, *, heartbeat_max_age_s: float = 120.0) -> HealthInfo:
        halt_active = False
        halt_reason: dict[str, str] | None = None
        if self._halt_flag_file is not None and self._halt_flag_file.exists():
            halt_active = True
            try:
                halt_reason = _parse_halt_file(self._halt_flag_file)
            except Exception:
                logger.debug("could not parse halt file %s", self._halt_flag_file)

        hb_age: float | None = None
        if self._heartbeat_file is not None and self._heartbeat_file.exists():
            hb_age = time.time() - self._heartbeat_file.stat().st_mtime

        status: str
        if halt_active:
            status = "halted"
        elif hb_age is not None and hb_age > heartbeat_max_age_s:
            status = "stale"
        else:
            status = "ok"

        return HealthInfo(
            status=status,
            uptime_s=time.time() - self._start_ts,
            runner_heartbeat_age_s=hb_age,
            halt_active=halt_active,
            halt_reason=halt_reason,
        )

    # ── Trades ──────────────────────────────────────────────────────────────

    def trades(
        self,
        *,
        only_open: bool = False,
        only_closed: bool = False,
        symbol: str | None = None,
        limit: int = 50,
    ) -> list[TradeSummary]:
        if only_open and only_closed:
            raise ValueError("only_open and only_closed are mutually exclusive")
        outcomes = self._all_outcomes_desc()
        result: list[TradeSummary] = []
        for o in outcomes:
            if only_open and o.is_closed:
                continue
            if only_closed and not o.is_closed:
                continue
            if symbol is not None and o.symbol != symbol:
                continue
            result.append(_trade_summary(o))
            if len(result) >= limit:
                break
        return result

    def symbols(self) -> list[str]:
        """Уникальные symbol'ы из всех outcomes (для UI filter dropdown)."""
        seen: set[str] = set()
        for o in self._all_outcomes_desc():
            seen.add(o.symbol)
        return sorted(seen)

    def trade_detail(self, trade_id: str) -> dict[str, Any] | None:
        # Multi-DB: пробуем каждую базу, возвращаем первую найденную.
        for db in self._outcomes_dbs:
            if not db.exists():
                continue
            log = TradeOutcomeLogger(db)
            outcome = log.get_by_id(trade_id)
            if outcome is not None:
                return _serialize_outcome_full(outcome)
        return None

    def strategy_stats(self) -> list[dict[str, Any]]:
        """Per-strategy агрегация: win_rate, profit_factor, total_pnl_usd.

        Strategy выводится из symbol через SYMBOL_TO_STRATEGY (1:1 в
        текущей конфигурации). Если symbol не в mapping → "unknown".

        Используется в дашборде для «как каждая стратегия работает».
        """
        by_strategy: dict[str, list[TradeOutcome]] = {}
        for o in self._all_outcomes_desc():
            strat = SYMBOL_TO_STRATEGY.get(o.symbol, "unknown")
            by_strategy.setdefault(strat, []).append(o)

        result: list[dict[str, Any]] = []
        for strat, outcomes in sorted(by_strategy.items()):
            closed = [o for o in outcomes if o.is_closed and o.pnl_usd is not None]
            wins = [o for o in closed if o.is_win]
            losses = [o for o in closed if o.is_loss]
            total_pnl: Decimal = sum(
                (o.pnl_usd for o in closed if o.pnl_usd is not None),
                start=Decimal("0"),
            )
            sum_wins: Decimal = sum(
                (o.pnl_usd for o in wins if o.pnl_usd is not None),
                start=Decimal("0"),
            )
            sum_losses_abs: Decimal = sum(
                (abs(o.pnl_usd) for o in losses if o.pnl_usd is not None),
                start=Decimal("0"),
            )
            profit_factor: str | None
            if sum_losses_abs > 0:
                profit_factor = format(sum_wins / sum_losses_abs, ".2f")
            elif sum_wins > 0:
                profit_factor = "inf"
            else:
                profit_factor = None
            result.append(
                {
                    "strategy": strat,
                    "symbol": outcomes[0].symbol if outcomes else None,
                    "total": len(outcomes),
                    "open": sum(1 for o in outcomes if not o.is_closed),
                    "closed": len(closed),
                    "wins": len(wins),
                    "losses": len(losses),
                    "win_rate_pct": (round(100.0 * len(wins) / len(closed), 1) if closed else 0.0),
                    "profit_factor": profit_factor,
                    "total_pnl_usd": str(total_pnl),
                }
            )
        return result

    def equity_curve(self, *, limit: int = 100) -> list[dict[str, Any]]:
        """Equity точки из закрытых сделок (running PnL cumulative).

        Простая реализация: накопленный pnl_usd от каждой closed trade.
        Для true equity curve нужны snapshots equity между сделками —
        отдельный PR.
        """
        outcomes = self._all_outcomes_desc()
        closed = [o for o in outcomes if o.is_closed and o.pnl_usd is not None]
        closed.sort(key=lambda o: o.exit_time_ms or 0)
        cumulative = Decimal("0")
        points: list[dict[str, Any]] = []
        for o in closed[-limit:]:
            assert o.pnl_usd is not None
            cumulative += o.pnl_usd
            points.append(
                {
                    "timestamp_ms": o.exit_time_ms,
                    "cumulative_pnl_usd": str(cumulative),
                    "pnl_usd": str(o.pnl_usd),
                    "trade_id": o.trade_id,
                }
            )
        return points

    def agent_confidence_history(self, agent_name: str, *, limit: int = 30) -> list[dict[str, Any]]:
        """История последних confidence/score значений одного агента.

        Используется для sparkline в UI: видеть как менялась уверенность
        агента в последних сделках.

        Возвращает list[{trade_id, timestamp_ms, value}] DESC by time.
        """
        outcomes = self._all_outcomes_desc()
        result: list[dict[str, Any]] = []
        for o in outcomes:
            payload = _agent_payload_for(o, agent_name)
            if not payload:
                continue
            value = _extract_confidence(payload, agent_name)
            if value is None:
                continue
            result.append(
                {
                    "trade_id": o.trade_id,
                    "timestamp_ms": o.entry_time_ms,
                    "value": value,
                }
            )
            if len(result) >= limit:
                break
        return result

    # ── Agents ──────────────────────────────────────────────────────────────

    def agent_snapshots(self) -> list[AgentSnapshot]:
        """Последний decision каждого из 5 субагентов.

        Идём по closed/open trades DESC, берём первый который у этого
        агента не пустой payload.
        """
        agent_keys = (
            "market_analyst",
            "sentiment_analyst",
            "risk_overseer",
            "macro_analyst",
            "coordinator",
        )
        found: dict[str, AgentSnapshot] = {}
        for o in self._all_outcomes_desc():
            for key in agent_keys:
                if key in found:
                    continue
                payload = _agent_payload_for(o, key)
                if not payload:
                    continue
                found[key] = AgentSnapshot(
                    name=key,
                    last_payload=payload,
                    last_trade_id=o.trade_id,
                    last_decision_at_ms=o.entry_time_ms,
                )
            if len(found) == len(agent_keys):
                break
        # Возвращаем в стабильном порядке, недостающие — пустые payloads
        result: list[AgentSnapshot] = []
        for key in agent_keys:
            snap = found.get(key)
            if snap is None:
                result.append(
                    AgentSnapshot(
                        name=key,
                        last_payload={},
                        last_trade_id="",
                        last_decision_at_ms=0,
                    )
                )
            else:
                result.append(snap)
        return result

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _open_logger(self) -> TradeOutcomeLogger:
        # Backwards-compat: legacy single-DB code path.
        # Connection per-call → стандартный паттерн TradeOutcomeLogger.
        return TradeOutcomeLogger(self._outcomes_dbs[0])

    def _all_outcomes_desc(self) -> list[TradeOutcome]:
        """Merge outcomes из всех баз, отсортированно по entry_time DESC."""
        outcomes: list[TradeOutcome] = []
        for db in self._outcomes_dbs:
            if not db.exists():
                continue
            log = TradeOutcomeLogger(db)
            outcomes.extend(log.iter_all())
        return sorted(outcomes, key=lambda o: o.entry_time_ms, reverse=True)


# ── Module helpers ──────────────────────────────────────────────────────────


# Маппинг symbol → strategy. 1:1 в текущей конфигурации. При добавлении
# новой стратегии — допиши сюда, иначе попадёт в "unknown" в API.
SYMBOL_TO_STRATEGY: dict[str, str] = {
    "BTC-USDT": "btc_breakout",
    "XAUT-USDT": "gold_safety_haven",
    "NCCO1OILWTI2USD-USDT": "oil_eia_avoid",
    "NCCO7241OILWTI2USD-USDT": "oil_eia_avoid",
    "NCSKTSLA2USD-USDT": "stock_earnings_avoid",
    "NCSKNVDA2USD-USDT": "stock_earnings_avoid",
    # Legacy aliases
    "XAU-USDT": "gold_safety_haven",
    "CL-USDT": "oil_eia_avoid",
    "TSLA-USDT": "stock_earnings_avoid",
    "NVDA-USDT": "stock_earnings_avoid",
}


def _trade_summary(o: TradeOutcome) -> TradeSummary:
    return TradeSummary(
        trade_id=o.trade_id,
        symbol=o.symbol,
        side=o.side,
        entry_time_ms=o.entry_time_ms,
        entry_price=str(o.entry_price),
        exit_time_ms=o.exit_time_ms,
        exit_price=str(o.exit_price) if o.exit_price is not None else None,
        pnl_pct=str(o.pnl_pct) if o.pnl_pct is not None else None,
        exit_reason=o.exit_reason,
        holding_time_min=o.holding_time_min,
        is_closed=o.is_closed,
        is_win=o.is_win,
        is_loss=o.is_loss,
    )


def _serialize_outcome_full(o: TradeOutcome) -> dict[str, Any]:
    import json

    def _maybe_json(raw: str) -> Any:
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return raw

    return {
        "trade_id": o.trade_id,
        "symbol": o.symbol,
        "side": o.side,
        "entry_time_ms": o.entry_time_ms,
        "entry_price": str(o.entry_price),
        "size": str(o.size),
        "exit_time_ms": o.exit_time_ms,
        "exit_price": str(o.exit_price) if o.exit_price is not None else None,
        "pnl_usd": str(o.pnl_usd) if o.pnl_usd is not None else None,
        "pnl_pct": str(o.pnl_pct) if o.pnl_pct is not None else None,
        "exit_reason": o.exit_reason,
        "holding_time_min": o.holding_time_min,
        "latency_decision_ms": o.latency_decision_ms,
        "latency_execution_ms": o.latency_execution_ms,
        "slippage_bps": str(o.slippage_bps) if o.slippage_bps is not None else None,
        "is_closed": o.is_closed,
        "is_win": o.is_win,
        "is_loss": o.is_loss,
        # LLM payloads — десериализованные dict
        "signal_candidate": _maybe_json(o.signal_candidate_json),
        "market_analyst": _maybe_json(o.market_analyst_json),
        "sentiment_analyst": _maybe_json(o.sentiment_analyst_json),
        "risk_overseer": _maybe_json(o.risk_overseer_json),
        "macro_analyst": _maybe_json(o.macro_analyst_json),
        "coordinator": _maybe_json(o.coordinator_json),
    }


def _extract_confidence(payload: dict[str, Any], agent_name: str) -> float | None:
    """Извлекаем единое 0..1 значение для sparkline из агент-payload.

    Coordinator: composite_confidence
    Sentiment: sentiment_score normalized к [0,1] (был [-1, 1])
    Все остальные: confidence (если есть)

    None если payload пустой или поле отсутствует.
    """
    if not payload:
        return None
    if agent_name == "coordinator":
        v = payload.get("composite_confidence")
    elif agent_name == "sentiment_analyst":
        s = payload.get("sentiment_score")
        if isinstance(s, int | float):
            # Map [-1, 1] → [0, 1]
            return max(0.0, min(1.0, (float(s) + 1.0) / 2.0))
        return None
    else:
        v = payload.get("confidence")
    if isinstance(v, int | float):
        return max(0.0, min(1.0, float(v)))
    return None


def _agent_payload_for(o: TradeOutcome, agent_key: str) -> dict[str, Any]:
    import json

    json_field = {
        "market_analyst": o.market_analyst_json,
        "sentiment_analyst": o.sentiment_analyst_json,
        "risk_overseer": o.risk_overseer_json,
        "macro_analyst": o.macro_analyst_json,
        "coordinator": o.coordinator_json,
    }.get(agent_key, "{}")
    try:
        parsed = json.loads(json_field)
    except (json.JSONDecodeError, ValueError):
        return {}
    if not isinstance(parsed, dict):
        return {}
    return parsed


def _parse_halt_file(path: Path) -> dict[str, str]:
    """Парсим metadata из halt-файла (формат HaltFlag.set)."""
    text = path.read_text(encoding="utf-8")
    fields: dict[str, str] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields


def _summary_to_dict(s: TradeSummary) -> dict[str, Any]:
    return {
        "trade_id": s.trade_id,
        "symbol": s.symbol,
        "side": s.side,
        "entry_time_ms": s.entry_time_ms,
        "entry_price": s.entry_price,
        "exit_time_ms": s.exit_time_ms,
        "exit_price": s.exit_price,
        "pnl_pct": s.pnl_pct,
        "exit_reason": s.exit_reason,
        "holding_time_min": s.holding_time_min,
        "is_closed": s.is_closed,
        "is_win": s.is_win,
        "is_loss": s.is_loss,
    }


def _agent_to_dict(a: AgentSnapshot) -> dict[str, Any]:
    return {
        "name": a.name,
        "last_payload": a.last_payload,
        "last_trade_id": a.last_trade_id,
        "last_decision_at_ms": a.last_decision_at_ms,
    }


def summaries_to_dicts(items: Iterable[TradeSummary]) -> list[dict[str, Any]]:
    return [_summary_to_dict(s) for s in items]


def agents_to_dicts(items: Iterable[AgentSnapshot]) -> list[dict[str, Any]]:
    return [_agent_to_dict(a) for a in items]


def health_to_dict(h: HealthInfo) -> dict[str, Any]:
    return {
        "status": h.status,
        "uptime_s": h.uptime_s,
        "runner_heartbeat_age_s": h.runner_heartbeat_age_s,
        "halt_active": h.halt_active,
        "halt_reason": h.halt_reason,
    }

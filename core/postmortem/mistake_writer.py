"""Markdown-генератор пост-мортем документов (plan #18 §6.2).

Принимает ``TradeOutcome`` + classification (от ``MistakeClassifierAgent``)
и пишет в файл ``journal/mistakes/<date>-<category>-<short-id>.md``.

Чистая функция формирования + atomic write через tempfile rename.
Без сетевых вызовов, без LLM — только composition.
"""

from __future__ import annotations

import contextlib
import logging
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.postmortem.models import TradeOutcome

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MistakeClassification:
    """Output ``MistakeClassifierAgent`` в типизированной форме.

    Дублирует JSON-payload агента, но как dataclass для type-safety
    в caller-коде.
    """

    primary_category: str
    secondary_categories: tuple[str, ...]
    what_went_wrong: str
    what_we_should_have_seen: str
    confidence_in_diagnosis: float

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> MistakeClassification:
        return cls(
            primary_category=str(payload["primary_category"]),
            secondary_categories=tuple(str(c) for c in payload.get("secondary_categories", [])),
            what_went_wrong=str(payload["what_went_wrong"]),
            what_we_should_have_seen=str(payload["what_we_should_have_seen"]),
            confidence_in_diagnosis=float(payload["confidence_in_diagnosis"]),
        )


def build_mistake_markdown(
    outcome: TradeOutcome,
    classification: MistakeClassification,
) -> str:
    """Сформировать markdown-документ.

    Формат соответствует шаблону plan #18 §6.2.
    """
    if not outcome.is_closed:
        raise ValueError(f"build_mistake_markdown: outcome {outcome.trade_id} ещё открыт")

    # exit_time_ms гарантированно не None (is_closed)
    assert outcome.exit_time_ms is not None
    exit_dt = datetime.fromtimestamp(outcome.exit_time_ms / 1000, tz=UTC)
    date_str = exit_dt.strftime("%Y-%m-%d %H:%M UTC")

    secondary_str = (
        " + " + ", ".join(classification.secondary_categories)
        if classification.secondary_categories
        else ""
    )
    pnl_pct_str = str(outcome.pnl_pct) if outcome.pnl_pct is not None else "?"
    pnl_usd_str = str(outcome.pnl_usd) if outcome.pnl_usd is not None else "?"

    lines = [
        f"# Mistake: {classification.primary_category}",
        "",
        f"**Date:** {date_str}",
        f"**Trade ID:** {outcome.trade_id}",
        f"**Symbol:** {outcome.symbol} ({outcome.side})",
        f"**Entry / Exit:** {outcome.entry_price} → {outcome.exit_price}",
        f"**PnL:** {pnl_usd_str} USD ({pnl_pct_str}%)",
        f"**Exit reason:** {outcome.exit_reason}",
        f"**Holding time:** {outcome.holding_time_min} min",
        f"**Category:** {classification.primary_category}{secondary_str}",
        f"**Diagnosis confidence:** {classification.confidence_in_diagnosis:.2f}",
        "",
        "## Что произошло",
        "",
        classification.what_went_wrong,
        "",
        "## Что упустили",
        "",
        classification.what_we_should_have_seen,
        "",
        "## Контекст решения (LLM payloads)",
        "",
        "<details><summary>Signal candidate</summary>",
        "",
        "```json",
        outcome.signal_candidate_json,
        "```",
        "",
        "</details>",
        "",
        "<details><summary>Market analyst</summary>",
        "",
        "```json",
        outcome.market_analyst_json,
        "```",
        "",
        "</details>",
        "",
        "<details><summary>Sentiment analyst</summary>",
        "",
        "```json",
        outcome.sentiment_analyst_json,
        "```",
        "",
        "</details>",
        "",
        "<details><summary>Risk overseer</summary>",
        "",
        "```json",
        outcome.risk_overseer_json,
        "```",
        "",
        "</details>",
        "",
        "<details><summary>Macro analyst</summary>",
        "",
        "```json",
        outcome.macro_analyst_json,
        "```",
        "",
        "</details>",
        "",
        "<details><summary>Coordinator</summary>",
        "",
        "```json",
        outcome.coordinator_json,
        "```",
        "",
        "</details>",
        "",
    ]
    return "\n".join(lines)


def mistake_filename(
    outcome: TradeOutcome,
    classification: MistakeClassification,
) -> str:
    """Имя файла: ``<date>-<category>-<short-id>.md``.

    Безопасно для filesystem (без spaces, без spec-символов).
    """
    if not outcome.is_closed:
        raise ValueError(f"mistake_filename: outcome {outcome.trade_id} ещё открыт")
    assert outcome.exit_time_ms is not None
    exit_dt = datetime.fromtimestamp(outcome.exit_time_ms / 1000, tz=UTC)
    date = exit_dt.strftime("%Y-%m-%d")
    short_id = outcome.trade_id[:8]
    return f"{date}-{classification.primary_category}-{short_id}.md"


def write_mistake_document(
    outcome: TradeOutcome,
    classification: MistakeClassification,
    output_dir: Path,
) -> Path:
    """Atomic write markdown файла в ``output_dir/<filename>``.

    Создаёт output_dir если её нет. Возвращает путь к файлу.

    Atomic: пишет в temp-файл рядом, fsync, затем rename — никаких
    half-written файлов даже при crash.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    content = build_mistake_markdown(outcome, classification)
    target = output_dir / mistake_filename(outcome, classification)

    # Atomic write через temp file + rename
    fd, tmp_path = tempfile.mkstemp(
        prefix=".tmp_mistake_",
        suffix=".md",
        dir=str(output_dir),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, target)
    except Exception:
        # Удаляем temp если переименование не удалось
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise

    logger.info("mistake document written: %s", target)
    return target

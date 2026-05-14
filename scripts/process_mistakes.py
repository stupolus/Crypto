"""Offline процессор убыточных сделок: TradeOutcomeLogger → markdown mistakes.

Читает loss-сделки из SQLite outcomes journal, прогоняет каждую через
MistakeClassifierAgent (Anthropic Sonnet 4.6), записывает markdown
документ в журнал/mistakes/.

Запуск (рекомендуется на cron'е daily):
    .venv/bin/python -m scripts.process_mistakes
    .venv/bin/python -m scripts.process_mistakes --limit 5 --out-dir custom/

Стоимость: ~$0.05 / loss × ~10 lossов в день = $0.5/день ≈ $15/месяц.

Не запускается в hot path runner'а — LLM-вызовы latency-чувствительные,
а пост-мортем не критично-срочный.

Игнорирует сделки которые уже обработаны: skip если соответствующий
markdown файл уже существует.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from core.agents.base import AgentRequest
from core.agents.settings import AnthropicSettings
from core.postmortem.logger import TradeOutcomeLogger
from core.postmortem.mistake_classifier import (
    MistakeClassifierAgent,
    trade_outcome_to_context,
)
from core.postmortem.mistake_writer import (
    MistakeClassification,
    write_mistake_document,
)
from core.postmortem.models import TradeOutcome

logger = logging.getLogger(__name__)


class ProcessResult:
    """Тонкая обёртка вокруг результата process_one — для подсчёта."""

    __slots__ = ("status",)

    def __init__(self, status: str) -> None:
        # "written" | "skipped" | "failed" | "not_loss"
        self.status = status


async def process_one(
    outcome: TradeOutcome,
    classifier: MistakeClassifierAgent,
    output_dir: Path,
    *,
    overwrite: bool = False,
) -> ProcessResult:
    """Обработать одну loss-сделку → markdown.

    Статусы:
    - "not_loss": skip, outcome не закрыт или не убыточен
    - "skipped": уже есть markdown для этого trade_id
    - "written": новый markdown создан
    - "failed": LLM вызов или write упали
    """
    if not outcome.is_closed or not outcome.is_loss:
        logger.debug("process_mistakes: skip %s (не closed loss)", outcome.trade_id)
        return ProcessResult("not_loss")

    existing = list(output_dir.glob(f"*-{outcome.trade_id[:8]}.md"))
    if existing and not overwrite:
        logger.info(
            "process_mistakes: skip %s — уже существует %s",
            outcome.trade_id,
            existing[0].name,
        )
        return ProcessResult("skipped")

    context = trade_outcome_to_context(outcome)
    try:
        response = await classifier.run(AgentRequest(context=context))
    except Exception as e:
        logger.exception("classifier failed для %s: %s", outcome.trade_id, e)
        return ProcessResult("failed")

    try:
        classification = MistakeClassification.from_payload(response.payload)
        path = write_mistake_document(outcome, classification, output_dir)
    except Exception:
        logger.exception("write_mistake_document failed для %s", outcome.trade_id)
        return ProcessResult("failed")

    logger.info(
        "process_mistakes: written %s | category=%s | confidence=%.2f",
        path.name,
        classification.primary_category,
        classification.confidence_in_diagnosis,
    )
    return ProcessResult("written")


async def run(
    db_path: Path,
    output_dir: Path,
    *,
    limit: int = 50,
    overwrite: bool = False,
) -> int:
    """Точка входа CLI. Возвращает exit code."""
    if not db_path.exists():
        print(
            f"DB не существует: {db_path}\n"
            "Запусти сначала llm_runner с --outcomes-db чтобы накопить outcomes.",
            file=sys.stderr,
        )
        return 1

    settings = AnthropicSettings()
    if not settings.configured:
        print(
            "ANTHROPIC_API_KEY не задан в .env — нельзя запустить classifier",
            file=sys.stderr,
        )
        return 1
    assert settings.api_key is not None  # для mypy

    output_dir.mkdir(parents=True, exist_ok=True)

    log = TradeOutcomeLogger(db_path)
    losses = log.recent_losses(limit=limit)
    if not losses:
        print("Нет убыточных closed сделок в журнале — нечего обрабатывать.")
        return 0

    print(f"Обрабатываем {len(losses)} loss-сделок (limit={limit})...")
    classifier = MistakeClassifierAgent(api_key=settings.api_key)

    counts = {"written": 0, "skipped": 0, "failed": 0, "not_loss": 0}
    for outcome in losses:
        result = await process_one(
            outcome,
            classifier,
            output_dir,
            overwrite=overwrite,
        )
        counts[result.status] += 1

    print(
        f"\nГотово: written={counts['written']}, "
        f"skipped={counts['skipped']}, failed={counts['failed']}, "
        f"not_loss={counts['not_loss']}"
    )
    return 0 if counts["failed"] == 0 else 2


def main() -> None:
    parser = argparse.ArgumentParser(description="Обработка убыточных сделок → markdown mistakes")
    parser.add_argument(
        "--db",
        default="ops/llm-outcomes.sqlite",
        help="Путь к outcomes SQLite (default ops/llm-outcomes.sqlite)",
    )
    parser.add_argument(
        "--out-dir",
        default="журнал/mistakes",
        help="Куда писать markdown файлы (default журнал/mistakes)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Максимум loss-сделок за один запуск (default 50)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Переписать markdown даже если он уже существует",
    )
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    rc = asyncio.run(
        run(
            Path(args.db),
            Path(args.out_dir),
            limit=args.limit,
            overwrite=args.overwrite,
        )
    )
    sys.exit(rc)


if __name__ == "__main__":
    main()

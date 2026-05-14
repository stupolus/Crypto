"""HaltFlag — emergency circuit breaker file flag.

Когда файл ``/var/lib/crypto/halt`` существует — llm_runner отказывается
открывать новые позиции и шлёт Telegram alert. Существующие открытые
позиции продолжают жить (SL/TP биржи сработают как обычно).

Создать halt:
    sudo -u crypto touch /var/lib/crypto/halt
    # или через telegram: пользователь напишет команду, отдельный PR

Снять halt:
    sudo -u crypto rm /var/lib/crypto/halt

Использование в runner::

    if HaltFlag(path).is_set():
        logger.warning("HALT flag active — skipping signal")
        return

Также авто-халт срабатывает когда ``DrawdownGuard`` детектит >threshold%
просадки эквити — в этом случае файл создаётся автоматически с reason
metadata внутри.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HaltReason:
    """Метаданные о том кто и почему создал halt."""

    created_at_iso: str
    source: str  # "manual", "drawdown_guard", "max_consecutive_losses", "external"
    note: str  # human-readable explanation


class HaltFlag:
    """File-based emergency stop signal для runner'а.

    Hot path только читает (``is_set``) — это дешёвый ``os.path.exists``.
    Запись делается либо вручную (touch), либо drawdown guard'ом, либо
    Telegram-командой (отдельный PR).
    """

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def is_set(self) -> bool:
        """Hot path check — есть ли halt-флаг."""
        return self._path.exists()

    def set(self, reason: HaltReason) -> None:
        """Создать halt-флаг с metadata. Идемпотентно (overwrite)."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        content = (
            f"HALTED\n"
            f"created_at: {reason.created_at_iso}\n"
            f"source: {reason.source}\n"
            f"note: {reason.note}\n"
        )
        self._path.write_text(content, encoding="utf-8")
        logger.warning(
            "HaltFlag SET: source=%s note=%s path=%s",
            reason.source,
            reason.note,
            self._path,
        )

    def clear(self) -> bool:
        """Снять halt. Возвращает True если файл был."""
        if not self._path.exists():
            return False
        self._path.unlink()
        logger.info("HaltFlag CLEARED: path=%s", self._path)
        return True

    def read_reason(self) -> HaltReason | None:
        """Прочитать metadata если halt активен."""
        if not self._path.exists():
            return None
        text = self._path.read_text(encoding="utf-8")
        fields: dict[str, str] = {}
        for line in text.splitlines():
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip()
        return HaltReason(
            created_at_iso=fields.get("created_at", ""),
            source=fields.get("source", "unknown"),
            note=fields.get("note", ""),
        )


def make_manual_halt(note: str = "manually triggered") -> HaltReason:
    """Helper для ручного create_halt вызова из CLI."""
    return HaltReason(
        created_at_iso=datetime.now(UTC).isoformat(),
        source="manual",
        note=note,
    )


def make_drawdown_halt(drawdown_pct: float, threshold_pct: float) -> HaltReason:
    return HaltReason(
        created_at_iso=datetime.now(UTC).isoformat(),
        source="drawdown_guard",
        note=f"drawdown {drawdown_pct:.2f}% > threshold {threshold_pct:.2f}%",
    )


def make_consecutive_losses_halt(count: int, threshold: int) -> HaltReason:
    return HaltReason(
        created_at_iso=datetime.now(UTC).isoformat(),
        source="max_consecutive_losses",
        note=f"{count} losses in a row > threshold {threshold}",
    )

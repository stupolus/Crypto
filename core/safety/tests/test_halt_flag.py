"""Unit-тесты ``HaltFlag``."""

from __future__ import annotations

from pathlib import Path

from core.safety.halt_flag import (
    HaltFlag,
    HaltReason,
    make_consecutive_losses_halt,
    make_drawdown_halt,
    make_manual_halt,
)


def test_is_set_false_when_no_file(tmp_path: Path) -> None:
    flag = HaltFlag(tmp_path / "halt")
    assert not flag.is_set()


def test_is_set_true_when_file_exists(tmp_path: Path) -> None:
    flag = HaltFlag(tmp_path / "halt")
    flag.set(make_manual_halt("test"))
    assert flag.is_set()


def test_set_creates_parent_dir(tmp_path: Path) -> None:
    deep = tmp_path / "deep" / "nested" / "halt"
    flag = HaltFlag(deep)
    flag.set(make_manual_halt("nested"))
    assert deep.exists()


def test_set_writes_metadata(tmp_path: Path) -> None:
    flag = HaltFlag(tmp_path / "halt")
    flag.set(
        HaltReason(
            created_at_iso="2026-05-14T22:00:00+00:00",
            source="manual",
            note="user пожелал stop",
        )
    )
    content = (tmp_path / "halt").read_text(encoding="utf-8")
    assert "HALTED" in content
    assert "source: manual" in content
    assert "user пожелал stop" in content


def test_clear_removes_file(tmp_path: Path) -> None:
    flag = HaltFlag(tmp_path / "halt")
    flag.set(make_manual_halt("x"))
    assert flag.is_set()
    removed = flag.clear()
    assert removed is True
    assert not flag.is_set()


def test_clear_no_file_returns_false(tmp_path: Path) -> None:
    flag = HaltFlag(tmp_path / "halt")
    assert flag.clear() is False


def test_read_reason_when_clear(tmp_path: Path) -> None:
    flag = HaltFlag(tmp_path / "halt")
    assert flag.read_reason() is None


def test_read_reason_returns_metadata(tmp_path: Path) -> None:
    flag = HaltFlag(tmp_path / "halt")
    original = HaltReason(
        created_at_iso="2026-05-14T22:00:00+00:00",
        source="drawdown_guard",
        note="drawdown 12.5% > threshold 10.0%",
    )
    flag.set(original)
    read = flag.read_reason()
    assert read is not None
    assert read.source == "drawdown_guard"
    assert read.note == "drawdown 12.5% > threshold 10.0%"
    assert read.created_at_iso == "2026-05-14T22:00:00+00:00"


def test_set_overwrites_existing(tmp_path: Path) -> None:
    """Повторный set заменяет старый reason."""
    flag = HaltFlag(tmp_path / "halt")
    flag.set(make_manual_halt("first"))
    flag.set(make_manual_halt("second"))
    read = flag.read_reason()
    assert read is not None
    assert read.note == "second"


def test_make_manual_halt_has_iso_timestamp() -> None:
    reason = make_manual_halt("test")
    assert reason.source == "manual"
    assert reason.note == "test"
    # ISO format starts with 4-digit year and has T separator
    assert "T" in reason.created_at_iso


def test_make_drawdown_halt() -> None:
    reason = make_drawdown_halt(drawdown_pct=12.34, threshold_pct=10.0)
    assert reason.source == "drawdown_guard"
    assert "12.34" in reason.note
    assert "10.00" in reason.note


def test_make_consecutive_losses_halt() -> None:
    reason = make_consecutive_losses_halt(count=6, threshold=5)
    assert reason.source == "max_consecutive_losses"
    assert "6" in reason.note
    assert "5" in reason.note


def test_path_property_returns_path(tmp_path: Path) -> None:
    p = tmp_path / "halt"
    flag = HaltFlag(p)
    assert flag.path == p


def test_string_path_constructor(tmp_path: Path) -> None:
    """HaltFlag accepts str path как и Path."""
    flag = HaltFlag(str(tmp_path / "halt"))
    assert not flag.is_set()
    flag.set(make_manual_halt("x"))
    assert flag.is_set()

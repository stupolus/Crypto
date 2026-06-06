"""Unit-тесты ``scripts.pdf_to_md`` (markitdown мокается фейком)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from scripts.pdf_to_md import (
    convert_pdf,
    iter_inbox_pdfs,
    run,
)


class _FakeResult:
    def __init__(self, text: str) -> None:
        self.text_content = text


class _FakeConverter:
    """Имитация markitdown: помнит, что конвертировал, отдаёт фиксированный текст."""

    def __init__(self, text: str = "# Заголовок\n\nтекст") -> None:
        self.text = text
        self.calls: list[str] = []

    def convert(self, source: str) -> _FakeResult:
        self.calls.append(source)
        return _FakeResult(self.text)


def _make_pdf(path: Path) -> Path:
    path.write_bytes(b"%PDF-1.4 fake")
    return path


def test_convert_pdf_returns_markdown(tmp_path: Path) -> None:
    pdf = _make_pdf(tmp_path / "книга.pdf")
    conv = _FakeConverter("# Книга\n\nсуть")
    text = convert_pdf(pdf, converter=conv)
    assert text == "# Книга\n\nсуть"
    assert conv.calls == [str(pdf)]


def test_convert_pdf_rejects_non_pdf(tmp_path: Path) -> None:
    txt = tmp_path / "заметка.txt"
    txt.write_text("hi", encoding="utf-8")
    with pytest.raises(ValueError, match="ожидался .pdf"):
        convert_pdf(txt, converter=_FakeConverter())


def test_convert_pdf_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        convert_pdf(tmp_path / "нет.pdf", converter=_FakeConverter())


def test_convert_pdf_empty_text_content(tmp_path: Path) -> None:
    pdf = _make_pdf(tmp_path / "scan.pdf")

    class _NoText:
        def convert(self, source: str) -> Any:
            return object()  # без text_content

    assert convert_pdf(pdf, converter=_NoText()) == ""


def test_iter_inbox_pdfs_sorted(tmp_path: Path) -> None:
    _make_pdf(tmp_path / "b.pdf")
    _make_pdf(tmp_path / "a.pdf")
    (tmp_path / "ignore.txt").write_text("x", encoding="utf-8")
    pdfs = iter_inbox_pdfs(tmp_path)
    assert [p.name for p in pdfs] == ["a.pdf", "b.pdf"]


def test_iter_inbox_pdfs_missing_dir(tmp_path: Path) -> None:
    assert iter_inbox_pdfs(tmp_path / "нет") == []


def test_run_single_file_to_stdout(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    pdf = _make_pdf(tmp_path / "doc.pdf")
    rc = run([pdf], converter=_FakeConverter("ПЕЧАТЬ"))
    assert rc == 0
    assert "ПЕЧАТЬ" in capsys.readouterr().out


def test_run_single_file_with_out(tmp_path: Path) -> None:
    pdf = _make_pdf(tmp_path / "doc.pdf")
    out = tmp_path / "doc.md"
    rc = run([pdf], out=out, converter=_FakeConverter("СОДЕРЖИМОЕ"))
    assert rc == 0
    assert out.read_text(encoding="utf-8") == "СОДЕРЖИМОЕ"


def test_run_inbox_writes_sibling_md(tmp_path: Path) -> None:
    _make_pdf(tmp_path / "a.pdf")
    _make_pdf(tmp_path / "b.pdf")
    rc = run([], to_inbox=True, inbox_dir=tmp_path, converter=_FakeConverter("X"))
    assert rc == 0
    assert (tmp_path / "a.md").read_text(encoding="utf-8") == "X"
    assert (tmp_path / "b.md").read_text(encoding="utf-8") == "X"


def test_run_inbox_empty(tmp_path: Path) -> None:
    assert run([], to_inbox=True, inbox_dir=tmp_path, converter=_FakeConverter()) == 1


def test_run_no_targets(tmp_path: Path) -> None:
    assert run([], converter=_FakeConverter()) == 1


def test_run_out_with_multiple_files_rejected(tmp_path: Path) -> None:
    p1 = _make_pdf(tmp_path / "a.pdf")
    p2 = _make_pdf(tmp_path / "b.pdf")
    rc = run([p1, p2], out=tmp_path / "x.md", converter=_FakeConverter())
    assert rc == 1


def test_run_reports_error_per_file(tmp_path: Path) -> None:
    good = _make_pdf(tmp_path / "ok.pdf")
    bad = tmp_path / "missing.pdf"  # не существует
    rc = run([good, bad], converter=_FakeConverter("OK"))
    assert rc == 1
    # хороший файл всё равно обработан (вывод рядом, т.к. >1 цель)
    assert (tmp_path / "ok.md").read_text(encoding="utf-8") == "OK"

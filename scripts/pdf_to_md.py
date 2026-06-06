"""Единый ридер PDF: PDF → Markdown через markitdown.

В проекте все PDF (книги, отчёты, статьи из ``бизнес/inbox/pdf/``) читаются
**через markitdown** (Microsoft), а не «как есть». Markdown-выход сохраняет
заголовки/списки/таблицы и не зависит от случайной разбивки строк в PDF —
это даёт стабильный текст для выжимок в ``бизнес/материалы/обработанное/``.

См. план ``plans/53-markitdown-pdf-integration-2026-06-06.md`` и инструкцию
``бизнес/как-добавлять-материалы.md``.

Установка зависимости (optional-группа ``materials``):
    .venv/bin/pip install -e ".[materials]"

Запуск:
    # один файл → stdout
    .venv/bin/python -m scripts.pdf_to_md бизнес/inbox/pdf/книга.pdf

    # один файл → рядом .md (книга.md)
    .venv/bin/python -m scripts.pdf_to_md книга.pdf -o книга.md

    # вся папка inbox/pdf → .md рядом с каждым PDF
    .venv/bin/python -m scripts.pdf_to_md --inbox

Утилита ничего не запускает на бирже и ничего не коммитит — только конвертирует.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Protocol, cast

DEFAULT_INBOX = Path("бизнес/inbox/pdf")


class _Converter(Protocol):
    """Минимальный интерфейс markitdown (для инъекции фейка в тестах)."""

    def convert(self, source: str) -> Any: ...


def _make_markitdown() -> _Converter:
    """Ленивый импорт markitdown. Изолирован — чтобы тесты могли мокать.

    markitdown — optional-зависимость (группа ``materials``); модуль должен
    импортироваться и без неё. Реальный запуск без зависимости → понятная
    ошибка с командой установки.
    """
    try:
        from markitdown import MarkItDown
    except ModuleNotFoundError as e:  # pragma: no cover - тривиальная ветка
        raise RuntimeError(
            "markitdown не установлен. Установи optional-группу materials:\n"
            '    pip install -e ".[materials]"'
        ) from e
    return cast(_Converter, MarkItDown())


def convert_pdf(path: Path, *, converter: _Converter | None = None) -> str:
    """Сконвертировать один PDF в Markdown-текст.

    ``converter`` инъектируется в тестах; по умолчанию — настоящий markitdown.
    """
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"ожидался .pdf, получено: {path.name}")
    if not path.is_file():
        raise FileNotFoundError(f"файл не найден: {path}")
    md = converter if converter is not None else _make_markitdown()
    result = md.convert(str(path))
    text = getattr(result, "text_content", None)
    return text if isinstance(text, str) else ""


def iter_inbox_pdfs(inbox_dir: Path = DEFAULT_INBOX) -> list[Path]:
    """Все ``*.pdf`` в папке inbox (без рекурсии), отсортированные по имени."""
    if not inbox_dir.is_dir():
        return []
    return sorted(p for p in inbox_dir.iterdir() if p.suffix.lower() == ".pdf" and p.is_file())


def _emit(path: Path, text: str, out: Path | None, sibling: bool) -> None:
    """Записать результат: явный ``out``, рядом (``sibling``), либо stdout."""
    if out is not None:
        out.write_text(text, encoding="utf-8")
    elif sibling:
        path.with_suffix(".md").write_text(text, encoding="utf-8")
    else:
        print(text)


def run(
    targets: list[Path],
    *,
    out: Path | None = None,
    to_inbox: bool = False,
    inbox_dir: Path = DEFAULT_INBOX,
    converter: _Converter | None = None,
) -> int:
    """Сконвертировать цели. Возвращает exit-code (0 — все ок, 1 — были ошибки)."""
    if to_inbox:
        targets = iter_inbox_pdfs(inbox_dir)
        if not targets:
            print(f"нет PDF в {inbox_dir}", file=sys.stderr)
            return 1

    if not targets:
        print("нечего конвертировать: укажи PDF-файл(ы) или --inbox", file=sys.stderr)
        return 1

    # --out имеет смысл только для одного файла.
    if out is not None and len(targets) > 1:
        print("--out нельзя с несколькими файлами; используй вывод рядом (.md)", file=sys.stderr)
        return 1

    # Запись рядом (.md): автоматически для batch/inbox, либо когда явный out не задан
    # и цель не одиночная-в-stdout. Для одиночного файла без --out — печать в stdout.
    sibling = to_inbox or len(targets) > 1

    has_errors = False
    for path in targets:
        try:
            text = convert_pdf(path, converter=converter)
            _emit(path, text, out, sibling)
            if sibling or out is not None:
                dest = out if out is not None else path.with_suffix(".md")
                print(f"✓ {path}{dest}", file=sys.stderr)
        except (ValueError, FileNotFoundError, RuntimeError) as e:
            print(f"✗ {path} — {type(e).__name__}: {e}", file=sys.stderr)
            has_errors = True
    return 1 if has_errors else 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="PDF → Markdown через markitdown (единый ридер PDF проекта)",
    )
    parser.add_argument(
        "files",
        nargs="*",
        type=Path,
        help="PDF-файл(ы) для конвертации",
    )
    parser.add_argument(
        "-o",
        "--out",
        type=Path,
        default=None,
        help="путь выходного .md (только для одного файла; иначе пишется рядом)",
    )
    parser.add_argument(
        "--inbox",
        action="store_true",
        help=f"обработать все PDF в {DEFAULT_INBOX} (вывод рядом с каждым)",
    )
    args = parser.parse_args()
    sys.exit(run(args.files, out=args.out, to_inbox=args.inbox))


if __name__ == "__main__":
    main()

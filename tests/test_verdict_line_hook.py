"""Тесты напоминания о первой строке файла вердикта после его записи."""

from pathlib import Path

from codeteam.core.roles.common import ACCEPTED_VERDICT, REWORK_VERDICT, VERDICT_FILE_NAME
from codeteam.core.roles.common.review import verdict_line_hook

# Файл вердикта в черновике ревьюера.
VERDICT_PATH = Path("draft") / VERDICT_FILE_NAME


def test_readable_verdict_gives_no_reminder() -> None:
    """
    Первая непустая строка с одним вердиктом, в том числе после пустых строк и под знаком заголовка, —
    напоминания нет.
    """
    for text in (f"{REWORK_VERDICT}\n\n## Причины", f"\n\n{ACCEPTED_VERDICT}", f"# {ACCEPTED_VERDICT}"):
        assert verdict_line_hook(VERDICT_PATH, text) is None


def test_unreadable_verdict_gives_reminder() -> None:
    """
    Заголовок вместо вердикта, вердикт не в первой строке и два вердикта в одной строке — напоминание есть.
    """
    texts = (
        f"# 000 Вердикт\n\n{REWORK_VERDICT}",
        f"Вердикт по этапу\n{ACCEPTED_VERDICT}",
        f"{ACCEPTED_VERDICT} или {REWORK_VERDICT}",
    )
    for text in texts:
        assert verdict_line_hook(VERDICT_PATH, text) is not None


def test_other_draft_file_gives_no_reminder() -> None:
    """
    Другие файлы черновика хук не проверяет.
    """
    assert verdict_line_hook(Path("draft") / "100_verdict.md", "# Вердикт") is None

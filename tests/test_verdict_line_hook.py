"""Тесты напоминания о первой строке файла вердикта после его записи."""

from pathlib import Path

from codeteam.core.agent.step_hooks import StepContext
from codeteam.core.roles.common import ACCEPTED_VERDICT, REWORK_VERDICT, VERDICT_FILE_NAME
from codeteam.core.roles.common.review import verdict_line_hook


def _reminder(*, private_dir: Path, file_name: str, text: str) -> str | None:
    """
    Записывает файл в черновик ревьюера и запускает хук на шаге, изменившем этот файл.

        private_dir: личная папка ревьюера.
        file_name: имя файла черновика.
        text: текст файла.

    Возвращает: Напоминание хука или None.
    """
    draft_file = private_dir / "draft" / file_name
    draft_file.parent.mkdir(parents = True, exist_ok = True)
    draft_file.write_text(text, encoding = "utf-8")

    return verdict_line_hook(StepContext(project_dir = private_dir, private_dir = private_dir, changed_files = (draft_file,)))


def test_readable_verdict_gives_no_reminder(tmp_path: Path) -> None:
    """
    Первая непустая строка с одним вердиктом, в том числе после пустых строк и под знаком заголовка, —
    напоминания нет.
    """
    for text in (f"{REWORK_VERDICT}\n\n## Причины", f"\n\n{ACCEPTED_VERDICT}", f"# {ACCEPTED_VERDICT}"):
        assert _reminder(private_dir = tmp_path, file_name = VERDICT_FILE_NAME, text = text) is None


def test_unreadable_verdict_gives_reminder(tmp_path: Path) -> None:
    """
    Заголовок вместо вердикта, вердикт не в первой строке и два вердикта в одной строке — напоминание есть.
    """
    texts = (
        f"# 000 Вердикт\n\n{REWORK_VERDICT}",
        f"Вердикт по этапу\n{ACCEPTED_VERDICT}",
        f"{ACCEPTED_VERDICT} или {REWORK_VERDICT}",
    )
    for text in texts:
        assert _reminder(private_dir = tmp_path, file_name = VERDICT_FILE_NAME, text = text) is not None


def test_other_draft_file_gives_no_reminder(tmp_path: Path) -> None:
    """
    Другие файлы черновика хук не проверяет.
    """
    assert _reminder(private_dir = tmp_path, file_name = "100_verdict.md", text = "# Вердикт") is None

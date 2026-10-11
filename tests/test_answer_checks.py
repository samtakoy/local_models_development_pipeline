"""Тесты проверок сдачи: обязательные файлы черновика, файл вердикта ревьюера, чистый проект."""

from pathlib import Path

import pytest

from codeteam.common.git import commit_all, init_repository
from codeteam.core.agent.answer_checks import required_files_check
from codeteam.core.roles.common import ACCEPTED_VERDICT, REWORK_VERDICT, VERDICT_FILE_NAME, check_verdict_file, \
    clean_project_check

# Обязательный файл черновика в тесте.
REQUIRED_FILE_NAME = "000_answer.md"


@pytest.fixture
def project_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """
    Папка проекта с коммитом: src/app.py.

    Возвращает: Путь папки проекта.
    """
    for name, value in {
        "GIT_AUTHOR_NAME": "test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
    }.items():
        monkeypatch.setenv(name, value)

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("def view():\n    return 1\n", encoding = "utf-8")
    init_repository(project_dir = tmp_path)
    commit_all(project_dir = tmp_path, message = "init")

    return tmp_path


def test_required_files_check(tmp_path: Path) -> None:
    """
    Нет обязательного файла — замечание с его именем; файл есть — замечания нет.
    """
    check = required_files_check(file_names = (REQUIRED_FILE_NAME,))

    remark = check(tmp_path)
    assert remark is not None
    assert REQUIRED_FILE_NAME in remark

    (tmp_path / REQUIRED_FILE_NAME).write_text("# Ответ\n", encoding = "utf-8")
    assert check(tmp_path) is None


def test_verdict_file_check(tmp_path: Path) -> None:
    """
    Нет файла вердикта или вердикт не читается — замечание; один вердикт в первой строке — замечания нет.
    """
    verdict_file = tmp_path / VERDICT_FILE_NAME
    assert check_verdict_file(tmp_path) is not None

    verdict_file.write_text(f"{ACCEPTED_VERDICT} или {REWORK_VERDICT}\n", encoding = "utf-8")
    assert check_verdict_file(tmp_path) is not None

    verdict_file.write_text(f"{ACCEPTED_VERDICT}\n\n## Причины\n", encoding = "utf-8")
    assert check_verdict_file(tmp_path) is None


def test_clean_project_check(project_dir: Path, tmp_path_factory: pytest.TempPathFactory) -> None:
    """
    Чистый проект — замечания нет; правка отслеживаемого файла — замечание с его путём.
    """
    draft_dir = tmp_path_factory.mktemp("draft")
    check = clean_project_check(project_dir = project_dir)
    assert check(draft_dir) is None

    (project_dir / "src" / "app.py").write_text("def view():\n    return 2\n", encoding = "utf-8")
    remark = check(draft_dir)
    assert remark is not None
    assert "src/app.py" in remark

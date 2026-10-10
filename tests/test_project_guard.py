"""Тесты охраны проекта после шага: изменённые отслеживаемые файлы возвращаются к коммиту."""

from pathlib import Path

import pytest

from codeteam.common.git import commit_all, init_repository, list_uncommitted_changes
from codeteam.core.roles.common import tracked_changes_check

# Текст замечания роли для теста.
REMARK = "Откатаны файлы: {paths}"

# Содержимое отслеживаемого файла в коммите.
COMMITTED_CONTENT = "def view():\n    return 1\n"


@pytest.fixture
def project_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """
    Папка проекта с коммитом: src/app.py и README.md.

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
    (tmp_path / "src" / "app.py").write_text(COMMITTED_CONTENT, encoding = "utf-8")
    (tmp_path / "README.md").write_text("# app\n", encoding = "utf-8")
    init_repository(project_dir = tmp_path)
    commit_all(project_dir = tmp_path, message = "init")

    return tmp_path


def test_clean_project_gives_no_remark(project_dir: Path) -> None:
    """
    Без правок проверка молчит.
    """
    check = tracked_changes_check(project_dir = project_dir, remark = REMARK)

    assert check() is None


def test_changed_files_are_restored(project_dir: Path) -> None:
    """
    Изменённый и удалённый отслеживаемые файлы возвращаются к коммиту, замечание называет оба.
    """
    check = tracked_changes_check(project_dir = project_dir, remark = REMARK)
    (project_dir / "src" / "app.py").write_text("def view():\n    return 2\n", encoding = "utf-8")
    (project_dir / "README.md").unlink()

    remark = check()

    assert remark is not None
    assert "src/app.py" in remark
    assert "README.md" in remark
    assert (project_dir / "src" / "app.py").read_text(encoding = "utf-8") == COMMITTED_CONTENT
    assert (project_dir / "README.md").is_file()
    assert list_uncommitted_changes(project_dir = project_dir) == []


def test_repeated_change_is_restored_again(project_dir: Path) -> None:
    """
    Повторная правка того же файла снова откатывается и снова попадает в замечание.
    """
    check = tracked_changes_check(project_dir = project_dir, remark = REMARK)
    app_file = project_dir / "src" / "app.py"
    app_file.write_text("first\n", encoding = "utf-8")
    check()

    app_file.write_text("second\n", encoding = "utf-8")
    remark = check()

    assert remark is not None
    assert "src/app.py" in remark
    assert app_file.read_text(encoding = "utf-8") == COMMITTED_CONTENT


def test_new_files_are_kept(project_dir: Path) -> None:
    """
    Новый файл, которого нет в коммите, проверка после шага не трогает.
    """
    check = tracked_changes_check(project_dir = project_dir, remark = REMARK)
    new_file = project_dir / "notes.txt"
    new_file.write_text("note\n", encoding = "utf-8")

    assert check() is None
    assert new_file.read_text(encoding = "utf-8") == "note\n"

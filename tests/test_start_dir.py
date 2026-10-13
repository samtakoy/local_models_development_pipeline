"""Тесты заполнения папки проекта из папки начального содержимого: папки проекта нет или она пустая —
содержимое копируется, иначе папка проекта не меняется."""

from pathlib import Path

import pytest

from codeteam.core.pipeline.project_setup import fill_from_start_dir


@pytest.fixture
def start_dir(tmp_path: Path) -> Path:
    """
    Папка начального содержимого с файлом и вложенной папкой.

        tmp_path: временная папка теста.

    Возвращает: Папку начального содержимого.
    """
    start = tmp_path / "start_folder"
    (start / "docs").mkdir(parents = True)
    (start / "AGENTS.md").write_text("правила", encoding = "utf-8")
    (start / "docs" / "spec.md").write_text("спецификация", encoding = "utf-8")

    return start


@pytest.mark.parametrize("project_exists", [False, True])
def test_missing_or_empty_project_filled(tmp_path: Path, start_dir: Path, project_exists: bool) -> None:
    """
    Папки проекта нет или она пустая — в неё копируется всё содержимое папки начального содержимого.
    """
    project_dir = tmp_path / "workspaces" / "demo"
    if project_exists:
        project_dir.mkdir(parents = True)

    fill_from_start_dir(project_dir = project_dir, start_dir = start_dir)

    assert (project_dir / "AGENTS.md").read_text(encoding = "utf-8") == "правила"
    assert (project_dir / "docs" / "spec.md").read_text(encoding = "utf-8") == "спецификация"


def test_filled_project_untouched(tmp_path: Path, start_dir: Path) -> None:
    """
    В папке проекта уже есть файлы — она не меняется.
    """
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    (project_dir / "main.py").write_text("код", encoding = "utf-8")

    fill_from_start_dir(project_dir = project_dir, start_dir = start_dir)

    assert sorted(path.name for path in project_dir.iterdir()) == ["main.py"]


def test_without_start_dir_nothing_created(tmp_path: Path) -> None:
    """
    Папки начального содержимого нет — папка проекта не создаётся.
    """
    project_dir = tmp_path / "demo"

    fill_from_start_dir(project_dir = project_dir, start_dir = tmp_path / "start_folder")

    assert not project_dir.exists()

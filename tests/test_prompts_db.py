"""Тесты базы промптов: какие файлы копируются, когда создаётся новая копия, что попадает в список прогона."""

import hashlib
import os
from datetime import datetime
from pathlib import Path

import pytest

from codeteam.app.prompts_db import PROMPTS_ROOT, RUN_PROMPTS_FILE_NAME, build_copy_name, find_prompt_files, \
    save_prompts

# Файлы промптов в папке промптов теста и их содержимое.
PROMPT_FILES = {
    "agent/prompts.py": "AGENT = 1\n",
    "roles/senior/prompts.py": "SENIOR = 1\n",
    "roles/senior/system_prompt.md": "# Сеньор\n",
    "roles/common/prompts.py": "COMMON = 1\n",
    "tools/files/read_prompts.py": "READ = 1\n",
    "tools/shell/common_prompts.py": "SHELL = 1\n",
}

# Файлы в папке промптов теста, которые не являются файлами промптов.
OTHER_FILES = {
    "agent/graph.py": "GRAPH = 1\n",
    "roles/senior/node.py": "NODE = 1\n",
    "tools/files/read.py": "TOOL = 1\n",
}

# Дата изменения файлов теста.
FIRST_DATE = datetime(2026, 10, 10, 12, 0)

# Другая дата изменения: следующий день.
NEXT_DATE = datetime(2026, 10, 11, 9, 30)


@pytest.fixture
def prompts_root(tmp_path: Path) -> Path:
    """
    Папка промптов теста: файлы промптов и другие файлы, дата изменения у всех FIRST_DATE.

    Возвращает: Путь папки промптов.
    """
    root = tmp_path / "core"
    for relative_path, content in {**PROMPT_FILES, **OTHER_FILES}.items():
        path = root / relative_path
        path.parent.mkdir(parents = True, exist_ok = True)
        path.write_text(content, encoding = "utf-8")
        _set_modified(path = path, moment = FIRST_DATE)

    return root


def test_copies_only_prompt_files(prompts_root: Path, tmp_path: Path) -> None:
    """
    В базу попадают только файлы промптов, по тем же путям, с содержимым и датой изменения оригинала.
    """
    db_dir = tmp_path / "prompts_db"
    save_prompts(prompts_root = prompts_root, db_dir = db_dir, run_dir = tmp_path / "run")

    copies = sorted(path.relative_to(db_dir).as_posix() for path in db_dir.rglob("*") if path.is_file())
    expected = sorted(
        f"{relative_path}.261010.{_fingerprint(path = prompts_root / relative_path)}"
        for relative_path in PROMPT_FILES
    )
    assert copies == expected

    for relative_path in PROMPT_FILES:
        source = prompts_root / relative_path
        copy = db_dir / Path(relative_path).with_name(build_copy_name(source = source))
        assert copy.read_bytes() == source.read_bytes()
        assert copy.stat().st_mtime == source.stat().st_mtime


def test_run_list_names_every_copy(prompts_root: Path, tmp_path: Path) -> None:
    """
    Список прогона лежит в папке прогона и называет каждый файл промптов и его копию в базе.
    """
    db_dir = tmp_path / "prompts_db"
    run_dir = tmp_path / "run"
    list_path = save_prompts(prompts_root = prompts_root, db_dir = db_dir, run_dir = run_dir)

    assert list_path == run_dir / RUN_PROMPTS_FILE_NAME
    listed = list_path.read_text(encoding = "utf-8")
    for relative_path in PROMPT_FILES:
        copy_name = build_copy_name(source = prompts_root / relative_path)
        assert f"| {relative_path} | {Path(relative_path).with_name(copy_name).as_posix()} |" in listed

    for relative_path in OTHER_FILES:
        assert relative_path not in listed


def test_unchanged_files_are_not_copied_again(prompts_root: Path, tmp_path: Path) -> None:
    """
    Повторный прогон без правок не создаёт новых копий.
    """
    db_dir = tmp_path / "prompts_db"
    save_prompts(prompts_root = prompts_root, db_dir = db_dir, run_dir = tmp_path / "run_1")
    first_copies = _db_files(db_dir = db_dir)

    save_prompts(prompts_root = prompts_root, db_dir = db_dir, run_dir = tmp_path / "run_2")

    assert _db_files(db_dir = db_dir) == first_copies


def test_changed_content_makes_new_copy(prompts_root: Path, tmp_path: Path) -> None:
    """
    Правка файла в тот же день даёт вторую копию; старая остаётся, список нового прогона называет новую.
    """
    db_dir = tmp_path / "prompts_db"
    source = prompts_root / "roles/senior/prompts.py"
    save_prompts(prompts_root = prompts_root, db_dir = db_dir, run_dir = tmp_path / "run_1")
    old_name = build_copy_name(source = source)

    source.write_text("SENIOR = 2\n", encoding = "utf-8")
    _set_modified(path = source, moment = FIRST_DATE)
    list_path = save_prompts(prompts_root = prompts_root, db_dir = db_dir, run_dir = tmp_path / "run_2")
    new_name = build_copy_name(source = source)

    assert new_name != old_name
    assert sorted(path.name for path in (db_dir / "roles/senior").glob("prompts.py.*")) == sorted([old_name, new_name])
    assert f"roles/senior/{new_name}" in list_path.read_text(encoding = "utf-8")
    assert f"roles/senior/{old_name}" not in list_path.read_text(encoding = "utf-8")


def test_same_content_on_other_date_makes_new_copy(prompts_root: Path, tmp_path: Path) -> None:
    """
    Тот же текст с датой изменения другого дня даёт новую копию: дата - часть имени копии.
    """
    db_dir = tmp_path / "prompts_db"
    source = prompts_root / "agent/prompts.py"
    save_prompts(prompts_root = prompts_root, db_dir = db_dir, run_dir = tmp_path / "run_1")

    _set_modified(path = source, moment = NEXT_DATE)
    save_prompts(prompts_root = prompts_root, db_dir = db_dir, run_dir = tmp_path / "run_2")

    fingerprint = _fingerprint(path = source)
    copy_names = sorted(path.name for path in (db_dir / "agent").iterdir())
    assert copy_names == [f"prompts.py.261010.{fingerprint}", f"prompts.py.261011.{fingerprint}"]


def test_project_prompt_files_are_found() -> None:
    """
    В папке промптов проекта находятся файлы основного агента, ролей и инструментов.
    """
    found = {path.relative_to(PROMPTS_ROOT).as_posix() for path in find_prompt_files(prompts_root = PROMPTS_ROOT)}

    assert "agent/prompts.py" in found
    assert "roles/senior/prompts.py" in found
    assert "roles/senior/system_prompt.md" in found
    assert "roles/common/prompts.py" in found
    assert "tools/files/common_prompts.py" in found
    assert "tools/shell/bash_prompts.py" in found


def _fingerprint(*, path: Path) -> str:
    """
    Считает отпечаток содержимого файла.

        path: файл промптов.

    Возвращает: Первые 20 знаков sha256 содержимого.
    """
    return hashlib.sha256(path.read_bytes()).hexdigest()[:20]


def _db_files(*, db_dir: Path) -> set[str]:
    """
    Перечисляет файлы базы.

        db_dir: папка базы промптов.

    Возвращает: Пути файлов относительно папки базы.
    """
    return {path.relative_to(db_dir).as_posix() for path in db_dir.rglob("*") if path.is_file()}


def _set_modified(*, path: Path, moment: datetime) -> None:
    """
    Задаёт дату изменения файла.

        path: файл.
        moment: дата и время изменения.
    """
    timestamp = moment.timestamp()
    os.utime(path, (timestamp, timestamp))

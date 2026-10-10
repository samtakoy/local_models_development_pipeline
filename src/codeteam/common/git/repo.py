"""Команды git над репозиторием в папке проекта."""

import subprocess
from pathlib import Path


class GitCommandError(RuntimeError):
    """Команда git завершилась с ошибкой."""


def is_repository(*, project_dir: Path) -> bool:
    """
    Проверяет, есть ли в папке проекта свой репозиторий git.

        project_dir: папка проекта.

    Возвращает: True, если в папке проекта есть .git.
    """
    return (project_dir / ".git").exists()


def init_repository(*, project_dir: Path) -> None:
    """
    Создаёт репозиторий git в папке проекта.

        project_dir: папка проекта.
    """
    _run_git(project_dir = project_dir, arguments = ["init"])


# Состояние нового, ещё не отслеживаемого файла в выводе git status --porcelain.
UNTRACKED_STATUS = "??"


def has_uncommitted_changes(*, project_dir: Path) -> bool:
    """
    Проверяет, есть ли в рабочей папке незакоммиченные правки и новые файлы.

        project_dir: папка проекта.

    Возвращает: True, если git status показывает изменения.
    """
    return bool(list_uncommitted_changes(project_dir = project_dir))


def list_uncommitted_changes(*, project_dir: Path) -> list[tuple[str, str]]:
    """
    Перечисляет незакоммиченные правки и новые файлы рабочей папки; файлы из .gitignore не входят.

        project_dir: папка проекта.

    Возвращает: Пары (состояние, путь) из git status --porcelain по порядку вывода;
        состояние UNTRACKED_STATUS — новый файл.
    """
    output = _run_git(project_dir = project_dir, arguments = ["status", "--porcelain", "--untracked-files=all"])

    return [(line[:2], line[3:]) for line in output.splitlines() if line.strip()]


def commit_all(*, project_dir: Path, message: str) -> bool:
    """
    Добавляет в индекс все изменения рабочей папки и коммитит их.

        project_dir: папка проекта.
        message: сообщение коммита.

    Возвращает: True, если коммит сделан; False, если коммитить нечего.
    """
    _run_git(project_dir = project_dir, arguments = ["add", "-A"])
    if not _has_staged_changes(project_dir = project_dir):
        return False

    _run_git(project_dir = project_dir, arguments = ["commit", "-m", message])

    return True


def commit_paths(*, project_dir: Path, paths: tuple[str, ...], message: str) -> None:
    """
    Коммитит только указанные файлы; остальные изменения индекса не попадают в коммит.

        project_dir: папка проекта.
        paths: пути файлов относительно папки проекта.
        message: сообщение коммита.
    """
    _run_git(project_dir = project_dir, arguments = ["add", "--", *paths])
    _run_git(project_dir = project_dir, arguments = ["commit", "-m", message, "--", *paths])


def head_commit(*, project_dir: Path) -> str:
    """
    Читает последний коммит репозитория.

        project_dir: папка проекта.

    Возвращает: Полный хэш коммита HEAD.
    """
    return _run_git(project_dir = project_dir, arguments = ["rev-parse", "HEAD"]).strip()


def restore_paths(*, project_dir: Path, paths: tuple[str, ...]) -> None:
    """
    Возвращает файлы к последнему коммиту: содержимое и индекс.

        project_dir: папка проекта.
        paths: пути отслеживаемых файлов относительно папки проекта.
    """
    _run_git(project_dir = project_dir, arguments = ["checkout", "HEAD", "--", *paths])


def _has_staged_changes(*, project_dir: Path) -> bool:
    """
    Проверяет, есть ли в индексе изменения для коммита.

        project_dir: папка проекта.

    Возвращает: True, если индекс отличается от последнего коммита.
    """
    output = _run_git(project_dir = project_dir, arguments = ["status", "--porcelain", "--untracked-files=no"])

    return any(line[:1] not in (" ", "?") for line in output.splitlines() if line)


def _run_git(*, project_dir: Path, arguments: list[str]) -> str:
    """
    Запускает команду git в папке проекта.

        project_dir: папка проекта.
        arguments: аргументы git.

    Возвращает: Вывод команды в stdout.
    """
    result = subprocess.run(
        ["git", *arguments],
        cwd = project_dir,
        stdin = subprocess.DEVNULL,
        capture_output = True,
        text = True,
    )
    if result.returncode != 0:
        raise GitCommandError(
            f"git {' '.join(arguments)}: код возврата {result.returncode}\n{result.stdout}{result.stderr}"
        )

    return result.stdout

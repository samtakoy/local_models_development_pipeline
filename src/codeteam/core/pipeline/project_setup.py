"""Подготовка папки проекта к прогону: репозиторий git и архив личных папок агентов."""

import logging
import shutil
from pathlib import Path

from codeteam.common.git import commit_all, commit_paths, has_uncommitted_changes, init_repository, is_repository
from codeteam.core.agent.workspace import CHECK_DIR, CLOSED_FILE_NAMES, PRIVATE_ROOT

logger = logging.getLogger(__name__)

# Папка архива внутри папки личных папок: содержимое прошлых прогонов.
ARCHIVE_DIR_NAME = "archive"

GITIGNORE_NAME = ".gitignore"

# Системные файлы, которые не попадают в репозиторий проекта.
SYSTEM_FILE_NAMES = (".DS_Store", ".idea",)

# Строки .gitignore: закрытые файлы, системные файлы, папка личных папок агентов и папка временных файлов проверки.
GITIGNORE_LINES = (
    *CLOSED_FILE_NAMES,
    *SYSTEM_FILE_NAMES,
    f"{PRIVATE_ROOT.as_posix()}/",
    f"{CHECK_DIR.as_posix()}/",
)

INITIAL_COMMIT_MESSAGE = "codeteam: исходное состояние проекта"
GITIGNORE_COMMIT_MESSAGE = f"codeteam: {' и '.join(GITIGNORE_LINES)} в {GITIGNORE_NAME}"


class UncommittedChangesError(RuntimeError):
    """В репозитории проекта есть незакоммиченные правки."""


def prepare_project(*, project_dir: Path, run_name: str) -> None:
    """
    Готовит папку проекта к прогону.

    Репозитория нет — создаёт его и коммитит исходное состояние проекта. Репозиторий есть —
    проверяет, что незакоммиченных правок нет. Дописывает в .gitignore строки GITIGNORE_LINES.
    Переносит прежнее содержимое папки личных папок в архив прогона.

        project_dir: папка проекта.
        run_name: имя прогона: имя папки архива.
    """
    fresh_repository = not is_repository(project_dir = project_dir)
    if fresh_repository:
        init_repository(project_dir = project_dir)
        logger.info(f"[git] создан репозиторий в {project_dir}")
    elif has_uncommitted_changes(project_dir = project_dir):
        raise UncommittedChangesError(
            f"в проекте {project_dir} есть незакоммиченные правки: закоммитьте или отмените их до запуска"
        )

    gitignore_changed = _add_gitignore_lines(project_dir = project_dir)
    if fresh_repository:
        commit_all(project_dir = project_dir, message = INITIAL_COMMIT_MESSAGE)
        logger.info(f"[git] коммит: {INITIAL_COMMIT_MESSAGE}")
    elif gitignore_changed:
        commit_paths(project_dir = project_dir, paths = (GITIGNORE_NAME,), message = GITIGNORE_COMMIT_MESSAGE)
        logger.info(f"[git] коммит: {GITIGNORE_COMMIT_MESSAGE}")

    _archive_private_root(project_dir = project_dir, run_name = run_name)


def _add_gitignore_lines(*, project_dir: Path) -> bool:
    """
    Дописывает в .gitignore проекта недостающие строки GITIGNORE_LINES.

    Строка считается уже записанной и без начального или конечного «/».

        project_dir: папка проекта.

    Возвращает: True, если файл изменён.
    """
    gitignore_path = project_dir / GITIGNORE_NAME
    text = gitignore_path.read_text(encoding = "utf-8") if gitignore_path.exists() else ""
    present = {line.strip().strip("/") for line in text.splitlines()}
    missing = [line for line in GITIGNORE_LINES if line.strip("/") not in present]
    if not missing:
        return False

    if text and not text.endswith("\n"):
        text += "\n"
    gitignore_path.write_text(text + "\n".join(missing) + "\n", encoding = "utf-8")
    logger.info(f"[git] в {GITIGNORE_NAME} добавлено: {', '.join(missing)}")

    return True


def _archive_private_root(*, project_dir: Path, run_name: str) -> None:
    """
    Переносит содержимое папки личных папок, кроме архива, в папку архива прогона.

        project_dir: папка проекта.
        run_name: имя прогона: имя папки архива.
    """
    private_root = project_dir / PRIVATE_ROOT
    if not private_root.exists():
        return

    entries = [entry for entry in private_root.iterdir() if entry.name != ARCHIVE_DIR_NAME]
    if not entries:
        return

    archive_dir = private_root / ARCHIVE_DIR_NAME / run_name
    archive_dir.mkdir(parents = True)
    for entry in entries:
        shutil.move(str(entry), str(archive_dir / entry.name))

    logger.info(f"[архив] прежние личные папки перенесены в {archive_dir.relative_to(project_dir)}")

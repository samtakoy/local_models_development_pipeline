"""Личные папки запусков агентов: <роль>_r<номер запуска> и перенос черновика и контекста из прошлой папки роли."""

import re
import shutil
from pathlib import Path

from codeteam.core.agent.workspace import PRIVATE_ROOT, context_path, draft_dir
from codeteam.core.pipeline.state import Rework
from codeteam.core.roles.common.review import rework_for


def role_private_dir_name(*, project_dir: Path, parent: Path, role_name: str, rework: Rework | None) -> Path:
    """
    Создаёт личную папку следующего запуска роли в узле пайплайна. Если работа возвращена этой роли,
    из прошлой папки роли переносится то, что задал возврат; иначе папка чистая.

        project_dir: папка проекта.
        parent: папка внутри папки личных папок, где лежат папки запусков роли; Path(".") - сама папка личных папок.
        role_name: имя роли.
        rework: возврат работы из состояния пайплайна; None - возврата нет.

    Возвращает: Путь новой папки внутри папки личных папок, например stage_10/developer_r2.
    """
    own_rework = rework_for(rework = rework, role_name = role_name)

    return reserve_private_dir_name(
        project_dir = project_dir,
        parent = parent,
        role_name = role_name,
        preserve_draft = own_rework is not None and own_rework.preserve_draft,
        preserve_context = own_rework is not None and own_rework.preserve_context,
    )


def reserve_private_dir_name(
    *,
    project_dir: Path,
    parent: Path,
    role_name: str,
    preserve_draft: bool,
    preserve_context: bool,
) -> Path:
    """
    Создаёт личную папку следующего запуска роли: <роль>_r<номер>, номер на 1 больше последнего.
    Если папка с этим номером уже есть, берётся следующий номер.

        project_dir: папка проекта.
        parent: папка внутри папки личных папок, где лежат папки запусков роли; Path(".") - сама папка личных папок.
        role_name: имя роли.
        preserve_draft: скопировать в новую папку черновик из прошлой папки роли.
        preserve_context: скопировать в новую папку файл контекста из прошлой папки роли.

    Возвращает: Путь новой папки внутри папки личных папок, например stage_10/developer_r2.
    """
    parent_dir = project_dir / PRIVATE_ROOT / parent
    parent_dir.mkdir(parents = True, exist_ok = True)
    last_number = _last_run_number(parent_dir = parent_dir, role_name = role_name)
    number = last_number + 1
    while True:
        try:
            (parent_dir / _run_dir_name(role_name = role_name, number = number)).mkdir()
            break
        except FileExistsError:
            number += 1

    new_dir = parent_dir / _run_dir_name(role_name = role_name, number = number)
    if last_number > 0:
        previous_dir = parent_dir / _run_dir_name(role_name = role_name, number = last_number)
        _copy_previous(
            previous_dir = previous_dir,
            new_dir = new_dir,
            preserve_draft = preserve_draft,
            preserve_context = preserve_context,
        )

    return new_dir.relative_to(project_dir / PRIVATE_ROOT)


def last_private_dir_name(*, project_dir: Path, parent: Path, role_name: str) -> Path | None:
    """
    Находит личную папку последнего запуска роли.

        project_dir: папка проекта.
        parent: папка внутри папки личных папок, где лежат папки запусков роли; Path(".") - сама папка личных папок.
        role_name: имя роли.

    Возвращает: Путь папки с наибольшим номером внутри папки личных папок; None, если запусков роли не было.
    """
    parent_dir = project_dir / PRIVATE_ROOT / parent
    if not parent_dir.is_dir():
        return None

    last_number = _last_run_number(parent_dir = parent_dir, role_name = role_name)
    if last_number == 0:
        return None

    return parent / _run_dir_name(role_name = role_name, number = last_number)


def _last_run_number(*, parent_dir: Path, role_name: str) -> int:
    """
    Находит наибольший номер запуска роли среди папок <роль>_r<номер>.

        parent_dir: папка с папками запусков роли.
        role_name: имя роли.

    Возвращает: Наибольший номер; 0, если папок запусков роли нет.
    """
    pattern = re.compile(rf"{re.escape(role_name)}_r(\d+)")
    numbers = [
        int(match.group(1))
        for entry in parent_dir.iterdir()
        if entry.is_dir() and (match := pattern.fullmatch(entry.name)) is not None
    ]

    return max(numbers, default = 0)


def _run_dir_name(*, role_name: str, number: int) -> str:
    """
    Собирает имя папки запуска роли.

        role_name: имя роли.
        number: номер запуска, с 1.

    Возвращает: Имя вида developer_r2.
    """
    return f"{role_name}_r{number}"


def _copy_previous(*, previous_dir: Path, new_dir: Path, preserve_draft: bool, preserve_context: bool) -> None:
    """
    Копирует черновик и файл контекста из прошлой папки роли в новую.

        previous_dir: прошлая папка роли.
        new_dir: новая папка роли.
        preserve_draft: скопировать черновик, если он есть.
        preserve_context: скопировать файл контекста, если он есть.
    """
    previous_draft = draft_dir(private_dir = previous_dir)
    if preserve_draft and previous_draft.is_dir():
        shutil.copytree(previous_draft, draft_dir(private_dir = new_dir))

    previous_context = context_path(private_dir = previous_dir)
    if preserve_context and previous_context.is_file():
        shutil.copy2(previous_context, context_path(private_dir = new_dir))

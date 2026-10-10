"""Файлы вывода инструментов оболочки: логи служб start_service и полный вывод обрезанных команд bash."""

import os
import tempfile
from pathlib import Path

from codeteam.core.agent.workspace import CHECK_DIR, PathOutsideWorkspace, Workspace


def new_output_file(*, workspace: Workspace, dir_name: str, prefix: str) -> Path:
    """
    Создаёт пустой файл вывода: в папке CHECK_DIR/dir_name проекта, если туда разрешена запись,
    иначе во временной папке системы.

        workspace: рабочее место вызова.
        dir_name: папка файлов внутри CHECK_DIR.
        prefix: начало имени файла.

    Возвращает: Путь файла.
    """
    output_dir = workspace.project_dir / CHECK_DIR / dir_name
    try:
        workspace.resolve_writable(path = str(output_dir))
    except PathOutsideWorkspace:
        output_dir = Path(tempfile.gettempdir())

    output_dir.mkdir(parents = True, exist_ok = True)
    output_descriptor, output_name = tempfile.mkstemp(prefix = prefix, suffix = ".log", dir = output_dir)
    os.close(output_descriptor)

    return Path(output_name)

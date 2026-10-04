"""Инструмент агента delete: удаление файла."""

from pathlib import Path

from langchain_core.tools import BaseTool, StructuredTool, ToolException
from pydantic import BaseModel, Field

from codeteam.common.files import IgnoreRules
from codeteam.core.agent.workspace import PathOutsideWorkspace, Workspace
from codeteam.core.tools.files._hints import PATH_HINT
from codeteam.core.tools.files._internal._paths import refuse_hidden_path

# Имя инструмента удаления файла.
DELETE_TOOL_NAME = "delete"

DELETE_DESCRIPTION = """Удаляет файл. Папки не удаляет.
Удаляет только там, где разрешена запись.
Закрытые файлы проекта (.env, личные папки других агентов) не удаляет."""


class DeleteArguments(BaseModel):
    """
    Аргументы delete.
    """

    file_path: str = Field(description = "путь файла, абсолютный или относительно папки проекта")


def build_delete_tool(*, workspace: Workspace, ignore_rules: IgnoreRules) -> BaseTool:
    """
    Собирает инструмент delete для рабочего места вызова.

        workspace: рабочее место вызова.
        ignore_rules: правила пропуска файлов проекта.

    Возвращает: Инструмент delete.
    """

    def delete(*, file_path: str) -> str:
        """
        Удаляет файл.

            file_path: путь от агента.

        Возвращает: Итог удаления. Ошибку для агента поднимает ToolException.
        """
        try:
            path = workspace.resolve_writable(path = file_path)
        except PathOutsideWorkspace as error:
            raise ToolException(f"Ошибка: {error}") from error

        refuse_hidden_path(workspace = workspace, ignore_rules = ignore_rules, path = path)

        return _delete(workspace = workspace, path = path)

    return StructuredTool.from_function(
        func = delete,
        name = DELETE_TOOL_NAME,
        description = DELETE_DESCRIPTION,
        args_schema = DeleteArguments,
        handle_tool_error = True,
    )


def _delete(*, workspace: Workspace, path: Path) -> str:
    """
    Удаляет существующий файл.

        workspace: рабочее место вызова.
        path: абсолютный путь.

    Возвращает: Итог удаления. Ошибку для агента поднимает ToolException.
    """
    shown_path = workspace.display_path(path = path)
    if path.is_dir():
        raise ToolException(f"Ошибка: {shown_path} — папка, delete удаляет только файлы")

    if not path.is_file():
        raise ToolException(f"Ошибка: файл не найден: {shown_path}. {PATH_HINT}")

    path.unlink()

    return f"Удалён файл {shown_path}"

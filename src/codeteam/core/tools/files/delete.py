"""Инструмент агента delete: удаление файла."""

from pathlib import Path

from langchain_core.tools import BaseTool, StructuredTool, ToolException
from pydantic import BaseModel, Field

from codeteam.common.files import IgnoreRules
from codeteam.core.agent.workspace import PathOutsideWorkspace, Workspace
from codeteam.core.tools.files.common_prompts import FILE_NOT_FOUND_ERROR, PATH_ACCESS_ERROR
from codeteam.core.tools.files.delete_prompts import (
    DELETE_DESCRIPTION,
    DELETE_DIRECTORY_ERROR,
    DELETE_FILE_PATH_DESCRIPTION,
)
from codeteam.core.tools.files._internal._paths import refuse_hidden_path

# Имя инструмента удаления файла.
DELETE_TOOL_NAME = "delete"


class DeleteArguments(BaseModel):
    """
    Аргументы delete.
    """

    file_path: str = Field(description = DELETE_FILE_PATH_DESCRIPTION)


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
            raise ToolException(PATH_ACCESS_ERROR.format(error = error)) from error

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
        raise ToolException(DELETE_DIRECTORY_ERROR.format(shown_path = shown_path))

    if not path.is_file():
        raise ToolException(FILE_NOT_FOUND_ERROR.format(shown_path = shown_path))

    path.unlink()

    return f"Удалён файл {shown_path}"

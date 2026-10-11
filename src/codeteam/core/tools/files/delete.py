"""Инструмент агента delete: удаление файла."""

from pathlib import Path

from langchain_core.tools import BaseTool, StructuredTool, ToolException
from pydantic import BaseModel, Field

from codeteam.common.files import IgnoreRules
from codeteam.core.agent.workspace import PathOutsideWorkspace, Workspace
from codeteam.core.tools.files.common_prompts import FILE_NOT_FOUND_ERROR, FILE_PATH_DESCRIPTION
from codeteam.core.tools.files.delete_prompts import DELETE_DESCRIPTION, DELETE_DIRECTORY_ERROR, DELETE_RESULT
from codeteam.core.tools.files._internal._paths import path_refusal_error, refuse_hidden_path
from codeteam.core.tools.files.refusals import PathRefusal, PathRefusals

# Имя инструмента удаления файла.
DELETE_TOOL_NAME = "delete"


class DeleteArguments(BaseModel):
    """
    Аргументы delete.
    """

    file_path: str = Field(description = FILE_PATH_DESCRIPTION)


def build_delete_tool(*, workspace: Workspace, ignore_rules: IgnoreRules, refusals: PathRefusals) -> BaseTool:
    """
    Собирает инструмент delete для рабочего места вызова.

        workspace: рабочее место вызова.
        ignore_rules: правила пропуска файлов проекта.
        refusals: отказы по пути за шаг агента.

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
            raise path_refusal_error(
                error = error,
                refusal = PathRefusal(path = file_path, is_write = True),
                refusals = refusals,
            ) from error

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

    return DELETE_RESULT.format(shown_path = shown_path)

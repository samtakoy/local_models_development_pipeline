"""Инструмент агента glob: файлы проекта по маске пути."""

from itertools import islice

from langchain_core.tools import BaseTool, StructuredTool, ToolException
from pydantic import BaseModel, Field

from codeteam.common.files import IgnoreRules, visible_files
from codeteam.core.agent.workspace import Workspace
from codeteam.core.tools.files.glob_prompts import (
    GLOB_DESCRIPTION,
    GLOB_LIMIT_NOTE,
    GLOB_NOT_DIRECTORY_ERROR,
    GLOB_NOTHING_FOUND,
    GLOB_PATH_DESCRIPTION,
    GLOB_PATTERN_DESCRIPTION,
)
from codeteam.core.tools.files._internal._paths import compile_path_mask, resolve_visible_path

# Имя инструмента поиска файлов по маске.
GLOB_TOOL_NAME = "glob"

# Сколько путей glob отдаёт за раз.
GLOB_RESULT_LIMIT = 100


class GlobArguments(BaseModel):
    """
    Аргументы glob.
    """

    pattern: str = Field(description = GLOB_PATTERN_DESCRIPTION)
    path: str | None = Field(default = None, description = GLOB_PATH_DESCRIPTION)


def build_glob_tool(*, workspace: Workspace, ignore_rules: IgnoreRules) -> BaseTool:
    """
    Собирает инструмент glob для рабочего места вызова.

        workspace: рабочее место вызова.
        ignore_rules: правила пропуска файлов проекта.

    Возвращает: Инструмент glob.
    """

    def glob(*, pattern: str, path: str | None = None) -> str:
        """
        Ищет файлы по маске пути для агента.

            pattern: маска пути.
            path: папка поиска от агента, None — папка проекта.

        Возвращает: Пути найденных файлов. Ошибку для агента поднимает ToolException.
        """
        search_dir = resolve_visible_path(
            workspace = workspace,
            ignore_rules = ignore_rules,
            path = "." if path is None else path,
        )
        if not search_dir.is_dir():
            shown_path = workspace.display_path(path = search_dir)
            raise ToolException(GLOB_NOT_DIRECTORY_ERROR.format(shown_path = shown_path))

        mask = compile_path_mask(mask = pattern)
        matched_files = (
            file_path for file_path in visible_files(rules = ignore_rules, root = search_dir)
            if mask.match_file(file_path.relative_to(search_dir).as_posix())
        )
        found = list(islice(matched_files, GLOB_RESULT_LIMIT + 1))
        if not found:
            return GLOB_NOTHING_FOUND

        shown = [workspace.display_path(path = file_path) for file_path in found[:GLOB_RESULT_LIMIT]]
        if len(found) > GLOB_RESULT_LIMIT:
            shown.append("\n" + GLOB_LIMIT_NOTE.format(limit = GLOB_RESULT_LIMIT))

        return "\n".join(shown)

    return StructuredTool.from_function(
        func = glob,
        name = GLOB_TOOL_NAME,
        description = GLOB_DESCRIPTION,
        args_schema = GlobArguments,
        handle_tool_error = True,
    )

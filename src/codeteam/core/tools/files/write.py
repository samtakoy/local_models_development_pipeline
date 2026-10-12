"""Инструмент агента write: запись файла целиком."""

import json
from pathlib import Path
from typing import Any

from langchain_core.tools import BaseTool, StructuredTool, ToolException
from pydantic import BaseModel, Field, field_validator

from codeteam.common.files import IgnoreRules, split_lines
from codeteam.core.agent.workspace import PathOutsideWorkspace, Workspace
from codeteam.core.tools.files.common_prompts import DIRECTORY_ERROR, FILE_PATH_DESCRIPTION
from codeteam.core.tools.files.write_prompts import WRITE_CONTENT_DESCRIPTION, WRITE_DESCRIPTION, WRITE_RESULT
from codeteam.core.tools.files._internal._draft import draft_file_refusal
from codeteam.core.tools.files._internal._paths import path_refusal_error, refuse_hidden_path
from codeteam.core.tools.files._internal._seen_files import SeenFiles
from codeteam.core.tools.files._internal.format import format_header
from codeteam.core.tools.files.refusals import PathRefusal, PathRefusals

# Имя инструмента записи файла.
WRITE_TOOL_NAME = "write"


class WriteArguments(BaseModel):
    """
    Аргументы write.
    """

    file_path: str = Field(description = FILE_PATH_DESCRIPTION)
    content: str = Field(description = WRITE_CONTENT_DESCRIPTION)

    @field_validator("content", mode = "before")
    @classmethod
    def json_content_to_text(cls, value: Any) -> Any:
        """
        Переводит содержимое-объект или содержимое-список в текст JSON.

            value: содержимое файла из вызова модели.

        Возвращает: Текст JSON для объекта и списка, остальное как есть.
        """
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii = False, indent = 2)

        return value


def build_write_tool(
    *,
    workspace: Workspace,
    seen_files: SeenFiles,
    ignore_rules: IgnoreRules,
    refusals: PathRefusals,
) -> BaseTool:
    """
    Собирает инструмент write для рабочего места вызова.

        workspace: рабочее место вызова.
        seen_files: файлы, которые видел вызов, общие с read и edit.
        ignore_rules: правила пропуска файлов проекта.
        refusals: отказы по пути за шаг агента.

    Возвращает: Инструмент write.
    """

    def write(*, file_path: str, content: str) -> str:
        """
        Записывает файл целиком.

            file_path: путь от агента.
            content: содержимое файла.

        Возвращает: Итог записи. Ошибку для агента поднимает ToolException.
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

        return _write(workspace = workspace, seen_files = seen_files, path = path, content = content)

    return StructuredTool.from_function(
        func = write,
        name = WRITE_TOOL_NAME,
        description = WRITE_DESCRIPTION,
        args_schema = WriteArguments,
        handle_tool_error = True,
    )


def _write(*, workspace: Workspace, seen_files: SeenFiles, path: Path, content: str) -> str:
    """
    Записывает файл целиком; существующий непустой — только после свежего чтения.

        workspace: рабочее место вызова.
        seen_files: файлы, которые видел вызов.
        path: абсолютный путь.
        content: содержимое файла.

    Возвращает: Заголовок файла и итог записи. Ошибку для агента поднимает ToolException.
    """
    shown_path = workspace.display_path(path = path)
    if path.is_dir():
        raise ToolException(DIRECTORY_ERROR.format(shown_path = shown_path))

    draft_refusal = draft_file_refusal(workspace = workspace, path = path)
    if draft_refusal is not None:
        raise ToolException(draft_refusal)

    # Пустой файл перезаписывается без чтения: терять в нём нечего
    if path.exists() and path.stat().st_size > 0:
        stale_reason = seen_files.stale_reason(path = path, shown_path = shown_path)
        if stale_reason is not None:
            raise ToolException(stale_reason)

    raw_content = content.encode("utf-8")
    path.parent.mkdir(parents = True, exist_ok = True)
    path.write_bytes(raw_content)
    line_count = len(split_lines(text = content))
    seen_files.remember(path = path, content = raw_content)
    header = format_header(path = shown_path)

    return header + "\n" + WRITE_RESULT.format(shown_path = shown_path, line_count = line_count)

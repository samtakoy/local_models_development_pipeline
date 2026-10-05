"""Инструмент агента write: запись файла целиком."""

from pathlib import Path

from langchain_core.tools import BaseTool, StructuredTool, ToolException
from pydantic import BaseModel, Field

from codeteam.common.files import IgnoreRules, split_lines
from codeteam.core.agent.workspace import PathOutsideWorkspace, Workspace
from codeteam.core.tools.files._internal._draft import draft_file_refusal
from codeteam.core.tools.files._internal._paths import refuse_hidden_path
from codeteam.core.tools.files._internal._seen_files import SeenFiles
from codeteam.core.tools.files._internal.format import format_header

# Имя инструмента записи файла.
WRITE_TOOL_NAME = "write"

WRITE_DESCRIPTION = """Записывает файл целиком, создаёт недостающие папки.
Существующий файл сначала прочитай инструментом read, иначе запись будет отклонена.
Для точечных изменений существующего файла используй edit.
Закрытые файлы проекта (.env, личные папки других агентов) не записывает."""


class WriteArguments(BaseModel):
    """
    Аргументы write.
    """

    file_path: str = Field(description = "путь файла, абсолютный или относительно папки проекта")
    content: str = Field(description = "полное содержимое файла")


def build_write_tool(
    *,
    workspace: Workspace,
    seen_files: SeenFiles,
    ignore_rules: IgnoreRules,
) -> BaseTool:
    """
    Собирает инструмент write для рабочего места вызова.

        workspace: рабочее место вызова.
        seen_files: файлы, которые видел вызов, общие с read и edit.
        ignore_rules: правила пропуска файлов проекта.

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
            raise ToolException(f"Ошибка: {error}") from error

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
        raise ToolException(f"Ошибка: {shown_path} — папка")

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

    return f"{header}\nЗаписан файл {shown_path}: строк {line_count}"

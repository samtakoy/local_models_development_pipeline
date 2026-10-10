"""Инструмент агента read: строки файла с номерами или содержимое папки."""

import math
import re
from pathlib import Path

from langchain_core.tools import BaseTool, StructuredTool, ToolException
from pydantic import BaseModel, Field

from codeteam.common.files import (
    DirectoryEntry,
    FileKind,
    IgnoreRules,
    decode_text,
    file_stats,
    list_directory,
    number_lines,
    split_lines,
)
from codeteam.core.agent.workspace import Workspace
from codeteam.core.tools.files.common_prompts import NOT_TEXT_REFUSAL
from codeteam.core.tools.files.read_prompts import (
    READ_BINARY_ENTRY,
    READ_DESCRIPTION,
    READ_DIRECTORY_HEADER,
    READ_EMPTY_DIRECTORY,
    READ_EMPTY_FILE,
    READ_END_SUMMARY,
    READ_FILE_PATH_DESCRIPTION,
    READ_LARGE_ENTRY,
    READ_LIMIT_DESCRIPTION,
    READ_OFFSET_DESCRIPTION,
    READ_OFFSET_ERROR,
    READ_OFFSET_LIMIT_ERROR,
    READ_PART_SUMMARY,
    READ_SIZE_KILOBYTES,
    READ_SIZE_MEGABYTES,
    READ_TEXT_ENTRY,
)
from codeteam.core.tools.files._internal._paths import resolve_visible_path
from codeteam.core.tools.files._internal._seen_files import SeenFiles
from codeteam.core.tools.files._internal.format import format_header, parse_header

# Имя инструмента чтения.
READ_TOOL_NAME = "read"

# Сколько строк read отдаёт за раз.
READ_LINE_LIMIT = 1000

# Длина строки в выводе read, дальше строка обрезается.
READ_LINE_WIDTH = 2000

# Предел объёма вывода read в символах.
READ_CHARACTER_LIMIT = 30_000

# Байт в килобайте и в мегабайте: для размера файлов в содержимом папки.
BYTES_IN_KILOBYTE = 1024
BYTES_IN_MEGABYTE = 1024 * 1024

# Заготовка {имя} в экранированном тексте шаблона.
_ESCAPED_PLACEHOLDER_PATTERN = re.compile(r"\\\{\w+\\\}")


def _summary_pattern(*, template: str) -> re.Pattern[str]:
    """
    Собирает шаблон поиска итоговой строки read по её тексту: заготовки {имя} становятся числами.

        template: текст итоговой строки с заготовками.

    Возвращает: Шаблон поиска итоговой строки.
    """
    escaped = re.escape(template)

    return re.compile(_ESCAPED_PLACEHOLDER_PATTERN.sub(r"\\d+", escaped))


# Итоговая строка read, когда файл показан до конца.
_END_SUMMARY_PATTERN = _summary_pattern(template = READ_END_SUMMARY)

# Итоговая строка read, когда показана часть файла.
_PART_SUMMARY_PATTERN = _summary_pattern(template = READ_PART_SUMMARY)


class ReadArguments(BaseModel):
    """
    Аргументы read.
    """

    file_path: str = Field(description = READ_FILE_PATH_DESCRIPTION)
    offset: int | None = Field(default = None, description = READ_OFFSET_DESCRIPTION)
    limit: int | None = Field(default = None, description = READ_LIMIT_DESCRIPTION.format(line_limit = READ_LINE_LIMIT))


def build_read_tool(*, workspace: Workspace, seen_files: SeenFiles, ignore_rules: IgnoreRules) -> BaseTool:
    """
    Собирает инструмент read для рабочего места вызова.

        workspace: рабочее место вызова.
        seen_files: файлы, которые видел вызов, общие с write и edit.
        ignore_rules: правила пропуска файлов проекта.

    Возвращает: Инструмент read.
    """

    def read(*, file_path: str, offset: int | None = None, limit: int | None = None) -> str:
        """
        Читает файл или папку для агента.

            file_path: путь от агента.
            offset: номер первой строки, от 1.
            limit: число строк.

        Возвращает: Заголовок файла и строки с номерами. Ошибку для агента поднимает ToolException.
        """
        path = resolve_visible_path(workspace = workspace, ignore_rules = ignore_rules, path = file_path)

        return _read(
            workspace = workspace,
            seen_files = seen_files,
            ignore_rules = ignore_rules,
            path = path,
            offset = 1 if offset is None else offset,
            limit = READ_LINE_LIMIT if limit is None else limit,
        )

    return StructuredTool.from_function(
        func = read,
        name = READ_TOOL_NAME,
        description = READ_DESCRIPTION.format(line_limit = READ_LINE_LIMIT),
        args_schema = ReadArguments,
        handle_tool_error = True,
    )


def _read(
    *,
    workspace: Workspace,
    seen_files: SeenFiles,
    ignore_rules: IgnoreRules,
    path: Path,
    offset: int,
    limit: int,
) -> str:
    """
    Читает файл или папку и отмечает содержимое файла как виденное.

        workspace: рабочее место вызова.
        seen_files: файлы, которые видел вызов.
        ignore_rules: правила пропуска файлов проекта.
        path: существующий абсолютный путь.
        offset: номер первой строки, от 1.
        limit: число строк.

    Возвращает: Заголовок файла и строки с номерами или содержимое папки.
        Ошибку для агента поднимает ToolException.
    """
    shown_path = workspace.display_path(path = path)
    if path.is_dir():
        entries = [
            entry for entry in list_directory(path = path)
            if not ignore_rules.is_closed(path = entry.path)
        ]
        if not entries:
            return READ_EMPTY_DIRECTORY.format(shown_path = shown_path)

        return READ_DIRECTORY_HEADER.format(shown_path = shown_path) + "\n" + "\n".join(_show_entry(entry = entry) for entry in entries)

    if offset < 1 or limit < 1:
        raise ToolException(READ_OFFSET_LIMIT_ERROR)

    raw_content = path.read_bytes()
    text = decode_text(content = raw_content)
    if text is None:
        raise ToolException(NOT_TEXT_REFUSAL.format(shown_path = shown_path))

    lines = split_lines(text = text)
    if not lines:
        seen_files.remember(path = path, content = raw_content)
        return format_header(path = shown_path) + "\n" + READ_EMPTY_FILE

    if offset > len(lines):
        raise ToolException(READ_OFFSET_ERROR.format(offset = offset, line_count = len(lines)))

    page = number_lines(
        lines = lines,
        offset = offset,
        limit = min(limit, READ_LINE_LIMIT),
        line_width = READ_LINE_WIDTH,
        character_limit = READ_CHARACTER_LIMIT,
    )
    seen_files.remember(path = path, content = raw_content)
    summary = _summary(first_number = page.first_number, last_number = page.last_number, total = page.total)
    header = format_header(path = shown_path)
    return header + "\n" + "\n".join(page.lines) + "\n\n" + summary


def is_read_header_line(*, line: str) -> bool:
    """
    Проверяет, что строка — заголовок вывода read, первая строка вывода.

        line: строка.

    Возвращает: True для заголовка вида [путь].
    """
    return parse_header(line = line) is not None


def is_read_summary_line(*, line: str) -> bool:
    """
    Проверяет, что строка — итоговая строка вывода read, последняя строка вывода.

        line: строка.

    Возвращает: True для «(Конец файла, …)» и «(Показаны строки …)».
    """
    text = line.strip()
    patterns = (_END_SUMMARY_PATTERN, _PART_SUMMARY_PATTERN)

    return any(pattern.fullmatch(text) is not None for pattern in patterns)


def _summary(*, first_number: int, last_number: int, total: int) -> str:
    """
    Собирает итоговую строку вывода read.

        first_number: номер первой показанной строки.
        last_number: номер последней показанной строки.
        total: число строк файла.

    Возвращает: «(Конец файла, …)», если показано до конца, иначе «(Показаны строки …)» с продолжением.
    """
    if last_number < total:
        return READ_PART_SUMMARY.format(
            first_number = first_number,
            last_number = last_number,
            total = total,
            next_offset = last_number + 1,
        )

    return READ_END_SUMMARY.format(total = total)


def _show_entry(*, entry: DirectoryEntry) -> str:
    """
    Показывает элемент папки строкой: папку с косой чертой, файл со сведениями.

        entry: элемент папки.

    Возвращает: «имя/» для папки, «имя (строк: N)» для текстового файла,
        «имя (двоичный или не UTF-8, 48 КБ)» для двоичного, «имя (большой, 3.2 МБ)» для большого, имя без сведений, если файл
        не удалось прочитать.
    """
    if entry.is_dir:
        return f"{entry.name}/"

    stats = file_stats(path = entry.path)
    if stats is None:
        return entry.name

    if stats.kind is FileKind.TEXT:
        return READ_TEXT_ENTRY.format(name = entry.name, line_count = stats.line_count)

    if stats.kind is FileKind.BINARY:
        return READ_BINARY_ENTRY.format(name = entry.name, size = _show_size(size_bytes = stats.size_bytes))

    return READ_LARGE_ENTRY.format(name = entry.name, size = _show_size(size_bytes = stats.size_bytes))


def _show_size(*, size_bytes: int) -> str:
    """
    Показывает размер файла в килобайтах или мегабайтах.

        size_bytes: размер в байтах.

    Возвращает: «48 КБ» до 1 МБ, с округлением вверх; «3.2 МБ» от 1 МБ.
    """
    if size_bytes < BYTES_IN_MEGABYTE:
        return READ_SIZE_KILOBYTES.format(size = math.ceil(size_bytes / BYTES_IN_KILOBYTE))

    return READ_SIZE_MEGABYTES.format(size = size_bytes / BYTES_IN_MEGABYTE)

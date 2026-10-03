"""Инструмент агента read: строки файла с номерами или содержимое папки."""

import re
from pathlib import Path

from langchain_core.tools import BaseTool, StructuredTool, ToolException
from pydantic import BaseModel, Field

from codeteam.common.files import IgnoreRules, list_directory, number_lines, split_lines
from codeteam.core.agent.workspace import Workspace
from codeteam.core.tools.files._internal._paths import resolve_visible_path
from codeteam.core.tools.files._internal._seen_files import SeenFiles
from codeteam.core.tools.files._internal.format import format_header, parse_header

# Имя инструмента чтения.
READ_TOOL_NAME = "read"

# Сколько строк read отдаёт за раз.
READ_LINE_LIMIT = 2000

# Длина строки в выводе read, дальше строка обрезается.
READ_LINE_WIDTH = 2000

# Предел объёма вывода read в символах.
READ_CHARACTER_LIMIT = 50_000

# Итоговая строка read, когда файл показан до конца: вид задаёт _summary.
_END_SUMMARY_PATTERN = re.compile(r"\(Конец файла, всего строк: \d+\)")

# Итоговая строка read, когда показана часть файла: вид задаёт _summary.
_PART_SUMMARY_PATTERN = re.compile(r"\(Показаны строки \d+-\d+ из \d+\. Продолжение: offset = \d+\)")

READ_DESCRIPTION = """Читает текстовый файл. Первая строка вывода — заголовок [путь],
дальше строки файла в виде "номер:строка". Заголовка и номеров в файле нет.
За раз показывает до 2000 строк; большой файл читай частями через offset и limit.
Для папки показывает её содержимое.
Чтобы найти нужный текст в большом файле, используй grep.
Если не уверен в пути к файлу, найди его через glob по маске.
Закрытые файлы проекта (.env, личные папки других агентов) не читает и в папке не показывает."""


class ReadArguments(BaseModel):
    """
    Аргументы read.
    """

    file_path: str = Field(description = "путь файла или папки, абсолютный или относительно папки проекта")
    offset: int | None = Field(default = None, description = "номер строки, с которой читать, от 1")
    limit: int | None = Field(default = None, description = "сколько строк прочитать, до 2000")


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
        description = READ_DESCRIPTION,
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
            if not ignore_rules.is_closed(path = path / entry.removesuffix("/"))
        ]
        if not entries:
            return f"Папка {shown_path} пуста"

        return f"Папка {shown_path}:\n" + "\n".join(entries)

    if offset < 1 or limit < 1:
        raise ToolException("Ошибка: offset и limit должны быть не меньше 1")

    raw_content = path.read_bytes()
    try:
        text = raw_content.decode("utf-8")
    except UnicodeDecodeError:
        raise ToolException(f"Ошибка: файл {shown_path} не текстовый") from None

    lines = split_lines(text = text)
    if not lines:
        seen_files.remember(path = path, content = raw_content)
        return format_header(path = shown_path) + "\n(Файл пуст)"

    if offset > len(lines):
        raise ToolException(f"Ошибка: offset {offset} больше числа строк в файле ({len(lines)})")

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
        return (
            f"(Показаны строки {first_number}-{last_number} из {total}. "
            f"Продолжение: offset = {last_number + 1})"
        )

    return f"(Конец файла, всего строк: {total})"

"""Инструмент агента grep: строки файлов проекта по регулярному выражению."""

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from itertools import islice
from pathlib import Path

from langchain_core.tools import BaseTool, StructuredTool, ToolException
from pydantic import BaseModel, Field

from codeteam.common.files import IgnoreRules, split_lines, visible_files
from codeteam.core.agent.workspace import Workspace
from codeteam.core.tools.files._internal._paths import compile_path_mask, resolve_visible_path

# Имя инструмента поиска текста.
GREP_TOOL_NAME = "grep"

# Сколько совпадений grep отдаёт за раз.
GREP_RESULT_LIMIT = 100

# Длина строки в выводе grep, дальше строка обрезается.
GREP_LINE_WIDTH = 2000

GREP_DESCRIPTION = """- Поиск по содержимому файлов.
- Ищет по содержимому файлов регулярным выражением.
- Поддерживает полный синтаксис регулярных выражений Python (например "log.*Error", "def\\s+\\w+").
- Файлы можно отобрать маской в параметре include (например "*.js", "*.{ts,tsx}").
- Возвращает пути файлов и номера строк с совпавшими строками.
- Используй, когда нужно найти файлы, содержащие определённый текст.
- Файлы, скрытые правилами проекта (служебные имена и .gitignore), не просматривает."""


class GrepArguments(BaseModel):
    """
    Аргументы grep.
    """

    pattern: str = Field(description = "регулярное выражение для поиска в строках")
    path: str | None = Field(
        default = None,
        description = "папка или файл поиска, по умолчанию папка проекта",
    )
    include: str | None = Field(
        default = None,
        description = "маска пути файлов, например *.py или *.{ts,tsx}",
    )


@dataclass(frozen = True)
class _LineMatch:
    """
    Строка файла, совпавшая с шаблоном.

        path: абсолютный путь файла.
        number: номер строки, от 1.
        text: текст строки.
    """

    path: Path
    number: int
    text: str


def build_grep_tool(*, workspace: Workspace, ignore_rules: IgnoreRules) -> BaseTool:
    """
    Собирает инструмент grep для рабочего места вызова.

        workspace: рабочее место вызова.
        ignore_rules: правила пропуска файлов проекта.

    Возвращает: Инструмент grep.
    """

    def grep(*, pattern: str, path: str | None = None, include: str | None = None) -> str:
        """
        Ищет строки файлов по регулярному выражению для агента.

            pattern: регулярное выражение.
            path: папка или файл поиска от агента, None — папка проекта.
            include: маска пути файлов внутри папки, None — все файлы.

        Возвращает: Совпавшие строки по файлам. Ошибку для агента поднимает ToolException.
        """
        try:
            regex = re.compile(pattern)
        except re.error as error:
            raise ToolException(f"Ошибка: неверное регулярное выражение {pattern}: {error}") from error

        search_path = resolve_visible_path(
            workspace = workspace,
            ignore_rules = ignore_rules,
            path = "." if path is None else path,
        )
        files = _searched_files(ignore_rules = ignore_rules, search_path = search_path, include = include)
        found = list(islice(_matching_lines(files = files, regex = regex), GREP_RESULT_LIMIT + 1))
        if not found:
            return "Совпадений нет"

        return _render(workspace = workspace, found = found)

    return StructuredTool.from_function(
        func = grep,
        name = GREP_TOOL_NAME,
        description = GREP_DESCRIPTION,
        args_schema = GrepArguments,
        handle_tool_error = True,
    )


def _searched_files(*, ignore_rules: IgnoreRules, search_path: Path, include: str | None) -> Iterable[Path]:
    """
    Выбирает файлы для поиска.

        ignore_rules: правила пропуска файлов проекта.
        search_path: существующий файл или папка поиска.
        include: маска пути файлов внутри папки, None — все файлы.

    Возвращает: Сам файл, если поиск по файлу; иначе видимые файлы папки, подходящие под маску.
        Ошибку для агента поднимает ToolException.
    """
    if search_path.is_file():
        return [search_path]

    files = visible_files(rules = ignore_rules, root = search_path)
    if include is None:
        return files

    mask = compile_path_mask(mask = include)

    return (
        file_path for file_path in files
        if mask.match_file(file_path.relative_to(search_path).as_posix())
    )


def _matching_lines(*, files: Iterable[Path], regex: re.Pattern[str]) -> Iterator[_LineMatch]:
    """
    Перебирает строки текстовых файлов и выдаёт совпавшие с шаблоном.

        files: файлы поиска.
        regex: шаблон поиска.

    Возвращает: Совпавшие строки в порядке файлов и номеров строк.
    """
    for file_path in files:
        for number, line in enumerate(_text_lines(path = file_path), start = 1):
            if regex.search(line):
                yield _LineMatch(path = file_path, number = number, text = line)


def _text_lines(*, path: Path) -> list[str]:
    """
    Читает строки текстового файла.

        path: путь файла.

    Возвращает: Строки файла; для нетекстового или нечитаемого файла — пустой список.
    """
    try:
        raw_content = path.read_bytes()
    except OSError:
        return []

    if b"\0" in raw_content:
        return []

    try:
        return split_lines(text = raw_content.decode("utf-8"))
    except UnicodeDecodeError:
        return []


def _render(*, workspace: Workspace, found: list[_LineMatch]) -> str:
    """
    Собирает ответ grep: путь файла и под ним совпавшие строки.

        workspace: рабочее место вызова.
        found: совпадения, на одно больше предела, если совпадений больше предела.

    Возвращает: Текст ответа.
    """
    shown_matches = found[:GREP_RESULT_LIMIT]
    output = [f"Совпадений: {len(shown_matches)}"]
    current_path = None
    for match in shown_matches:
        if match.path != current_path:
            current_path = match.path
            output.append(f"\n{workspace.display_path(path = match.path)}:")

        text = match.text if len(match.text) <= GREP_LINE_WIDTH else match.text[:GREP_LINE_WIDTH] + "…"
        output.append(f"  {match.number}:{text}")

    if len(found) > GREP_RESULT_LIMIT:
        output.append(f"\n(Показаны первые {GREP_RESULT_LIMIT} совпадений. Уточни шаблон, path или include.)")

    return "\n".join(output)

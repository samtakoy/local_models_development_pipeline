"""Инструмент агента edit с заменой текста: фрагмент old_string в файле заменяется на new_string.

Устройство и описание для модели перенесены из opencode (https://github.com/anomalyco/opencode,
packages/opencode/src/tool/edit.ts и edit.txt, коммит 9b4882db54), лицензия MIT; см. THIRD_PARTY_NOTICES.md.
"""

from pathlib import Path

from langchain_core.tools import BaseTool, StructuredTool, ToolException
from pydantic import BaseModel, Field

from codeteam.core.agent.workspace import PathOutsideWorkspace, Workspace
from codeteam.core.tools.files._hints import PATH_HINT
from codeteam.core.tools.files._internal._seen_files import SeenFiles
from codeteam.core.tools.files.read import is_read_header_line, is_read_summary_line
from codeteam.core.tools.files._internal.edit_utils import (
    EMPTY_OLD_STRING_MESSAGE,
    TextMatchError,
    TextNotFoundError,
    replace_text,
)

EDIT_TOOL_NAME = "edit"

TEXT_REPLACE_EDIT_DESCRIPTION = """Заменяет в существующем файле точный фрагмент old_string на new_string.
Новый файл создаётся инструментом write.

Удобен и приоритетен для небольших правок, а также когда надо заменить только блок в большом файле (чтобы не перегенерировать весь файл целиком).

Правила:
- Сначала прочитай файл инструментом read, иначе правка будет отклонена.
- Вывод read: первая строка — заголовок [путь], дальше строки в виде «номер:текст». Заголовок
  и номер с двоеточием — не текст файла: не включай их в old_string и new_string, а отступы после
  двоеточия сохраняй в точности.
- Если old_string не найден в файле, правка отклоняется.
- Если old_string найден в нескольких местах, правка отклоняется: добавь в old_string соседние строки,
  чтобы место стало единственным, или задай replace_all, чтобы заменить все вхождения.
- replace_all подходит для замены и переименования по всему файлу, например имени переменной."""


class TextReplaceEditArguments(BaseModel):
    """
    Аргументы edit с заменой текста.
    """

    file_path: str = Field(description = "путь файла, абсолютный или относительно папки проекта")
    old_string: str = Field(description = "точный фрагмент файла, который нужно заменить")
    new_string: str = Field(description = "текст на замену, отличный от old_string")
    replace_all: bool | None = Field(
        default = None,
        description = "заменить все вхождения old_string, по умолчанию нет",
    )


def build_edit_tool(*, workspace: Workspace, seen_files: SeenFiles) -> BaseTool:
    """
    Собирает инструмент edit с заменой текста для рабочего места вызова.

        workspace: рабочее место вызова.
        seen_files: файлы, которые видел вызов, общие с read и write.

    Возвращает: Инструмент edit.
    """

    def edit(*, file_path: str, old_string: str, new_string: str, replace_all: bool | None = None) -> str:
        """
        Заменяет фрагмент файла.

            file_path: путь от агента.
            old_string: фрагмент, который нужно заменить.
            new_string: текст на замену.
            replace_all: заменить все вхождения.

        Возвращает: Итог правки. Ошибку для агента поднимает ToolException.
        """
        try:
            path = workspace.resolve_writable(path = file_path)
        except PathOutsideWorkspace as error:
            raise ToolException(f"Ошибка: {error}") from error

        if not old_string:
            raise ToolException(f"Ошибка: {EMPTY_OLD_STRING_MESSAGE}")

        return _edit(
            workspace = workspace,
            seen_files = seen_files,
            path = path,
            old_string = old_string,
            new_string = new_string,
            replace_all = bool(replace_all),
        )

    return StructuredTool.from_function(
        func = edit,
        name = EDIT_TOOL_NAME,
        description = TEXT_REPLACE_EDIT_DESCRIPTION,
        args_schema = TextReplaceEditArguments,
        handle_tool_error = True,
    )


def _edit(
    *,
    workspace: Workspace,
    seen_files: SeenFiles,
    path: Path,
    old_string: str,
    new_string: str,
    replace_all: bool,
) -> str:
    """
    Заменяет фрагмент прочитанного файла и отмечает новое содержимое как виденное.

        workspace: рабочее место вызова.
        seen_files: файлы, которые видел вызов.
        path: абсолютный путь.
        old_string: фрагмент, который нужно заменить.
        new_string: текст на замену.
        replace_all: заменить все вхождения.

    Возвращает: Итог правки. Ошибку для агента поднимает ToolException.
    """
    shown_path = workspace.display_path(path = path)
    if path.is_dir():
        raise ToolException(f"Ошибка: {shown_path} — папка")

    if not path.is_file():
        raise ToolException(
            f"Ошибка: файл не найден: {shown_path}. {PATH_HINT} Новый файл создаётся инструментом write."
        )

    stale_reason = seen_files.stale_reason(path = path, shown_path = shown_path)
    if stale_reason is not None:
        raise ToolException(stale_reason)

    try:
        text = path.read_bytes().decode("utf-8")
    except UnicodeDecodeError:
        raise ToolException(f"Ошибка: файл {shown_path} не текстовый") from None

    is_crlf = "\r\n" in text
    try:
        new_text, service_lines = _replace(
            content = _to_lf(text = text),
            old_string = _to_lf(text = old_string),
            new_string = _to_lf(text = new_string),
            replace_all = replace_all,
        )
    except TextMatchError as error:
        raise ToolException(f"Ошибка в {shown_path}: {error}") from error

    if is_crlf:
        new_text = new_text.replace("\n", "\r\n")

    raw_content = new_text.encode("utf-8")
    path.write_bytes(raw_content)
    seen_files.remember(path = path, content = raw_content)

    answer = f"Правка применена: {shown_path}"
    if not service_lines:
        return answer

    return f"{answer}\n{_service_lines_note(service_lines = service_lines)}"


def _replace(*, content: str, old_string: str, new_string: str, replace_all: bool) -> tuple[str, list[str]]:
    """
    Заменяет фрагмент; если он не найден, ищет ещё раз без служебных строк read по краям old_string.

        content: текст файла с переводами строк \\n.
        old_string: фрагмент от модели.
        new_string: текст на замену.
        replace_all: заменить все вхождения.

    Возвращает: Текст после замены и отрезанные служебные строки. Отказ поднимает TextMatchError.
    """
    try:
        return replace_text(
            content = content,
            old_string = old_string,
            new_string = new_string,
            replace_all = replace_all,
        ), []
    except TextNotFoundError:
        trimmed, service_lines = _without_read_edges(text = old_string)
        if not service_lines:
            raise

    return replace_text(
        content = content,
        old_string = trimmed,
        new_string = new_string,
        replace_all = replace_all,
    ), service_lines


def _without_read_edges(*, text: str) -> tuple[str, list[str]]:
    """
    Отрезает служебные строки вывода read по краям: заголовок первой строкой, итоговую строку
    последней вместе с пустой строкой перед ней. Строки в середине не трогаются.

        text: old_string с переводами строк \\n.

    Возвращает: Текст без служебных строк и отрезанные строки; текст без изменений, если отрезать нечего
        или после отрезания ничего не остаётся.
    """
    lines = text.split("\n")
    service_lines: list[str] = []
    if len(lines) > 1 and is_read_header_line(line = lines[0]):
        service_lines.append(lines[0])
        lines = lines[1:]

    if len(lines) > 1 and is_read_summary_line(line = lines[-1]):
        service_lines.append(lines[-1])
        lines = lines[:-1]
        if len(lines) > 1 and not lines[-1].strip():
            lines = lines[:-1]

    trimmed = "\n".join(lines)
    if not trimmed.strip():
        return text, []

    return trimmed, service_lines


def _service_lines_note(*, service_lines: list[str]) -> str:
    """
    Собирает замечание об отрезанных служебных строках read.

        service_lines: отрезанные строки.

    Возвращает: Текст замечания для агента.
    """
    if len(service_lines) == 1:
        return (
            "Замечание: old_string в вызове инструмента содержала лишнюю служебную строку: "
            f"{service_lines[0]}"
        )

    listed = ", ".join(service_lines)
    return f"Замечание: old_string в вызове инструмента содержала лишние служебные строки: {listed}"


def _to_lf(*, text: str) -> str:
    """
    Заменяет переводы строк \\r\\n на \\n.

        text: текст.

    Возвращает: Текст с переводами строк \\n.
    """
    return text.replace("\r\n", "\n")

"""Инструмент агента edit с заменой текста: фрагмент old_string в файле заменяется на new_string.

Устройство перенесено из opencode (https://github.com/anomalyco/opencode,
packages/opencode/src/tool/edit.ts, коммит 9b4882db54), лицензия MIT; см. THIRD_PARTY_NOTICES.md.
"""

from pathlib import Path

from langchain_core.tools import BaseTool, StructuredTool, ToolException
from pydantic import BaseModel, Field

from codeteam.common.files import decode_text, number_lines
from codeteam.core.agent.workspace import PathOutsideWorkspace, Workspace
from codeteam.core.tools.files.common_prompts import (
    DIRECTORY_ERROR,
    FILE_PATH_DESCRIPTION,
    NOT_TEXT_REFUSAL,
    PATH_ACCESS_ERROR,
)
from codeteam.core.tools.files.edit_prompts import (
    EDIT_ERROR,
    EDIT_FILE_ERROR,
    EDIT_FILE_NOT_FOUND_ERROR,
    EDIT_NEW_STRING_DESCRIPTION,
    EDIT_OLD_STRING_DESCRIPTION,
    EDIT_REPLACE_ALL_DESCRIPTION,
    EDIT_RESULT,
    EDIT_SERVICE_LINE_NOTE,
    EDIT_SERVICE_LINES_NOTE,
    EMPTY_OLD_STRING_MESSAGE,
    SIMILAR_FRAGMENT_NOTE,
    TEXT_REPLACE_EDIT_DESCRIPTION,
)
from codeteam.core.tools.files._internal._seen_files import SeenFiles
from codeteam.core.tools.files.read import (
    READ_CHARACTER_LIMIT,
    READ_LINE_WIDTH,
    is_read_header_line,
    is_read_summary_line,
)
from codeteam.core.tools.files._internal.edit_utils import (
    TextMatchError,
    TextNotFoundError,
    replace_text,
    similar_fragment,
)

EDIT_TOOL_NAME = "edit"


class TextReplaceEditArguments(BaseModel):
    """
    Аргументы edit с заменой текста.
    """

    file_path: str = Field(description = FILE_PATH_DESCRIPTION)
    old_string: str = Field(description = EDIT_OLD_STRING_DESCRIPTION)
    new_string: str = Field(description = EDIT_NEW_STRING_DESCRIPTION)
    replace_all: bool | None = Field(default = None, description = EDIT_REPLACE_ALL_DESCRIPTION)


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
            raise ToolException(PATH_ACCESS_ERROR.format(error = error)) from error

        if not old_string:
            raise ToolException(EDIT_ERROR.format(message = EMPTY_OLD_STRING_MESSAGE))

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
        raise ToolException(DIRECTORY_ERROR.format(shown_path = shown_path))

    if not path.is_file():
        raise ToolException(EDIT_FILE_NOT_FOUND_ERROR.format(shown_path = shown_path))

    stale_reason = seen_files.stale_reason(path = path, shown_path = shown_path)
    if stale_reason is not None:
        raise ToolException(stale_reason)

    text = decode_text(content = path.read_bytes())
    if text is None:
        raise ToolException(NOT_TEXT_REFUSAL.format(shown_path = shown_path))

    is_crlf = "\r\n" in text
    content = _to_lf(text = text)
    normalized_old_string = _to_lf(text = old_string)
    try:
        new_text, service_lines = _replace(
            content = content,
            old_string = normalized_old_string,
            new_string = _to_lf(text = new_string),
            replace_all = replace_all,
        )
    except TextNotFoundError as error:
        note = _similar_fragment_note(content = content, old_string = normalized_old_string)
        message = EDIT_FILE_ERROR.format(shown_path = shown_path, message = error)
        if note is not None:
            message += f"\n\n{note}"
        raise ToolException(message) from error
    except TextMatchError as error:
        raise ToolException(EDIT_FILE_ERROR.format(shown_path = shown_path, message = error)) from error

    if is_crlf:
        new_text = new_text.replace("\n", "\r\n")

    raw_content = new_text.encode("utf-8")
    path.write_bytes(raw_content)
    seen_files.remember(path = path, content = raw_content)

    answer = EDIT_RESULT.format(shown_path = shown_path)
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


def _similar_fragment_note(*, content: str, old_string: str) -> str | None:
    """
    Собирает дополнение к отказу «не найден» с единственным похожим местом файла.

        content: текст файла с переводами строк \\n.
        old_string: фрагмент от модели с переводами строк \\n.

    Возвращает: Текст дополнения со строками места в виде вывода read; None, если похожего места
        нет или их несколько.
    """
    fragment = similar_fragment(content = content, old_string = old_string)
    if fragment is None:
        return None

    first_number, last_number = fragment
    page = number_lines(
        lines = content.split("\n"),
        offset = first_number,
        limit = last_number - first_number + 1,
        line_width = READ_LINE_WIDTH,
        character_limit = READ_CHARACTER_LIMIT,
    )

    return SIMILAR_FRAGMENT_NOTE.format(
        first_number = page.first_number,
        last_number = page.last_number,
        numbered_lines = "\n".join(page.lines),
    )


def _service_lines_note(*, service_lines: list[str]) -> str:
    """
    Собирает замечание об отрезанных служебных строках read.

        service_lines: отрезанные строки.

    Возвращает: Текст замечания для агента.
    """
    if len(service_lines) == 1:
        return EDIT_SERVICE_LINE_NOTE.format(line = service_lines[0])

    return EDIT_SERVICE_LINES_NOTE.format(lines = ", ".join(service_lines))


def _to_lf(*, text: str) -> str:
    """
    Заменяет переводы строк \\r\\n на \\n.

        text: текст.

    Возвращает: Текст с переводами строк \\n.
    """
    return text.replace("\r\n", "\n")

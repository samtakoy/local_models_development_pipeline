"""Хуки после шага инструментов: проверяют изменённые на шаге файлы черновика и дают агенту замечания."""

import re
from collections.abc import Callable
from pathlib import Path

from codeteam.core.agent.prompts import DUPLICATE_SECTION_NUMBER_REMARK, LATIN_SECTION_NAME_REMARK, \
    NOT_DRAFT_SECTION_REMARK
from codeteam.core.agent.workspace import DRAFT_SECTION_PATTERN, LATIN_DRAFT_SECTION_PATTERN

# Хук после шага: путь и текст изменённого файла черновика → замечание агенту или None.
StepHook = Callable[[Path, str], str | None]

# Проверка после шага: смотрит не на черновик, а на что угодно ещё (например, на проект) → замечание агенту или None.
StepCheck = Callable[[], str | None]

# Строка, открывающая блок с указанным языком: ``` и имя языка.
LANGUAGE_BLOCK_START_PATTERN = re.compile(r"^```[A-Za-z0-9_+#.-]+$")

# Граница блока: строка, начинающаяся с ```.
BLOCK_FENCE = "```"


def draft_section_hook(path: Path, text: str) -> str | None:
    """
    Проверяет имя изменённого файла черновика: раздел ли это, латиница ли в теме, нет ли рядом
    разделов с тем же номером.

        path: путь изменённого файла черновика.
        text: текст файла.

    Возвращает: Замечания агенту одной строкой или None, если имя раздела в порядке.
    """
    section_match = DRAFT_SECTION_PATTERN.match(path.name)
    if section_match is None:
        return NOT_DRAFT_SECTION_REMARK.format(file_name = path.name)

    remarks = []
    if not LATIN_DRAFT_SECTION_PATTERN.match(path.name):
        remarks.append(LATIN_SECTION_NAME_REMARK.format(file_name = path.name))

    same_number_names = _same_number_section_names(path = path, number = section_match.group(1))
    if same_number_names:
        remarks.append(
            DUPLICATE_SECTION_NUMBER_REMARK.format(file_name = path.name, other_names = ", ".join(same_number_names))
        )

    return "\n".join(remarks) if remarks else None


def code_block_hook(*, max_lines: int, remark: str, skip_file_names: tuple[str, ...]) -> StepHook:
    """
    Собирает хук, который замечает в файле черновика блоки с указанным языком длиннее предела.

        max_lines: наибольшее число строк внутри одного блока с указанным языком.
        remark: текст замечания агенту; поля {file_name} и {max_lines} в нём заменяются
            именем файла и пределом.
        skip_file_names: имена файлов черновика, которые хук не проверяет.

    Возвращает: Хук после шага.
    """
    def hook(path: Path, text: str) -> str | None:
        """Находит самый длинный блок с указанным языком и сравнивает его с пределом."""
        if path.name in skip_file_names:
            return None

        longest_block = max(_language_block_lengths(text = text), default = 0)
        if longest_block <= max_lines:
            return None

        return remark.format(file_name = path.name, max_lines = max_lines)

    return hook


def _same_number_section_names(*, path: Path, number: str) -> list[str]:
    """
    Находит в папке раздела другие разделы с тем же номером.

        path: путь раздела черновика.
        number: номер раздела, как он записан в имени.

    Возвращает: Имена других разделов с тем же номером по порядку имён.
    """
    names = []
    for sibling in sorted(path.parent.glob("*.md")):
        sibling_match = DRAFT_SECTION_PATTERN.match(sibling.name)
        if sibling != path and sibling_match is not None and sibling_match.group(1) == number:
            names.append(sibling.name)

    return names


def _language_block_lengths(*, text: str) -> list[int]:
    """
    Считает строки внутри блоков с указанным языком; блоки без языка пропускает.

        text: текст файла.

    Возвращает: Число строк внутри каждого блока с указанным языком по порядку.
    """
    lengths = []
    inside_block = False
    is_language_block = False
    line_count = 0
    for line in text.splitlines():
        stripped_line = line.strip()
        if not inside_block:
            if stripped_line.startswith(BLOCK_FENCE):
                inside_block = True
                is_language_block = LANGUAGE_BLOCK_START_PATTERN.match(stripped_line) is not None
                line_count = 0
            continue

        if stripped_line == BLOCK_FENCE:
            if is_language_block:
                lengths.append(line_count)
            inside_block = False
            continue

        line_count += 1

    if inside_block and is_language_block:
        lengths.append(line_count)

    return lengths

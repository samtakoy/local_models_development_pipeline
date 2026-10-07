"""Хуки после шага инструментов: проверяют изменённые на шаге файлы черновика и дают агенту замечания."""

import re
from collections.abc import Callable
from pathlib import Path

from codeteam.core.agent.prompts import CODE_BLOCK_REMARK

# Хук после шага: путь и текст изменённого файла черновика → замечание агенту или None.
StepHook = Callable[[Path, str], str | None]

# Строка, открывающая блок с указанным языком: ``` и имя языка.
LANGUAGE_BLOCK_START_PATTERN = re.compile(r"^```[A-Za-z0-9_+#.-]+$")

# Граница блока: строка, начинающаяся с ```.
BLOCK_FENCE = "```"


def code_block_hook(*, max_lines: int) -> StepHook:
    """
    Собирает хук, который замечает в файле черновика блоки с указанным языком длиннее предела.

        max_lines: наибольшее число строк внутри одного блока с указанным языком.

    Возвращает: Хук после шага.
    """
    def hook(path: Path, text: str) -> str | None:
        """Находит самый длинный блок с указанным языком и сравнивает его с пределом."""
        longest_block = max(_language_block_lengths(text = text), default = 0)
        if longest_block <= max_lines:
            return None

        return CODE_BLOCK_REMARK.format(file_name = path.name, max_lines = max_lines)

    return hook


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

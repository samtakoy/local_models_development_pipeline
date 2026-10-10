"""Тесты хука длинных блоков кода: замечание называет строки всех блоков с языком длиннее предела."""

from pathlib import Path

from codeteam.core.agent.prompts import CODE_BLOCK_LINES
from codeteam.core.agent.step_hooks import code_block_hook

# Предел строк в блоке для теста.
MAX_LINES = 3

# Замечание теста: поля хука через разделитель.
REMARK = "{file_name}|{max_lines}|{long_blocks}"


def _block(*, language: str, line_count: int) -> list[str]:
    """
    Собирает строки блока кода.

        language: язык блока; пустая строка - блок без языка.
        line_count: число строк внутри блока.

    Возвращает: Строки блока вместе с оградами.
    """
    return [f"```{language}", *(f"line {number}" for number in range(line_count)), "```"]


def _lines(*, first_line: int, last_line: int) -> str:
    """
    Показывает строки блока так, как их называет замечание.

        first_line: строка открывающей ограды.
        last_line: строка закрывающей ограды.

    Возвращает: Строки блока для замечания.
    """
    return CODE_BLOCK_LINES.format(first_line = first_line, last_line = last_line)


def test_all_long_blocks_are_named() -> None:
    """
    Замечание называет оба длинных блока с языком; короткий блок и длинный блок без языка не попадают.
    """
    lines = [
        "# План",                                    # 1
        *_block(language = "python", line_count = 5),  # 2-8
        *_block(language = "python", line_count = 2),  # 9-12
        *_block(language = "", line_count = 6),        # 13-20
        *_block(language = "html", line_count = 4),    # 21-26
    ]
    hook = code_block_hook(max_lines = MAX_LINES, remark = REMARK, skip_file_names = ())

    remark = hook(Path("300_plan.md"), "\n".join(lines))

    assert remark == f"300_plan.md|3|{_lines(first_line = 2, last_line = 8)}; {_lines(first_line = 21, last_line = 26)}"


def test_short_blocks_give_no_remark() -> None:
    """
    Без блоков длиннее предела замечания нет.
    """
    hook = code_block_hook(max_lines = MAX_LINES, remark = REMARK, skip_file_names = ())

    assert hook(Path("300_plan.md"), "\n".join(_block(language = "python", line_count = 3))) is None


def test_unclosed_block_ends_at_last_line() -> None:
    """
    Незакрытый длинный блок называется до последней строки файла.
    """
    lines = ["# План", "```python", "a", "b", "c", "d"]
    hook = code_block_hook(max_lines = MAX_LINES, remark = REMARK, skip_file_names = ())

    assert hook(Path("300_plan.md"), "\n".join(lines)) == f"300_plan.md|3|{_lines(first_line = 2, last_line = 6)}"

"""Тесты хука длинных блоков кода: замечание называет строки всех блоков с языком длиннее предела."""

from pathlib import Path

from codeteam.core.agent.prompts import CODE_BLOCK_LINES
from codeteam.core.agent.statistics import WORK_PHASE
from codeteam.core.agent.step_hooks import StepContext, code_block_hook

# Предел строк в блоке для теста.
MAX_LINES = 3

# Замечание теста: поля хука через разделитель.
REMARK = "{file_name}|{max_lines}|{long_blocks}"

# Папка, за которой следит хук, относительно личной папки.
FOLDER = Path("draft")


def _remark(*, private_dir: Path, text: str) -> str | None:
    """
    Записывает файл плана в папку хука и запускает хук на шаге, изменившем этот файл.

        private_dir: личная папка агента.
        text: текст файла.

    Возвращает: Замечание хука или None.
    """
    plan_file = private_dir / FOLDER / "300_plan.md"
    plan_file.parent.mkdir(parents = True, exist_ok = True)
    plan_file.write_text(text, encoding = "utf-8")
    hook = code_block_hook(folder = FOLDER, max_lines = MAX_LINES, remark = REMARK, skip_file_names = ())

    context = StepContext(
        project_dir = private_dir,
        private_dir = private_dir,
        phase = WORK_PHASE,
        changed_files = (plan_file,),
        refusals = (),
    )

    return hook(context)


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


def test_all_long_blocks_are_named(tmp_path: Path) -> None:
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
    remark = _remark(private_dir = tmp_path, text = "\n".join(lines))

    assert remark == f"300_plan.md|3|{_lines(first_line = 2, last_line = 8)}; {_lines(first_line = 21, last_line = 26)}"


def test_short_blocks_give_no_remark(tmp_path: Path) -> None:
    """
    Без блоков длиннее предела замечания нет.
    """
    assert _remark(private_dir = tmp_path, text = "\n".join(_block(language = "python", line_count = 3))) is None


def test_unclosed_block_ends_at_last_line(tmp_path: Path) -> None:
    """
    Незакрытый длинный блок называется до последней строки файла.
    """
    lines = ["# План", "```python", "a", "b", "c", "d"]
    remark = _remark(private_dir = tmp_path, text = "\n".join(lines))

    assert remark == f"300_plan.md|3|{_lines(first_line = 2, last_line = 6)}"

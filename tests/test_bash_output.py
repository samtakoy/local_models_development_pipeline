"""Тесты обрезки вывода bash: короткий вывод приходит целиком, длинный сохраняется в файл, агенту приходят
последние целые строки с номерами строк и путём к полному выводу."""

import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from langchain_core.tools import BaseTool

from codeteam.common.shell import CommandHost, ShellProcesses
from codeteam.core.agent.workspace import Workspace
from codeteam.core.tools.shell import build_bash_tool
from codeteam.core.tools.shell.bash import BASH_OUTPUT_LIMIT

# Путь к файлу полного вывода в пометке об обрезке.
FULL_OUTPUT_PATH_PATTERN = re.compile(r"\S+\.log")


@pytest.fixture
def workspace(tmp_path: Path) -> Workspace:
    """
    Рабочее место в папке теста.

        tmp_path: временная папка теста.

    Возвращает: Рабочее место.
    """
    return Workspace(
        project_dir = tmp_path,
        private_dir = tmp_path / ".ct-work" / "agent",
        input_dirs = (),
        readable_dirs = (tmp_path,),
        writable_dirs = (tmp_path,),
        refusal_hint = None,
    )


@pytest.fixture
def bash(workspace: Workspace) -> Iterator[BaseTool]:
    """
    Инструмент bash на рабочем месте в папке теста.

        workspace: рабочее место теста.

    Возвращает: Инструмент bash; хозяин команд и фоновые процессы снимаются после теста.
    """
    processes = ShellProcesses()
    host = CommandHost(write_roots = workspace.writable_dirs, processes = processes)
    yield build_bash_tool(workspace = workspace, processes = processes, host = host)
    processes.kill_all()
    host.close()


def _split_answer(*, answer: str, workspace: Workspace) -> tuple[str, Path, list[str]]:
    """
    Делит ответ bash с обрезанным выводом на пометку, файл полного вывода и показанные строки.

        answer: ответ bash.
        workspace: рабочее место теста.

    Возвращает: Строку пометки без пути к файлу, путь файла полного вывода и показанные строки вывода.
    """
    answer_lines = answer.split("\n")
    notice_index = next(index for index, line in enumerate(answer_lines) if FULL_OUTPUT_PATH_PATTERN.search(line))
    notice = answer_lines[notice_index]
    shown_path = FULL_OUTPUT_PATH_PATTERN.search(notice).group(0)

    return notice.replace(shown_path, ""), workspace.project_dir / shown_path, answer_lines[notice_index + 1:]


def test_short_output_is_returned_whole(bash: BaseTool, workspace: Workspace) -> None:
    """
    Короткий вывод приходит целиком, файл полного вывода не создаётся.
    """
    answer = bash.invoke({"command": "echo привет"})

    assert answer == "Код возврата: 0\nпривет\n"
    assert not (workspace.project_dir / "tmp_check" / "bash_output").exists()


def test_long_output_shows_last_whole_lines_and_saves_full_output(bash: BaseTool, workspace: Workspace) -> None:
    """
    Длинный вывод: полный вывод лежит в файле, агенту приходят последние целые строки в пределах
    BASH_OUTPUT_LIMIT, а пометка называет номер первой показанной строки, последней и число строк.
    """
    full_output = "".join(f"строка {number}\n" for number in range(1, 3001))

    answer = bash.invoke({"command": "python3 -c \"for number in range(1, 3001): print('строка', number)\""})

    notice, full_output_path, shown_lines = _split_answer(answer = answer, workspace = workspace)
    assert full_output_path.read_text(encoding = "utf-8") == full_output

    full_lines = full_output.split("\n")[:-1]
    assert shown_lines == full_lines[-len(shown_lines):]
    assert len("\n".join(shown_lines)) <= BASH_OUTPUT_LIMIT

    first_shown = len(full_lines) - len(shown_lines) + 1
    notice_numbers = [int(number) for number in re.findall(r"\d+", notice)]
    assert notice_numbers == [first_shown, 3000, 3000], notice


def test_single_long_line_shows_its_end(bash: BaseTool, workspace: Workspace) -> None:
    """
    Одна строка длиннее предела: агенту приходят последние BASH_OUTPUT_LIMIT символов этой строки,
    полный вывод лежит в файле.
    """
    long_line = "a" * 15000 + "конец"

    answer = bash.invoke({"command": "python3 -c \"print('a' * 15000 + 'конец')\""})

    notice, full_output_path, shown_lines = _split_answer(answer = answer, workspace = workspace)
    assert full_output_path.read_text(encoding = "utf-8") == long_line + "\n"
    assert shown_lines == [long_line[-BASH_OUTPUT_LIMIT:]]

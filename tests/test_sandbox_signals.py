"""Тесты песочницы macOS: сигналы доходят только до процессов того же вызова команды."""

import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from codeteam.common.shell import CommandResult, ReadRestrictions, run_command
from codeteam.common.shell.processes import kill_process_group
from tests.shell_helpers import is_process_alive

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason = "песочница есть только на macOS")

# Предел времени команды в тестах, секунды.
COMMAND_TIMEOUT_SECONDS = 20


def _run(*, command: str, work_dir: Path) -> CommandResult:
    """
    Запускает команду под песочницей с записью в папку теста.

        command: команда bash.
        work_dir: папка запуска и записи.

    Возвращает: Итог команды.
    """
    return run_command(
        command = command,
        working_dir = str(work_dir),
        timeout_seconds = COMMAND_TIMEOUT_SECONDS,
        write_roots = (work_dir,),
        read_restrictions = ReadRestrictions(root = work_dir, closed_file_names = (), closed_dirs = (), open_dirs = ()),
    )


@pytest.fixture
def outside_process() -> Iterator[subprocess.Popen]:
    """
    Процесс вне песочницы.

    Возвращает: Работающий процесс sleep; снимается после теста.
    """
    process = subprocess.Popen(["sleep", "300"])
    yield process
    process.kill()
    process.wait()


def test_kill_outside_process_is_denied(tmp_path: Path, outside_process: subprocess.Popen) -> None:
    """
    kill процесса вне песочницы получает отказ, процесс продолжает работать.
    """
    result = _run(command = f"kill {outside_process.pid}", work_dir = tmp_path)

    assert result.exit_code == 1
    assert "Operation not permitted" in result.output
    assert outside_process.poll() is None


def test_pkill_outside_process_is_denied(tmp_path: Path, outside_process: subprocess.Popen) -> None:
    """
    pkill по команде процесса вне песочницы получает отказ, процесс продолжает работать.
    """
    result = _run(command = "pkill -f 'sleep 300'", work_dir = tmp_path)

    assert "Operation not permitted" in result.output
    assert outside_process.poll() is None


def test_kill_own_process_in_same_call_works(tmp_path: Path) -> None:
    """
    kill фонового процесса, запущенного в том же вызове, останавливает его.
    """
    result = _run(command = "sleep 100 & pid=$!; kill $pid; wait $pid", work_dir = tmp_path)

    # 143 = 128 + SIGTERM: процесс остановлен сигналом
    assert result.exit_code == 143


def test_kill_own_process_from_previous_call_is_denied(tmp_path: Path) -> None:
    """
    kill фонового процесса из прошлого вызова получает отказ.
    """
    started = _run(command = "sleep 100 > /dev/null 2>&1 & echo $!", work_dir = tmp_path)
    background_pid = int(started.output.strip())
    try:
        result = _run(command = f"kill {background_pid}", work_dir = tmp_path)

        assert "Operation not permitted" in result.output
        assert is_process_alive(process_id = background_pid)
    finally:
        kill_process_group(process_group_id = started.process_group_id)

"""Тесты учёта групп процессов: группа из одних завершённых процессов не роняет учёт."""

import os
import signal
import subprocess
from collections.abc import Iterator

import pytest

from codeteam.common.shell import ShellProcesses
from codeteam.common.shell.processes import kill_process_group
from tests.shell_helpers import wait_process_gone


@pytest.fixture
def zombie_group_id() -> Iterator[int]:
    """
    Группа, в которой остался только завершённый процесс, ещё не убранный родителем.

    Возвращает: Номер группы; процесс убирается после теста.
    """
    process = subprocess.Popen(["sleep", "100"], start_new_session = True)
    os.kill(process.pid, signal.SIGKILL)
    # процесс завершён, но не убран: родитель (тест) ещё не вызвал wait
    os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOWAIT)
    yield process.pid
    process.wait()


def test_remember_zombie_group_does_not_raise(zombie_group_id: int) -> None:
    """
    Запоминание группы из завершённого процесса проходит без ошибки, снятие всех групп тоже.
    """
    processes = ShellProcesses()

    processes.remember(process_group_id = zombie_group_id)
    processes.kill_all()


def test_kill_zombie_group_does_not_raise(zombie_group_id: int) -> None:
    """
    Снятие группы из завершённого процесса проходит без ошибки.
    """
    kill_process_group(process_group_id = zombie_group_id)


def test_kill_process_group_stops_live_group() -> None:
    """
    Снятие живой группы останавливает её процесс.
    """
    process = subprocess.Popen(["sleep", "100"], start_new_session = True)

    kill_process_group(process_group_id = process.pid)

    assert process.wait(timeout = 5) == -signal.SIGKILL
    assert wait_process_gone(process_id = process.pid)

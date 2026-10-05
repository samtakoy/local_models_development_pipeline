"""Тесты инструмента stop_process: остановка фоновых процессов, запущенных агентом через bash."""

import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from langchain_core.tools import BaseTool

from codeteam.common.shell import ShellProcesses
from codeteam.core.agent.workspace import Workspace
from codeteam.core.tools.shell import build_bash_tool, build_stop_process_tool
from tests.shell_helpers import is_process_alive, wait_process_gone


@dataclass(frozen = True)
class AgentShell:
    """
    Инструменты оболочки одного агента с общим учётом процессов.

        bash: инструмент bash.
        stop_process: инструмент stop_process.
    """

    bash: BaseTool
    stop_process: BaseTool

    def start(self, *, command: str) -> int:
        """
        Запускает фоновую команду через bash.

            command: команда bash.

        Возвращает: Номер фонового процесса.
        """
        output = self.bash.invoke({"command": f"{command} > /dev/null 2>&1 & echo $!"})

        return int(output.splitlines()[-1])


@pytest.fixture
def agent_shell(tmp_path: Path) -> Iterator[AgentShell]:
    """
    Инструменты оболочки агента на рабочем месте в папке теста.

    Возвращает: Инструменты bash и stop_process; фоновые процессы снимаются после теста.
    """
    workspace = Workspace(
        project_dir = tmp_path,
        private_dir = tmp_path / ".ct-work" / "agent",
        input_dirs = (),
        readable_dirs = (tmp_path,),
        writable_dirs = (tmp_path,),
        refusal_hint = None,
    )
    processes = ShellProcesses()
    yield AgentShell(
        bash = build_bash_tool(workspace = workspace, processes = processes),
        stop_process = build_stop_process_tool(processes = processes),
    )
    processes.kill_all()


def test_stop_by_pid_stops_process_and_its_children(agent_shell: AgentShell) -> None:
    """
    Остановка по номеру снимает и сам процесс, и запущенный им дочерний: как uv run и его python.
    """
    wrapper_pid = agent_shell.start(command = "bash -c 'sleep 101; true'")
    child_listing = subprocess.run(["pgrep", "-P", str(wrapper_pid)], capture_output = True, text = True)
    child_pid = int(child_listing.stdout.split()[0])

    answer = agent_shell.stop_process.invoke({"pid": wrapper_pid})

    assert answer == f"Остановлен процесс {wrapper_pid} и всё, что запущено с ним в том же вызове bash."
    assert wait_process_gone(process_id = wrapper_pid)
    assert wait_process_gone(process_id = child_pid)


def test_stop_by_pid_accepts_string_number(agent_shell: AgentShell) -> None:
    """
    Номер строкой тоже принимается: модель иногда передаёт числа строками.
    """
    process_id = agent_shell.start(command = "sleep 102")

    answer = agent_shell.stop_process.invoke({"pid": str(process_id)})

    assert answer.startswith(f"Остановлен процесс {process_id}")
    assert wait_process_gone(process_id = process_id)


def test_stop_outside_pid_is_refused_with_own_processes(agent_shell: AgentShell) -> None:
    """
    Номер чужого процесса получает отказ со списком своих фоновых процессов; чужой процесс работает.
    """
    own_process_id = agent_shell.start(command = "sleep 103")
    outside_process = subprocess.Popen(["sleep", "300"])
    try:
        answer = agent_shell.stop_process.invoke({"pid": outside_process.pid})

        assert answer.startswith(f"Ошибка: процесса {outside_process.pid} нет среди твоих")
        assert f"- {own_process_id}: sleep 103" in answer
        assert outside_process.poll() is None
        assert is_process_alive(process_id = own_process_id)
    finally:
        outside_process.kill()
        outside_process.wait()


def test_stop_without_pid_stops_all_own_processes(agent_shell: AgentShell) -> None:
    """
    Без номера останавливаются все свои фоновые процессы, в ответе их список.
    """
    first_process_id = agent_shell.start(command = "sleep 104")
    second_process_id = agent_shell.start(command = "sleep 105")

    answer = agent_shell.stop_process.invoke({})

    assert answer == (
        "Остановлены процессы:\n"
        f"- {first_process_id}: sleep 104\n"
        f"- {second_process_id}: sleep 105"
    )
    assert wait_process_gone(process_id = first_process_id)
    assert wait_process_gone(process_id = second_process_id)


def test_stop_without_processes(agent_shell: AgentShell) -> None:
    """
    Когда своих фоновых процессов нет, ответы об этом говорят прямо.
    """
    assert agent_shell.stop_process.invoke({}) == "Работающих фоновых процессов не было."
    assert agent_shell.stop_process.invoke({"pid": 1}) == (
        "Ошибка: процесса 1 нет среди твоих работающих фоновых процессов. "
        "Работающих фоновых процессов у тебя нет."
    )

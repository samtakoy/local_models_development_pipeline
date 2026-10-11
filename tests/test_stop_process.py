"""Тесты инструмента stop_process: остановка фоновых процессов, запущенных агентом через bash."""

import subprocess
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from langchain_core.tools import BaseTool

from codeteam.common.shell import CommandHost, ShellProcesses
from codeteam.core.agent.workspace import Workspace
from codeteam.core.tools.shell import build_bash_tool, build_stop_process_tool
from tests.shell_helpers import error_page_server_command, free_port, is_process_alive, requires_sandbox, \
    wait_port_open, wait_process_gone

# Окончание фоновой команды агента: вывод в никуда, номер фонового процесса в ответе bash.
BACKGROUND_SUFFIX = " > /dev/null 2>&1 & echo $!"

# Сколько ждать запуска команды в соседнем потоке, секунды.
COMMAND_START_TIMEOUT_SECONDS = 10


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
        output = self.bash.invoke({"command": command + BACKGROUND_SUFFIX})

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
    )
    processes = ShellProcesses()
    host = CommandHost(write_roots = workspace.writable_dirs, processes = processes)
    yield AgentShell(
        bash = build_bash_tool(workspace = workspace, processes = processes, host = host),
        stop_process = build_stop_process_tool(processes = processes),
    )
    processes.kill_all()
    host.close()


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
        assert f"- {own_process_id}: sleep 103{BACKGROUND_SUFFIX}" in answer
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
        f"- {first_process_id}: sleep 104{BACKGROUND_SUFFIX}\n"
        f"- {second_process_id}: sleep 105{BACKGROUND_SUFFIX}"
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


@requires_sandbox
def test_detached_process_is_listed_and_stopped(agent_shell: AgentShell) -> None:
    """
    Процесс, ушедший в фон в новой сессии, есть в списке своих процессов и останавливается по номеру.
    """
    port = free_port()
    output = agent_shell.bash.invoke({"command": error_page_server_command(port = port, detached = True)})
    process_id = int(output.splitlines()[-1])
    assert wait_port_open(port = port)

    refusal = agent_shell.stop_process.invoke({"pid": 1})
    agent_shell.stop_process.invoke({"pid": process_id})

    assert f"- {process_id}: " in refusal
    assert wait_process_gone(process_id = process_id)


@requires_sandbox
def test_stop_without_pid_keeps_running_command(agent_shell: AgentShell, tmp_path: Path) -> None:
    """
    Остановка всех фоновых процессов не обрывает команду, результат которой агент сейчас ждёт.
    """
    started_file = tmp_path / "started"
    answers: list[str] = []
    command = threading.Thread(target = lambda: answers.append(
        agent_shell.bash.invoke({"command": f"touch {started_file}; sleep 2; echo готово"})
    ))
    command.start()
    deadline = time.monotonic() + COMMAND_START_TIMEOUT_SECONDS
    while not started_file.exists() and time.monotonic() < deadline:
        time.sleep(0.05)

    agent_shell.stop_process.invoke({})
    command.join()

    assert started_file.exists()
    assert "готово" in answers[0]

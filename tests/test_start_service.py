"""Тесты инструмента start_service: повторный запуск на том же порту заменяет прежнюю службу."""

import os
import re
import socket
from collections.abc import Iterator
from pathlib import Path

import pytest
from langchain_core.tools import BaseTool

from codeteam.common.shell import CommandHost, ShellProcesses
from codeteam.core.agent.workspace import Workspace
from codeteam.core.tools.shell import build_start_service_tool
from tests.shell_helpers import wait_process_group_gone

# Номер процесса службы в ответе start_service.
SERVICE_PROCESS_PATTERN = re.compile(r"Служба готова: процесс (\d+)")


@pytest.fixture
def processes() -> Iterator[ShellProcesses]:
    """
    Учёт фоновых процессов теста; после теста все процессы снимаются.

    Возвращает: Учёт фоновых процессов.
    """
    shell_processes = ShellProcesses()
    yield shell_processes
    shell_processes.kill_all()


@pytest.fixture
def start_service(tmp_path: Path, processes: ShellProcesses) -> Iterator[BaseTool]:
    """
    Инструмент start_service на рабочем месте в папке теста.

        tmp_path: временная папка теста.
        processes: учёт фоновых процессов теста.

    Возвращает: Инструмент start_service; хозяин команд останавливается после теста.
    """
    workspace = Workspace(
        project_dir = tmp_path,
        private_dir = tmp_path / ".ct-work" / "agent",
        input_dirs = (),
        readable_dirs = (tmp_path,),
        writable_dirs = (tmp_path,),
        refusal_hint = None,
    )

    host = CommandHost(write_roots = workspace.writable_dirs, processes = processes)
    yield build_start_service_tool(workspace = workspace, processes = processes, host = host)
    host.close()


def _free_port() -> int:
    """
    Находит свободный порт на 127.0.0.1.

    Возвращает: Номер порта.
    """
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _start(*, start_service: BaseTool, port: int) -> str:
    """
    Запускает простой веб-сервер на порту.

        start_service: инструмент start_service.
        port: порт сервера.

    Возвращает: Ответ start_service.
    """
    return start_service.invoke({
        "command": f"python3 -m http.server {port} --bind 127.0.0.1",
        "port": port,
    })


def _is_alive(*, process_group_id: int) -> bool:
    """
    Проверяет, работает ли служба: жив ли хоть один процесс её группы.

        process_group_id: номер группы процессов службы из ответа start_service.

    Возвращает: True, если в группе есть процесс.
    """
    try:
        os.killpg(process_group_id, 0)
    except ProcessLookupError:
        return False

    return True


def test_restart_on_same_port_replaces_previous_service(start_service: BaseTool) -> None:
    """
    Второй запуск на том же порту останавливает прежнюю службу и запускает новую.
    """
    port = _free_port()

    first = _start(start_service = start_service, port = port)
    second = _start(start_service = start_service, port = port)

    first_match = SERVICE_PROCESS_PATTERN.search(first)
    second_match = SERVICE_PROCESS_PATTERN.search(second)
    assert first_match is not None and second_match is not None, f"{first}\n{second}"
    assert not _is_alive(process_group_id = int(first_match.group(1)))
    assert _is_alive(process_group_id = int(second_match.group(1)))


def test_port_busy_by_other_program_is_refused(start_service: BaseTool) -> None:
    """
    Порт, занятый не службой этого инструмента, — отказ, служба не запускается.
    """
    with socket.socket() as other_program:
        other_program.bind(("127.0.0.1", 0))
        other_program.listen()
        port = other_program.getsockname()[1]

        result = _start(start_service = start_service, port = port)

    assert result.startswith(f"Ошибка: порт {port} уже занят другой программой")


def test_command_with_ampersand_starts_service(start_service: BaseTool, processes: ShellProcesses) -> None:
    """
    Команда с & в фоне и внутри кавычек запускает службу; её останавливают по номеру из ответа.
    """
    port = _free_port()

    result = start_service.invoke({
        "command": f'python3 -m http.server {port} --bind 127.0.0.1 & echo "a&b"',
        "port": port,
    })

    match = SERVICE_PROCESS_PATTERN.search(result)
    assert match is not None, result
    assert processes.kill_group_of(process_id = int(match.group(1)))
    assert wait_process_group_gone(process_group_id = int(match.group(1)))

"""Тесты инструмента start_service: повторный запуск на том же порту заменяет прежнюю службу,
номер службы из ответа совпадает с номером в списке stop_process и останавливает службу."""

import re
import socket
from collections.abc import Iterator
from pathlib import Path

import pytest
from langchain_core.tools import BaseTool

from codeteam.common.shell import CommandHost, ShellProcesses
from codeteam.core.agent.workspace import Workspace
from codeteam.core.tools.shell import build_bash_tool, build_start_service_tool, build_stop_process_tool
from tests.shell_helpers import is_process_alive, wait_port_open, wait_process_gone

# Номер процесса службы в ответе start_service.
SERVICE_PROCESS_PATTERN = re.compile(r"Служба готова: процесс (\d+)")

# Номер процесса в готовом вызове stop_process из ответа start_service.
STOP_CALL_PATTERN = re.compile(r"stop_process\(pid = (\d+)\)")


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
def host(workspace: Workspace, processes: ShellProcesses) -> Iterator[CommandHost]:
    """
    Хозяин команд агента, общий для bash и start_service.

        workspace: рабочее место теста.
        processes: учёт фоновых процессов теста.

    Возвращает: Хозяин команд; останавливается после теста.
    """
    command_host = CommandHost(write_roots = workspace.writable_dirs, processes = processes)
    yield command_host
    command_host.close()


@pytest.fixture
def start_service(workspace: Workspace, processes: ShellProcesses, host: CommandHost) -> BaseTool:
    """
    Инструмент start_service на рабочем месте в папке теста.

        workspace: рабочее место теста.
        processes: учёт фоновых процессов теста.
        host: хозяин команд агента.

    Возвращает: Инструмент start_service.
    """
    return build_start_service_tool(workspace = workspace, processes = processes, host = host)


@pytest.fixture
def bash(workspace: Workspace, processes: ShellProcesses, host: CommandHost) -> BaseTool:
    """
    Инструмент bash с тем же учётом процессов и хозяином команд, что у start_service.

        workspace: рабочее место теста.
        processes: учёт фоновых процессов теста.
        host: хозяин команд агента.

    Возвращает: Инструмент bash.
    """
    return build_bash_tool(workspace = workspace, processes = processes, host = host)


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


@pytest.fixture
def stop_process(processes: ShellProcesses) -> BaseTool:
    """
    Инструмент stop_process с тем же учётом процессов, что у start_service.

        processes: учёт фоновых процессов теста.

    Возвращает: Инструмент stop_process.
    """
    return build_stop_process_tool(processes = processes)


def _service_process_id(*, answer: str) -> int:
    """
    Берёт номер службы из ответа start_service.

        answer: ответ start_service.

    Возвращает: Номер процесса службы.
    """
    match = SERVICE_PROCESS_PATTERN.search(answer)
    assert match is not None, answer

    return int(match.group(1))


def _stop_process_id(*, answer: str) -> int:
    """
    Берёт номер процесса из вызова stop_process в ответе start_service.

        answer: ответ start_service.

    Возвращает: Номер процесса службы.
    """
    match = STOP_CALL_PATTERN.search(answer)
    assert match is not None, answer

    return int(match.group(1))


def test_restart_on_same_port_replaces_previous_service(start_service: BaseTool) -> None:
    """
    Второй запуск на том же порту останавливает прежнюю службу и запускает новую.
    """
    port = _free_port()

    first = _start(start_service = start_service, port = port)
    second = _start(start_service = start_service, port = port)

    assert wait_process_gone(process_id = _service_process_id(answer = first))
    assert is_process_alive(process_id = _service_process_id(answer = second))


def test_own_bash_process_on_port_is_stopped_and_service_started(bash: BaseTool, start_service: BaseTool) -> None:
    """
    Порт занят сервером, который агент запустил через bash: start_service останавливает его, запускает
    службу и называет в ответе номер остановленного процесса.
    """
    port = _free_port()
    bash_answer = bash.invoke({"command": f"python3 -m http.server {port} --bind 127.0.0.1 > /dev/null 2>&1 & echo $!"})
    bash_process_id = int(bash_answer.split()[-1])
    assert wait_port_open(port = port)

    answer = _start(start_service = start_service, port = port)

    assert str(bash_process_id) in answer.split("\n")[0], answer
    assert wait_process_gone(process_id = bash_process_id)
    assert is_process_alive(process_id = _service_process_id(answer = answer))


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

    process_id = _service_process_id(answer = result)
    assert processes.kill_group_of(process_id = process_id)
    assert wait_process_gone(process_id = process_id)


def test_stop_all_lists_service_by_agent_command(
    start_service: BaseTool,
    stop_process: BaseTool,
    tmp_path: Path,
) -> None:
    """
    Список stop_process показывает службу одной строкой: номер из ответа start_service и команду агента
    без служебной обёртки; номер — работающий процесс службы.
    """
    port = _free_port()
    command = f"cd {tmp_path} && python3 -m http.server {port} --bind 127.0.0.1"

    process_id = _service_process_id(answer = start_service.invoke({"command": command, "port": port}))
    assert is_process_alive(process_id = process_id)

    answer = stop_process.invoke({})

    assert answer == f"Остановлены процессы:\n- {process_id}: {command}"
    assert wait_process_gone(process_id = process_id)
    assert stop_process.invoke({}) == "Работающих фоновых процессов не было."


def test_stop_by_service_number(start_service: BaseTool, stop_process: BaseTool) -> None:
    """
    Номер из ответа start_service останавливает службу.
    """
    port = _free_port()
    process_id = _service_process_id(answer = _start(start_service = start_service, port = port))

    answer = stop_process.invoke({"pid": process_id})

    assert answer == f"Остановлен процесс {process_id} и всё, что запущено с ним в том же вызове bash."
    assert wait_process_gone(process_id = process_id)


def test_unknown_number_refusal_lists_service(start_service: BaseTool, stop_process: BaseTool) -> None:
    """
    Отказ на чужой номер перечисляет службу номером из ответа start_service и командой агента.
    """
    port = _free_port()
    command = f"python3 -m http.server {port} --bind 127.0.0.1"
    process_id = _service_process_id(answer = start_service.invoke({"command": command, "port": port}))

    answer = stop_process.invoke({"pid": 1})

    assert answer == (
        "Ошибка: процесса 1 нет среди твоих работающих фоновых процессов. Твои фоновые процессы:\n"
        f"- {process_id}: {command}\n"
        "Вызови stop_process с номером из списка или без pid, чтобы остановить все."
    )


def test_not_ready_reports_conditions_and_empty_log(start_service: BaseTool, tmp_path: Path) -> None:
    """
    Служба, чей вывод перенаправлен в свой файл, не становится готовой: ответ называет порт, номер
    работающего процесса для stop_process и не даёт путь к пустому логу инструмента.
    """
    port = _free_port()

    answer = start_service.invoke({
        "command": f"python3 -m http.server {port} --bind 127.0.0.1 > served.log 2>&1",
        "port": port,
        "log_pattern": "Serving HTTP",
        "timeout_seconds": 2,
    })

    assert str(port) in answer
    assert is_process_alive(process_id = _stop_process_id(answer = answer))
    assert "services/" not in answer
    assert (tmp_path / "served.log").exists()


def test_not_ready_with_output_shows_log(start_service: BaseTool) -> None:
    """
    Служба с выводом, где нет строки log_pattern, не становится готовой: ответ называет порт, номер
    работающего процесса для stop_process, путь к логу и последние строки лога.
    """
    port = _free_port()

    answer = start_service.invoke({
        "command": f"python3 -u -m http.server {port} --bind 127.0.0.1",
        "port": port,
        "log_pattern": "Server started",
        "timeout_seconds": 2,
    })

    assert str(port) in answer
    assert is_process_alive(process_id = _stop_process_id(answer = answer))
    log_path = re.search(r"\S+services/\S+\.log", answer)
    assert log_path is not None, answer
    assert "Serving HTTP" in answer


def test_failed_service_is_not_listed(start_service: BaseTool, stop_process: BaseTool) -> None:
    """
    Служба, которая сразу завершилась, не получает в ответе вызова stop_process и не попадает в список
    stop_process.
    """
    port = _free_port()

    answer = start_service.invoke({"command": "python3 -c 'import sys; sys.exit(3)'", "port": port})

    assert STOP_CALL_PATTERN.search(answer) is None, answer
    assert stop_process.invoke({}) == "Работающих фоновых процессов не было."

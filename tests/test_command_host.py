"""Тесты хозяина команд: одна песочница на агента — свои процессы останавливаются из любого вызова,
чужие нет; запись только в разрешённые папки; предел времени, одновременные команды, перезапуск хозяина;
процесс, ушедший в фон в новой сессии, остаётся своим; сторож песочницы переживает падение хозяина,
а в Linux — и сигнал всем процессам из команды."""

import subprocess
import sys
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from codeteam.common.shell import CommandHost, CommandHostRestarted, CommandResult, ShellProcesses
from codeteam.common.shell.sandbox import landlock_exec
from tests.shell_helpers import error_page_server_command, free_port, is_process_alive, keeper_process_ids, \
    wait_port_open, wait_process_gone

pytestmark = pytest.mark.skipif(
    not (
        sys.platform == "darwin"
        or (sys.platform == "linux" and landlock_exec.landlock_abi_version() >= landlock_exec.MINIMAL_ABI_VERSION)
    ),
    reason = "песочница есть только на macOS и в Linux с Landlock",
)

# Предел времени команды в тестах, секунды.
COMMAND_TIMEOUT_SECONDS = 20

# Сколько может длиться вызов, оставивший процесс в фоне: дочитывание вывода и запас, секунды.
BACKGROUND_CALL_LIMIT_SECONDS = 3


class AgentCommands:
    """
    Хозяин команд агента в папке теста.

        host: хозяин команд.
        processes: учёт фоновых процессов агента.
        work_dir: папка запуска и записи.
    """

    def __init__(self, *, work_dir: Path) -> None:
        self.processes = ShellProcesses()
        self.host = CommandHost(write_roots = (work_dir,), processes = self.processes)
        self.work_dir = work_dir

    def run(self, *, command: str) -> CommandResult:
        """
        Выполняет команду и запоминает её фоновые процессы.

            command: команда bash.

        Возвращает: Итог команды.
        """
        result = self.host.run(command = command, working_dir = str(self.work_dir), timeout_seconds = COMMAND_TIMEOUT_SECONDS)
        self.processes.remember(
            process_group_id = result.process_group_id,
            background_process_id = result.background_process_id,
            command = command,
        )

        return result

    def start_background(self, *, seconds: int) -> int:
        """
        Запускает фоновый sleep.

            seconds: длительность sleep.

        Возвращает: Номер фонового процесса.
        """
        return int(self.run(command = f"sleep {seconds} > /dev/null 2>&1 & echo $!").output.split()[-1])

    def close(self) -> None:
        """
        Снимает фоновые процессы и останавливает хозяина.
        """
        self.processes.kill_all()
        self.host.close()


def _make_agent(*, path: Path) -> Iterator[AgentCommands]:
    """
    Создаёт хозяина команд агента в папке и останавливает его после теста.

        path: папка запуска и записи.

    Возвращает: Хозяина команд агента.
    """
    path.mkdir(parents = True, exist_ok = True)
    agent = AgentCommands(work_dir = path)
    yield agent
    agent.close()


@pytest.fixture
def agent(tmp_path: Path) -> Iterator[AgentCommands]:
    """Хозяин команд агента в папке теста."""
    yield from _make_agent(path = tmp_path / "agent")


@pytest.fixture
def other_agent(tmp_path: Path) -> Iterator[AgentCommands]:
    """Хозяин команд другого агента."""
    yield from _make_agent(path = tmp_path / "other_agent")


@pytest.fixture
def outside_process() -> Iterator[subprocess.Popen]:
    """
    Процесс вне песочницы.

    Возвращает: Работающий процесс sleep; снимается после теста.
    """
    process = subprocess.Popen(["sleep", "301"])
    yield process
    process.kill()
    process.wait()


def test_kill_own_process_from_previous_call(agent: AgentCommands) -> None:
    """
    kill фонового процесса из прошлого вызова останавливает его.
    """
    process_id = agent.start_background(seconds = 300)

    result = agent.run(command = f"kill {process_id}")

    assert result.exit_code == 0
    assert wait_process_gone(process_id = process_id)


def test_kill_own_process_by_variable_and_substitution(agent: AgentCommands) -> None:
    """
    kill своего процесса через переменную и через $(pgrep ...) останавливает его.
    """
    by_variable = agent.start_background(seconds = 302)
    by_substitution = agent.start_background(seconds = 303)

    agent.run(command = f"APP_PID={by_variable}; kill $APP_PID")
    agent.run(command = "kill $(pgrep -f '[s]leep 303')")

    assert wait_process_gone(process_id = by_variable)
    assert wait_process_gone(process_id = by_substitution)


def test_outside_process_is_protected(agent: AgentCommands, outside_process: subprocess.Popen) -> None:
    """
    kill, pkill и kill через $(pgrep ...) процесса вне песочницы получают отказ, процесс работает.
    """
    by_number = agent.run(command = f"kill {outside_process.pid}")
    agent.run(command = "pkill -f '[s]leep 301'")
    agent.run(command = "kill -9 $(pgrep -f '[s]leep 301')")

    assert by_number.exit_code != 0
    assert "Operation not permitted" in by_number.output
    assert outside_process.poll() is None


def test_other_agent_process_is_protected(agent: AgentCommands, other_agent: AgentCommands) -> None:
    """
    kill процесса другого агента получает отказ, процесс работает.
    """
    process_id = other_agent.start_background(seconds = 304)

    result = agent.run(command = f"kill {process_id}")

    assert result.exit_code != 0
    assert is_process_alive(process_id = process_id)


def test_write_only_to_allowed_folders(agent: AgentCommands) -> None:
    """
    Запись в папку агента разрешена, в папку тестов проекта — нет.
    """
    outside_path = Path(__file__).resolve().parent / "command_host_outside.txt"

    allowed = agent.run(command = "mkdir -p sub && echo x > sub/a.txt")
    denied = agent.run(command = f"echo x > {outside_path}")

    assert allowed.exit_code == 0
    assert denied.exit_code != 0
    assert not outside_path.exists()


def test_pipe_exit_codes(agent: AgentCommands) -> None:
    """
    Коды команд цепочки через | приходят вместе с итогом.
    """
    result = agent.run(command = "false | true")

    assert result.exit_code == 0
    assert result.pipe_exit_codes == (1, 0)


def test_background_process_id(agent: AgentCommands) -> None:
    """
    Номер последнего фонового процесса совпадает с $! команды; без фоновых процессов номера нет.
    """
    background = agent.run(command = "sleep 306 > /dev/null 2>&1 & echo $!")
    foreground = agent.run(command = "echo без фона")

    assert background.background_process_id == int(background.output.split()[-1])
    assert foreground.background_process_id is None


def test_background_list_does_not_block_call(agent: AgentCommands) -> None:
    """
    Фоновая цепочка `cd && программа > файл &` держит вывод вызова, но вызов не ждёт её;
    программа продолжает работать.
    """
    started = time.monotonic()

    result = agent.run(command = "cd . && sleep 307 > /dev/null 2>&1 & echo $!")

    assert result.exit_code == 0
    assert time.monotonic() - started < BACKGROUND_CALL_LIMIT_SECONDS
    assert is_process_alive(process_id = int(result.output.split()[-1]))


def test_background_without_redirect_does_not_block_call(agent: AgentCommands) -> None:
    """
    Фоновая программа без перенаправления вывода не держит вызов; программа продолжает работать.
    """
    started = time.monotonic()

    result = agent.run(command = "sleep 308 & echo запущен $!")

    assert result.output.split()[0] == "запущен"
    assert time.monotonic() - started < BACKGROUND_CALL_LIMIT_SECONDS
    assert is_process_alive(process_id = int(result.output.split()[-1]))


def test_foreground_output_is_complete(agent: AgentCommands) -> None:
    """
    Вывод основной команды приходит целиком: и большой, и с паузой перед концом.
    """
    large = agent.run(command = "seq 1 200000")
    paused = agent.run(command = "echo начало; sleep 1; echo конец")

    assert large.output.split() == [str(number) for number in range(1, 200001)]
    assert paused.output.split() == ["начало", "конец"]


def test_timeout_kills_command(agent: AgentCommands) -> None:
    """
    Команда дольше предела времени прерывается вместе со своей группой процессов.
    """
    started = time.monotonic()

    result = agent.host.run(command = "echo начало; sleep 30", working_dir = str(agent.work_dir), timeout_seconds = 1)

    assert result.exit_code is None
    assert "начало" in result.output
    assert time.monotonic() - started < 10


def test_commands_run_at_the_same_time(agent: AgentCommands) -> None:
    """
    Команды из разных потоков выполняются одновременно.
    """
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers = 3) as executor:
        results = list(executor.map(lambda _: agent.run(command = "sleep 1; echo готово"), range(3)))

    assert all(result.output.strip() == "готово" for result in results)
    assert time.monotonic() - started < 2.5


def test_host_restart_stops_background_processes(agent: AgentCommands) -> None:
    """
    Агент снял хозяина: команда получает CommandHostRestarted, фоновые процессы агента остановлены,
    следующая команда выполняется.
    """
    process_id = agent.start_background(seconds = 305)

    with pytest.raises(CommandHostRestarted):
        agent.run(command = "kill -9 $PPID")

    assert wait_process_gone(process_id = process_id)
    assert agent.run(command = "echo снова").output.strip() == "снова"


def test_pkill_python_does_not_stop_host(agent: AgentCommands) -> None:
    """
    Обычный сигнал остановки хозяину (pkill -f python) не снимает его.
    """
    agent.run(command = "kill $PPID")

    assert agent.run(command = "echo работает").output.strip() == "работает"


def _start_detached_server(*, agent: AgentCommands) -> int:
    """
    Запускает сервер, который уходит в фон в новой сессии.

        agent: хозяин команд агента.

    Возвращает: Номер процесса сервера.
    """
    port = free_port()
    process_id = int(agent.run(command = error_page_server_command(port = port, detached = True)).output.split()[-1])
    assert wait_port_open(port = port)

    return process_id


def test_detached_process_is_own(agent: AgentCommands, other_agent: AgentCommands) -> None:
    """
    Процесс, ушедший в фон в новой сессии, есть в списке своего агента; другой агент его не видит и не снимает.
    """
    process_id = _start_detached_server(agent = agent)
    other_agent.run(command = "echo старт")

    other_agent.processes.kill_all()

    assert process_id in [process.process_id for process in agent.processes.alive_processes()]
    assert process_id not in [process.process_id for process in other_agent.processes.alive_processes()]
    assert is_process_alive(process_id = process_id)


def test_close_stops_detached_process(agent: AgentCommands) -> None:
    """
    Остановка хозяина снимает и процесс, ушедший в фон в новой сессии.
    """
    process_id = _start_detached_server(agent = agent)

    agent.host.close()

    assert wait_process_gone(process_id = process_id)


def test_host_restart_stops_detached_process_and_keeps_keeper(agent: AgentCommands) -> None:
    """
    Агент снял хозяина: процесс, ушедший в фон, остановлен, сторож тот же, следующая команда выполняется.
    """
    process_id = _start_detached_server(agent = agent)
    keepers = keeper_process_ids()

    with pytest.raises(CommandHostRestarted):
        agent.run(command = "kill -9 $PPID")

    assert keepers
    assert wait_process_gone(process_id = process_id)
    assert keeper_process_ids() == keepers
    assert agent.run(command = "echo снова").output.strip() == "снова"


@pytest.mark.skipif(sys.platform != "linux", reason = "вложить песочницу можно только в Linux")
def test_signal_to_all_does_not_stop_keeper(agent: AgentCommands) -> None:
    """
    kill -9 -1 из команды снимает хозяина, но не сторожа: он во внешней песочнице.
    """
    agent.run(command = "echo старт")
    keepers = keeper_process_ids()

    with pytest.raises(CommandHostRestarted):
        agent.run(command = "kill -9 -1")

    assert keepers
    assert keeper_process_ids() == keepers
    assert agent.run(command = "echo снова").output.strip() == "снова"

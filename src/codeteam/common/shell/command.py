"""Запуск команды оболочки с пределом времени."""

import os
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from codeteam.common.shell.macos_sandbox import ReadRestrictions, sandbox_argv

# Переменные окружения, через которые команда унаследовала бы виртуальное окружение процесса
# codeteam и его пути импорта: их задают uv run и среда разработки.
HOST_ENVIRONMENT_NAMES = ("VIRTUAL_ENV", "PYTHONPATH", "PYTHONHOME", "UV")

# Начала имён переменных окружения uv процесса codeteam.
HOST_ENVIRONMENT_PREFIXES = ("UV_",)

# Строка после команды: отправляет коды команд последней цепочки через | в канал с номером
# {status_fd} и завершает bash с кодом самой команды.
PIPE_STATUS_SUFFIX = (
    '\n__ct_pipe_status="${{PIPESTATUS[*]}}" __ct_exit_code=$?; '
    'echo "$__ct_pipe_status" >&{status_fd}; exit "$__ct_exit_code"'
)

# Сколько байт кодов цепочки читать из канала: коды занимают одну короткую строку.
PIPE_STATUS_READ_LIMIT = 4096


@dataclass(frozen = True)
class CommandResult:
    """
    Итог команды оболочки.

        exit_code: код возврата; None, если команда прервана по времени.
        output: stdout и stderr вместе.
        pipe_exit_codes: коды команд последней цепочки через |; пустые, если команда прервана
            по времени или сама вызвала exit.
    """

    exit_code: int | None
    output: str
    pipe_exit_codes: tuple[int, ...]


def run_command(
    *,
    command: str,
    working_dir: str,
    timeout_seconds: int,
    write_roots: tuple[Path, ...],
    read_restrictions: ReadRestrictions,
) -> CommandResult:
    """
    Запускает команду bash в своей группе процессов; по истечении времени снимает всю группу.

    Ввода у команды нет: stdin закрыт. Окружение команды — без виртуального окружения процесса
    codeteam. На macOS запись разрешена только в write_roots и временные папки системы, чтение
    закрытых файлов и папок запрещено (macos_sandbox).

        command: команда bash.
        working_dir: папка запуска.
        timeout_seconds: предел времени, секунды.
        write_roots: папки, куда команде разрешена запись.
        read_restrictions: запреты чтения.

    Возвращает: Код возврата, вывод команды и коды команд её последней цепочки.
    """
    status_read_fd, status_write_fd = os.pipe()
    script = command + PIPE_STATUS_SUFFIX.format(status_fd = status_write_fd)
    process = subprocess.Popen(
        sandbox_argv(
            argv = ["bash", "-c", script],
            write_roots = write_roots,
            read_restrictions = read_restrictions,
        ),
        cwd = working_dir,
        env = _command_environment(),
        stdin = subprocess.DEVNULL,
        stdout = subprocess.PIPE,
        stderr = subprocess.STDOUT,
        start_new_session = True,
        pass_fds = (status_write_fd,),
    )
    os.close(status_write_fd)
    try:
        raw_output, _ = process.communicate(timeout = timeout_seconds)
        exit_code = process.returncode
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        raw_output, _ = process.communicate()
        exit_code = None

    return CommandResult(
        exit_code = exit_code,
        output = raw_output.decode("utf-8", errors = "replace"),
        pipe_exit_codes = _read_pipe_exit_codes(status_read_fd = status_read_fd),
    )


def _read_pipe_exit_codes(*, status_read_fd: int) -> tuple[int, ...]:
    """
    Читает коды команд цепочки из канала и закрывает его.

    Канал читается без ожидания: команда уже завершилась, а фоновый процесс команды может держать
    канал открытым.

        status_read_fd: конец канала для чтения.

    Возвращает: Коды команд цепочки; пустые, если команда их не отправила.
    """
    os.set_blocking(status_read_fd, False)
    try:
        raw_status = os.read(status_read_fd, PIPE_STATUS_READ_LIMIT)
    except BlockingIOError:
        raw_status = b""
    finally:
        os.close(status_read_fd)

    return tuple(int(code) for code in raw_status.decode("ascii", errors = "replace").split() if code.isdigit())


def _command_environment() -> dict[str, str]:
    """
    Собирает окружение команды: окружение процесса без его виртуального окружения.

    Убирает переменные HOST_ENVIRONMENT_NAMES и HOST_ENVIRONMENT_PREFIXES и папку bin
    виртуального окружения процесса из PATH.

    Возвращает: Переменные окружения для команды.
    """
    host_bin_dirs = {str(Path(sys.prefix) / "bin")} if sys.prefix != sys.base_prefix else set()
    virtual_env = os.environ.get("VIRTUAL_ENV")
    if virtual_env is not None:
        host_bin_dirs.add(str(Path(virtual_env) / "bin"))

    environment = {
        name: value
        for name, value in os.environ.items()
        if name not in HOST_ENVIRONMENT_NAMES and not name.startswith(HOST_ENVIRONMENT_PREFIXES)
    }
    path_dirs = environment.get("PATH", "").split(os.pathsep)
    environment["PATH"] = os.pathsep.join(path_dir for path_dir in path_dirs if path_dir not in host_bin_dirs)

    return environment

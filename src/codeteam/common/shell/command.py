"""Запуск команды оболочки с пределом времени."""

import os
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from codeteam.common.shell.macos_sandbox import sandbox_argv

# Переменные окружения, через которые команда унаследовала бы виртуальное окружение процесса
# codeteam и его пути импорта: их задают uv run и среда разработки.
HOST_ENVIRONMENT_NAMES = ("VIRTUAL_ENV", "PYTHONPATH", "PYTHONHOME", "UV")

# Начала имён переменных окружения uv процесса codeteam.
HOST_ENVIRONMENT_PREFIXES = ("UV_",)


@dataclass(frozen = True)
class CommandResult:
    """
    Итог команды оболочки.

        exit_code: код возврата; None, если команда прервана по времени.
        output: stdout и stderr вместе.
    """

    exit_code: int | None
    output: str


def run_command(
    *,
    command: str,
    working_dir: str,
    timeout_seconds: int,
    write_roots: tuple[Path, ...],
) -> CommandResult:
    """
    Запускает команду bash в своей группе процессов; по истечении времени снимает всю группу.

    Ввода у команды нет: stdin закрыт. Окружение команды — без виртуального окружения процесса
    codeteam. На macOS запись разрешена только в write_roots и временные папки системы
    (macos_sandbox).

        command: команда bash.
        working_dir: папка запуска.
        timeout_seconds: предел времени, секунды.
        write_roots: папки, куда команде разрешена запись.

    Возвращает: Код возврата и вывод команды.
    """
    process = subprocess.Popen(
        sandbox_argv(argv = ["bash", "-c", command], write_roots = write_roots),
        cwd = working_dir,
        env = _command_environment(),
        stdin = subprocess.DEVNULL,
        stdout = subprocess.PIPE,
        stderr = subprocess.STDOUT,
        start_new_session = True,
    )
    try:
        raw_output, _ = process.communicate(timeout = timeout_seconds)
        exit_code = process.returncode
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        raw_output, _ = process.communicate()
        exit_code = None

    return CommandResult(exit_code = exit_code, output = raw_output.decode("utf-8", errors = "replace"))


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

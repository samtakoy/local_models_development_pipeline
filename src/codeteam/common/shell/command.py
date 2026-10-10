"""Итог команды оболочки и окружение, в котором выполняются команды агента."""

import os
import sys
from dataclasses import dataclass
from pathlib import Path

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
        pipe_exit_codes: коды команд последней цепочки через |; пустые, если команда прервана
            по времени или сама вызвала exit.
        process_group_id: номер группы процессов команды: в ней остаются её фоновые процессы.
        background_process_id: номер последнего процесса, запущенного командой в фоне ($!); None, если
            команда ничего не запускала в фоне, прервана по времени или сама вызвала exit.
    """

    exit_code: int | None
    output: str
    pipe_exit_codes: tuple[int, ...]
    process_group_id: int
    background_process_id: int | None


def command_environment() -> dict[str, str]:
    """
    Собирает окружение команд агента: окружение процесса codeteam без его виртуального окружения.

    Убирает переменные HOST_ENVIRONMENT_NAMES и HOST_ENVIRONMENT_PREFIXES и папку bin
    виртуального окружения процесса из PATH.

    Возвращает: Переменные окружения для команд.
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

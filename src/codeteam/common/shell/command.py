"""Запуск команды оболочки с пределом времени."""

import os
import signal
import subprocess
from dataclasses import dataclass
from pathlib import Path

from codeteam.common.shell.macos_sandbox import sandbox_argv


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

    Ввода у команды нет: stdin закрыт. На macOS запись разрешена только в write_roots и
    временные папки системы (macos_sandbox).

        command: команда bash.
        working_dir: папка запуска.
        timeout_seconds: предел времени, секунды.
        write_roots: папки, куда команде разрешена запись.

    Возвращает: Код возврата и вывод команды.
    """
    process = subprocess.Popen(
        sandbox_argv(argv = ["bash", "-c", command], write_roots = write_roots),
        cwd = working_dir,
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

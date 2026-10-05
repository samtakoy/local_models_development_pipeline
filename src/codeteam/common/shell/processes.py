"""Фоновые процессы команд оболочки: учёт групп процессов, их список и снятие."""

import os
import signal
import subprocess
from dataclasses import dataclass


@dataclass(frozen = True)
class ShellProcess:
    """
    Работающий процесс из запомненной группы.

        process_id: номер процесса.
        command: команда процесса с аргументами.
    """

    process_id: int
    command: str


class ShellProcesses:
    """
    Группы процессов команд, в которых после завершения команды остались работающие процессы.
    """

    def __init__(self) -> None:
        self._group_ids: set[int] = set()

    def remember(self, *, process_group_id: int) -> None:
        """
        Запоминает группу процессов команды, если в ней остались работающие процессы.

            process_group_id: номер группы процессов команды.
        """
        if _is_process_group_alive(process_group_id = process_group_id):
            self._group_ids.add(process_group_id)

    def alive_processes(self) -> list[ShellProcess]:
        """
        Перечисляет работающие процессы запомненных групп.

        Возвращает: Процессы по возрастанию номера.
        """
        if not self._group_ids:
            return []

        listing = subprocess.run(
            ["ps", "-A", "-o", "pid=,pgid=,command="],
            capture_output = True,
            text = True,
            check = True,
        )
        processes = []
        for line in listing.stdout.splitlines():
            process_id, process_group_id, command = line.split(maxsplit = 2)
            if int(process_group_id) in self._group_ids:
                processes.append(ShellProcess(process_id = int(process_id), command = command))

        return sorted(processes, key = lambda process: process.process_id)

    def kill_group_of(self, *, process_id: int) -> bool:
        """
        Снимает запомненную группу, в которой работает процесс.

            process_id: номер процесса.

        Возвращает: True, если группа снята; False, если процесса нет или его группа не запомнена.
        """
        try:
            process_group_id = os.getpgid(process_id)
        except ProcessLookupError:
            return False

        if process_group_id not in self._group_ids:
            return False

        kill_process_group(process_group_id = process_group_id)
        self._group_ids.discard(process_group_id)

        return True

    def kill_all(self) -> None:
        """
        Снимает все запомненные группы процессов.
        """
        for process_group_id in self._group_ids:
            kill_process_group(process_group_id = process_group_id)
        self._group_ids.clear()


def kill_process_group(*, process_group_id: int) -> None:
    """
    Снимает группу процессов; если в группе никого не осталось или остались только завершённые
    процессы, которые ещё не убрала система, ничего не делает.

        process_group_id: номер группы процессов.
    """
    try:
        os.killpg(process_group_id, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        # PermissionError: на macOS так отвечает группа из одних завершённых процессов
        pass


def _is_process_group_alive(*, process_group_id: int) -> bool:
    """
    Проверяет, есть ли в группе работающие процессы.

        process_group_id: номер группы процессов.

    Возвращает: True, если в группе есть хотя бы один процесс, в том числе завершённый, которого
        ещё не убрала система.
    """
    try:
        os.killpg(process_group_id, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # на macOS так отвечает группа из одних завершённых процессов
        return True

    return True

"""Фоновые процессы команд оболочки: учёт групп процессов, их список и снятие."""

import os
import signal
from dataclasses import dataclass


@dataclass(frozen = True)
class ShellProcess:
    """
    Команда агента, после которой в фоне остались работающие процессы.

        process_id: номер, по которому агент узнаёт запуск: номер последнего фонового процесса
            команды ($!), а если его нет — номер группы процессов команды.
        command: команда агента.
    """

    process_id: int
    command: str


class ShellProcesses:
    """
    Группы процессов команд, в которых после завершения команды остались работающие процессы.
    """

    def __init__(self) -> None:
        # запуск агента по номеру группы процессов его команды
        self._processes: dict[int, ShellProcess] = {}

    def remember(self, *, process_group_id: int, background_process_id: int | None, command: str) -> None:
        """
        Запоминает группу процессов команды, если в ней остались работающие процессы.

            process_group_id: номер группы процессов команды.
            background_process_id: номер последнего фонового процесса команды ($!); None, если его нет.
            command: команда агента.
        """
        if not is_process_group_alive(process_group_id = process_group_id):
            return

        process_id = process_group_id if background_process_id is None else background_process_id
        self._processes[process_group_id] = ShellProcess(process_id = process_id, command = command)

    def alive_processes(self) -> list[ShellProcess]:
        """
        Перечисляет запуски агента, в группах которых есть работающие процессы.

        Возвращает: Запуски по возрастанию номера.
        """
        alive = [
            process
            for process_group_id, process in self._processes.items()
            if is_process_group_alive(process_group_id = process_group_id)
        ]

        return sorted(alive, key = lambda process: process.process_id)

    def process_of(self, *, process_id: int) -> ShellProcess | None:
        """
        Находит запуск агента, в группе которого работает процесс.

            process_id: номер запуска из учёта, номер запомненной группы или номер любого процесса в ней.

        Возвращает: Запуск агента; None, если процесс не относится к запомненной группе.
        """
        process_group_id = self._group_of(process_id = process_id)
        if process_group_id is None:
            return None

        return self._processes[process_group_id]

    def kill_group_of(self, *, process_id: int) -> bool:
        """
        Снимает запомненную группу, в которой работает процесс.

            process_id: номер запуска из учёта, номер запомненной группы или номер любого процесса в ней.

        Возвращает: True, если группа снята; False, если процесса нет или его группа не запомнена.
        """
        process_group_id = self._group_of(process_id = process_id)
        if process_group_id is None:
            return False

        kill_process_group(process_group_id = process_group_id)
        del self._processes[process_group_id]

        return True

    def kill_all(self) -> None:
        """
        Снимает все запомненные группы процессов.
        """
        for process_group_id in self._processes:
            kill_process_group(process_group_id = process_group_id)
        self._processes.clear()

    def _group_of(self, *, process_id: int) -> int | None:
        """
        Находит запомненную группу по номеру.

            process_id: номер запуска из учёта, номер запомненной группы или номер любого процесса в ней.

        Возвращает: Номер группы; None, если номер не относится к запомненной группе.
        """
        for process_group_id, process in self._processes.items():
            if process_id in (process_group_id, process.process_id):
                return process_group_id

        try:
            process_group_id = os.getpgid(process_id)
        except ProcessLookupError:
            return None

        return process_group_id if process_group_id in self._processes else None


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


def is_process_group_alive(*, process_group_id: int) -> bool:
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

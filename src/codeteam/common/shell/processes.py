"""Фоновые процессы агента: учёт запусков, список работающих процессов, их порты и снятие.

С песочницей свои процессы — все процессы песочницы агента, в том числе ушедшие в фон в новой группе:
их отбирает песочница. Без песочницы — процессы групп запомненных команд.
"""

import os
import signal
from dataclasses import dataclass
from typing import Protocol

import psutil


@dataclass(frozen = True)
class ShellProcess:
    """
    Запуск агента, после которого работают процессы.

        process_id: номер, по которому агент узнаёт запуск: номер последнего фонового процесса
            команды ($!), а если его нет — номер группы процессов команды; для группы, которой агент
            не запускал напрямую (процесс ушёл в фон в новой группе), — наименьший номер её процесса.
        command: команда агента; для такой группы — командная строка её процесса.
    """

    process_id: int
    command: str


@dataclass(frozen = True)
class _RunningProcess:
    """
    Работающий процесс агента.

        process_id: номер процесса.
        process_group_id: номер его группы процессов.
    """

    process_id: int
    process_group_id: int


class ProcessSandbox(Protocol):
    """
    Песочница агента: отбирает и снимает свои процессы среди любых номеров.
    """

    def own_process_ids(self, *, process_ids: list[int]) -> list[int] | None:
        """
        Отбирает номера процессов песочницы агента.

            process_ids: номера процессов.

        Возвращает: Свои номера; None, если песочницу проверить нельзя.
        """

    def kill_own_processes(self, *, process_ids: list[int]) -> list[int] | None:
        """
        Снимает группы процессов песочницы с этими номерами.

            process_ids: номера процессов.

        Возвращает: Номера, группы которых сняты; None, если песочница недоступна.
        """


class ShellProcesses:
    """
    Фоновые процессы агента. Запомненные команды дают имена запускам в списке процессов.
    """

    def __init__(self) -> None:
        # запуск агента по номеру группы процессов его команды
        self._processes: dict[int, ShellProcess] = {}
        # песочница агента; None - своими считаются процессы запомненных групп
        self._sandbox: ProcessSandbox | None = None

    def use_sandbox(self, *, sandbox: ProcessSandbox) -> None:
        """
        Включает отбор своих процессов песочницей агента.

            sandbox: песочница агента.
        """
        self._sandbox = sandbox

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
        Перечисляет запуски агента, в группах которых работают процессы.

        Возвращает: Запуски по возрастанию номера.
        """
        return self._launches(running = self._running_processes())

    def port_listeners(self, *, port: int) -> list[ShellProcess]:
        """
        Находит запуски агента, процессы которых слушают порт TCP.

            port: порт.

        Возвращает: Запуски по возрастанию номера; пустой список, если порт никто не слушает или слушают
            только чужие процессы.
        """
        listeners = [
            process
            for process in self._running_processes()
            if _listens(process_id = process.process_id, port = port)
        ]

        return self._launches(running = listeners)

    def kill_group_of(self, *, process_id: int) -> bool:
        """
        Снимает группу своих процессов, в которой работает процесс.

            process_id: номер запуска из списка, номер запомненной группы или номер любого своего процесса.

        Возвращает: True, если группа снята; False, если среди своих работающих процессов такого нет.
        """
        running = self._running_processes()
        process_group_id = self._group_of(process_id = process_id, running = running)
        if process_group_id is None:
            return False

        self._kill(running = [process for process in running if process.process_group_id == process_group_id])
        self._processes.pop(process_group_id, None)

        return True

    def kill_all(self) -> None:
        """
        Снимает все свои процессы.
        """
        self._kill(running = self._running_processes())
        self._processes.clear()

    def _running_processes(self) -> list[_RunningProcess]:
        """
        Находит свои работающие процессы среди процессов пользователя: с песочницей их отбирает песочница,
        без неё или когда песочницу проверить нельзя — процессы запомненных групп.

        Возвращает: Свои работающие процессы.
        """
        candidate_ids = _user_process_ids()
        own_ids = None if self._sandbox is None else self._sandbox.own_process_ids(process_ids = candidate_ids)
        running = []
        for process_id in candidate_ids if own_ids is None else own_ids:
            try:
                process_group_id = os.getpgid(process_id)
            except ProcessLookupError:
                continue
            if own_ids is None and process_group_id not in self._processes:
                continue
            running.append(_RunningProcess(process_id = process_id, process_group_id = process_group_id))

        return running

    def _kill(self, *, running: list[_RunningProcess]) -> None:
        """
        Снимает группы процессов: через песочницу, а когда она недоступна — запомненные группы.

            running: свои работающие процессы.
        """
        if not running:
            return

        if self._sandbox is not None:
            killed = self._sandbox.kill_own_processes(process_ids = [process.process_id for process in running])
            if killed is not None:
                return

        for process_group_id in {process.process_group_id for process in running} & self._processes.keys():
            kill_process_group(process_group_id = process_group_id)

    def _launches(self, *, running: list[_RunningProcess]) -> list[ShellProcess]:
        """
        Собирает запуски по группам процессов: запомненная группа — её команда, иначе — процесс группы
        с наименьшим номером и его командная строка.

            running: работающие процессы.

        Возвращает: Запуски по возрастанию номера.
        """
        group_process_ids: dict[int, list[int]] = {}
        for process in running:
            group_process_ids.setdefault(process.process_group_id, []).append(process.process_id)

        launches = []
        for process_group_id, process_ids in group_process_ids.items():
            launch = self._processes.get(process_group_id)
            if launch is None:
                first_process_id = min(process_ids)
                launch = ShellProcess(process_id = first_process_id, command = _command_line(process_id = first_process_id))
            launches.append(launch)

        return sorted(launches, key = lambda launch: launch.process_id)

    def _group_of(self, *, process_id: int, running: list[_RunningProcess]) -> int | None:
        """
        Находит группу своих работающих процессов по номеру.

            process_id: номер запуска из списка, номер запомненной группы или номер любого своего процесса.
            running: свои работающие процессы.

        Возвращает: Номер группы; None, если номер не относится к своим работающим процессам.
        """
        running_group_ids = {process.process_group_id for process in running}
        for process_group_id, launch in self._processes.items():
            if process_id in (process_group_id, launch.process_id) and process_group_id in running_group_ids:
                return process_group_id

        for process in running:
            if process.process_id == process_id:
                return process.process_group_id

        return None


def _user_process_ids() -> list[int]:
    """
    Перечисляет процессы текущего пользователя, кроме этого процесса.

    Возвращает: Номера процессов.
    """
    user_id = os.getuid()
    process_ids = []
    for process in psutil.process_iter(["uids"]):
        uids = process.info["uids"]
        if uids is not None and uids.real == user_id and process.pid != os.getpid():
            process_ids.append(process.pid)

    return process_ids


def _listens(*, process_id: int, port: int) -> bool:
    """
    Проверяет, слушает ли процесс порт TCP.

        process_id: номер процесса.
        port: порт.

    Возвращает: True, если слушает; False, если нет или процесс уже завершился.
    """
    try:
        connections = psutil.Process(process_id).net_connections(kind = "tcp")
    except psutil.Error:
        return False

    return any(connection.status == psutil.CONN_LISTEN and connection.laddr.port == port for connection in connections)


def _command_line(*, process_id: int) -> str:
    """
    Читает командную строку процесса.

        process_id: номер процесса.

    Возвращает: Командную строку; пустую строку, если процесс уже завершился.
    """
    try:
        return " ".join(psutil.Process(process_id).cmdline())
    except psutil.Error:
        return ""


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

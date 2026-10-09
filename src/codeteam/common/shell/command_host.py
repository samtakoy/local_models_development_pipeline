"""Хозяин команд агента: одна песочница на все команды агента.

Команды выполняет процесс-хозяин (host_process.py), запущенный в песочнице. Все команды — его дочерние
процессы, поэтому агент останавливает свои фоновые процессы из любого вызова, а чужие — нет.
"""

import json
import logging
import queue
import subprocess
import sys
import threading
from pathlib import Path

from codeteam.common.shell import host_process
from codeteam.common.shell.command import CommandResult, command_environment
from codeteam.common.shell.processes import ShellProcesses, kill_process_group
from codeteam.common.shell.sandbox import HOME_CACHE_DIRS, sandboxed_argv

logger = logging.getLogger(__name__)

# Сколько ждать итога команды после снятия её группы по пределу времени, секунды.
KILLED_COMMAND_WAIT_SECONDS = 5

# Сколько ждать завершения процесса-хозяина после закрытия его ввода, секунды.
HOST_EXIT_WAIT_SECONDS = 5


class CommandHostRestarted(RuntimeError):
    """
    Процесс-хозяин упал и запущен заново: команда не выполнена, фоновые процессы агента остановлены.
    """


class _HostGone:
    """Метка в очереди ответов: процесс-хозяин завершился."""


_HOST_GONE = _HostGone()


class CommandHost:
    """
    Хозяин команд одного агента: запускает процесс-хозяина в песочнице при первой команде и выполняет
    через него команды. Команды можно выполнять одновременно из разных потоков.
    """

    def __init__(self, *, write_roots: tuple[Path, ...], processes: ShellProcesses) -> None:
        """
        Запоминает права песочницы и учёт фоновых процессов агента.

            write_roots: папки, куда командам разрешена запись; несуществующие создаются при запуске хозяина.
            processes: учёт фоновых процессов агента: при падении хозяина все они останавливаются.
        """
        self._write_roots = write_roots
        self._processes = processes
        self._lock = threading.Lock()
        self._connection: _HostConnection | None = None

    def run(self, *, command: str, working_dir: str, timeout_seconds: int) -> CommandResult:
        """
        Выполняет команду bash; по истечении времени снимает её группу процессов.
        Фоновые процессы завершившейся команды продолжают работать в её группе.

            command: команда bash.
            working_dir: папка запуска.
            timeout_seconds: предел времени, секунды.

        Возвращает: Код возврата, вывод команды и коды её последней цепочки.
            Падение хозяина поднимает CommandHostRestarted.
        """
        connection = self._current_connection()
        request_id, replies = connection.submit(command = command, working_dir = working_dir)
        started = replies.get()
        if started is _HOST_GONE:
            self._restart(connection = connection, process_group_id = None)

        process_group_id = started[host_process.PROCESS_GROUP_ID_FIELD]
        try:
            finished = replies.get(timeout = timeout_seconds)
            timed_out = False
        except queue.Empty:
            kill_process_group(process_group_id = process_group_id)
            finished = _get_or_none(replies = replies, timeout_seconds = KILLED_COMMAND_WAIT_SECONDS)
            timed_out = True
        finally:
            connection.forget(request_id = request_id)

        if finished is _HOST_GONE:
            self._restart(connection = connection, process_group_id = process_group_id)

        output = "" if finished is None else finished[host_process.OUTPUT_FIELD]
        if timed_out:
            return CommandResult(exit_code = None, output = output, pipe_exit_codes = (), process_group_id = process_group_id)

        return CommandResult(
            exit_code = finished[host_process.EXIT_CODE_FIELD],
            output = output,
            pipe_exit_codes = tuple(finished[host_process.PIPE_EXIT_CODES_FIELD]),
            process_group_id = process_group_id,
        )

    def close(self) -> None:
        """
        Останавливает процесс-хозяина. Фоновые процессы команд снимает владелец их учёта.
        """
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None

    def _current_connection(self) -> "_HostConnection":
        """
        Отдаёт соединение с работающим хозяином; при первой команде запускает хозяина.

        Возвращает: Соединение с хозяином. Упавший хозяин перезапускается, это поднимает CommandHostRestarted.
        """
        with self._lock:
            if self._connection is None:
                self._connection = self._start_connection()
            connection = self._connection

        if not connection.is_alive():
            self._restart(connection = connection, process_group_id = None)

        return connection

    def _start_connection(self) -> "_HostConnection":
        """
        Создаёт недостающие папки записи и запускает процесс-хозяина в песочнице.

        Возвращает: Соединение с новым хозяином.
        """
        for root in (*self._write_roots, *HOME_CACHE_DIRS):
            if not root.exists():
                root.mkdir(parents = True)

        argv = sandboxed_argv(argv = [sys.executable, "-I", host_process.__file__], write_roots = self._write_roots)

        return _HostConnection(argv = argv)

    def _restart(self, *, connection: "_HostConnection", process_group_id: int | None) -> None:
        """
        Перезапускает упавшего хозяина: снимает группу текущей команды и все фоновые процессы агента.

            connection: соединение с упавшим хозяином.
            process_group_id: группа текущей команды; None, если команда не успела запуститься.

        Поднимает CommandHostRestarted.
        """
        if process_group_id is not None:
            kill_process_group(process_group_id = process_group_id)

        with self._lock:
            if self._connection is connection:
                logger.warning("процесс-хозяин команд агента упал: перезапуск, фоновые процессы агента остановлены")
                self._processes.kill_all()
                connection.close()
                self._connection = self._start_connection()

        raise CommandHostRestarted("процесс-хозяин команд перезапущен, фоновые процессы агента остановлены")


class _HostConnection:
    """
    Соединение с одним процессом-хозяином: отправка запросов и раздача ответов ждущим вызовам.
    """

    def __init__(self, *, argv: list[str]) -> None:
        """
        Запускает процесс-хозяина и поток чтения его ответов.

            argv: запуск процесса-хозяина, уже под песочницей.
        """
        self._process = subprocess.Popen(
            argv,
            stdin = subprocess.PIPE,
            stdout = subprocess.PIPE,
            env = command_environment(),
            start_new_session = True,
            text = True,
            encoding = "utf-8",
        )
        self._lock = threading.Lock()
        self._replies: dict[int, queue.Queue] = {}
        self._next_request_id = 0
        # хозяин закрыл вывод: новые запросы сразу получают метку _HOST_GONE
        self._is_gone = False
        threading.Thread(target = self._read_replies, daemon = True).start()

    def is_alive(self) -> bool:
        """
        Проверяет, работает ли процесс-хозяин.

        Возвращает: True, если процесс не завершился.
        """
        return self._process.poll() is None

    def submit(self, *, command: str, working_dir: str) -> tuple[int, queue.Queue]:
        """
        Отправляет хозяину команду.

            command: команда bash.
            working_dir: папка запуска.

        Возвращает: Номер запроса и очередь его ответов; если хозяин завершился, в очереди будет метка _HOST_GONE.
        """
        replies: queue.Queue = queue.Queue()
        request = {
            host_process.COMMAND_FIELD: command,
            host_process.WORKING_DIR_FIELD: working_dir,
        }
        with self._lock:
            request_id = self._next_request_id
            self._next_request_id += 1
            self._replies[request_id] = replies
            if self._is_gone:
                replies.put(_HOST_GONE)
                return request_id, replies

            try:
                self._process.stdin.write(json.dumps({host_process.REQUEST_ID_FIELD: request_id, **request}) + "\n")
                self._process.stdin.flush()
            except (BrokenPipeError, ValueError):
                replies.put(_HOST_GONE)

        return request_id, replies

    def forget(self, *, request_id: int) -> None:
        """
        Перестаёт ждать ответы на запрос: поздний ответ отбрасывается.

            request_id: номер запроса.
        """
        with self._lock:
            self._replies.pop(request_id, None)

    def close(self) -> None:
        """
        Закрывает ввод хозяина и ждёт его завершения; не дождавшись, снимает его.
        """
        try:
            self._process.stdin.close()
        except BrokenPipeError:
            pass
        try:
            self._process.wait(timeout = HOST_EXIT_WAIT_SECONDS)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait()

    def _read_replies(self) -> None:
        """
        Читает ответы хозяина и раздаёт их по очередям запросов; когда хозяин завершился, кладёт во все
        очереди метку _HOST_GONE.
        """
        for line in self._process.stdout:
            reply = json.loads(line)
            with self._lock:
                replies = self._replies.get(reply[host_process.REQUEST_ID_FIELD])
            if replies is not None:
                replies.put(reply)

        with self._lock:
            self._is_gone = True
            for replies in self._replies.values():
                replies.put(_HOST_GONE)


def _get_or_none(*, replies: queue.Queue, timeout_seconds: float) -> dict | _HostGone | None:
    """
    Ждёт ответ из очереди не дольше предела.

        replies: очередь ответов запроса.
        timeout_seconds: предел ожидания, секунды.

    Возвращает: Ответ или метку _HOST_GONE; None, если ответа нет.
    """
    try:
        return replies.get(timeout = timeout_seconds)
    except queue.Empty:
        return None

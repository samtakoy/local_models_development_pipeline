"""Хозяин команд агента: одна песочница на все команды агента.

Песочницу держит сторож (sandbox_keeper.py): первый процесс песочницы, он запускает процесс-хозяина
(host_process.py) и после падения запускает нового в той же песочнице. Команды выполняет хозяин; все они —
его потомки и потому в песочнице агента, даже ушедшие в фон в новой сессии. Поэтому агент останавливает
свои фоновые процессы из любого вызова, а чужие — нет. Свои процессы среди любых номеров отбирает сторож:
сигналы из песочницы ядро пропускает только процессам этой песочницы. В Linux хозяин работает во вложенной
песочнице, и команды не могут снять сторожа.
"""

import json
import logging
import queue
import subprocess
import sys
import threading
from pathlib import Path

from codeteam.common.shell import host_process, sandbox_keeper
from codeteam.common.shell.command import CommandResult, command_environment
from codeteam.common.shell.processes import ShellProcesses, kill_process_group
from codeteam.common.shell.sandbox import HOME_CACHE_DIRS, is_sandbox_available, nested_sandbox_argv, sandboxed_argv

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
    """Метка в очереди ответов: процесс-хозяин или сторож завершился."""


_HOST_GONE = _HostGone()


class CommandHost:
    """
    Хозяин команд одного агента: при первой команде запускает песочницу со сторожем и процессом-хозяином
    и выполняет через хозяина команды. Команды можно выполнять одновременно из разных потоков.
    """

    def __init__(self, *, write_roots: tuple[Path, ...], processes: ShellProcesses) -> None:
        """
        Запоминает права песочницы и учёт фоновых процессов агента; если песочница есть, учёт отбирает
        свои процессы через этого хозяина.

            write_roots: папки, куда командам разрешена запись; несуществующие создаются при запуске хозяина.
            processes: учёт фоновых процессов агента: при падении хозяина все они останавливаются.
        """
        self._write_roots = write_roots
        self._processes = processes
        self._lock = threading.Lock()
        self._connection: _HostConnection | None = None
        # группы процессов команд, результат которых ещё ждут
        self._running_lock = threading.Lock()
        self._running_group_ids: set[int] = set()
        if is_sandbox_available():
            processes.use_sandbox(sandbox = self)

    def run(self, *, command: str, working_dir: str, timeout_seconds: int) -> CommandResult:
        """
        Выполняет команду bash; по истечении времени снимает её группу процессов.
        Фоновые процессы завершившейся команды продолжают работать в её группе.

            command: команда bash.
            working_dir: папка запуска.
            timeout_seconds: предел времени, секунды.

        Возвращает: Код возврата, вывод команды, коды её последней цепочки и номер последнего
            фонового процесса. Падение хозяина поднимает CommandHostRestarted.
        """
        connection = self._current_connection()
        request_id, replies = connection.submit(command = command, working_dir = working_dir)
        started = replies.get()
        if started is _HOST_GONE:
            self._restart(connection = connection, process_group_id = None)

        process_group_id = started[host_process.PROCESS_GROUP_ID_FIELD]
        with self._running_lock:
            self._running_group_ids.add(process_group_id)
        try:
            finished = replies.get(timeout = timeout_seconds)
            timed_out = False
        except queue.Empty:
            kill_process_group(process_group_id = process_group_id)
            finished = _get_or_none(replies = replies, timeout_seconds = KILLED_COMMAND_WAIT_SECONDS)
            timed_out = True
        finally:
            connection.forget(request_id = request_id)
            with self._running_lock:
                self._running_group_ids.discard(process_group_id)

        if finished is _HOST_GONE:
            self._restart(connection = connection, process_group_id = process_group_id)

        output = "" if finished is None else finished[host_process.OUTPUT_FIELD]
        if timed_out:
            return CommandResult(
                exit_code = None,
                output = output,
                pipe_exit_codes = (),
                process_group_id = process_group_id,
                background_process_id = None,
            )

        return CommandResult(
            exit_code = finished[host_process.EXIT_CODE_FIELD],
            output = output,
            pipe_exit_codes = tuple(finished[host_process.PIPE_EXIT_CODES_FIELD]),
            process_group_id = process_group_id,
            background_process_id = finished[host_process.BACKGROUND_PROCESS_ID_FIELD],
        )

    def running_command_group_ids(self) -> set[int]:
        """
        Перечисляет группы процессов команд, которые сейчас выполняются: их результат ещё ждут.

        Возвращает: Номера групп.
        """
        with self._running_lock:
            return set(self._running_group_ids)

    def own_process_ids(self, *, process_ids: list[int]) -> list[int] | None:
        """
        Отбирает номера процессов, которые работают в песочнице агента, кроме сторожа и хозяина.

            process_ids: номера процессов.

        Возвращает: Свои номера; пустой список, если песочница ещё не запускалась; None, если сторож
            завершился и песочницу проверить нельзя.
        """
        connection = self._connection
        if connection is None:
            return []

        return connection.ask_keeper(action = sandbox_keeper.MEMBERS_ACTION, process_ids = process_ids)

    def kill_own_processes(self, *, process_ids: list[int]) -> list[int] | None:
        """
        Снимает группы процессов песочницы агента с этими номерами; чужие процессы не трогает.

            process_ids: номера процессов.

        Возвращает: Номера, группы которых сняты; пустой список, если песочница ещё не запускалась;
            None, если сторож завершился.
        """
        connection = self._connection
        if connection is None:
            return []

        return connection.ask_keeper(action = sandbox_keeper.KILL_ACTION, process_ids = process_ids)

    def close(self) -> None:
        """
        Останавливает сторожа: он снимает хозяина и все процессы песочницы.
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
        Создаёт недостающие папки записи и запускает в песочнице сторожа с процессом-хозяином.

        Возвращает: Соединение со сторожем.
        """
        for root in (*self._write_roots, *HOME_CACHE_DIRS):
            if not root.exists():
                root.mkdir(parents = True)

        host_argv = nested_sandbox_argv(
            argv = [sys.executable, "-I", host_process.__file__],
            write_roots = self._write_roots,
        )
        keeper_options = [sandbox_keeper.SANDBOXED_OPTION] if is_sandbox_available() else []
        argv = sandboxed_argv(
            argv = [sys.executable, "-I", sandbox_keeper.__file__, *keeper_options, *host_argv],
            write_roots = self._write_roots,
        )

        return _HostConnection(argv = argv)

    def _restart(self, *, connection: "_HostConnection", process_group_id: int | None) -> None:
        """
        Перезапускает упавшего хозяина: снимает группу текущей команды и все фоновые процессы агента.
        Пока сторож жив, новый хозяин запускается в той же песочнице; без сторожа — новая песочница.

            connection: соединение с упавшим хозяином.
            process_group_id: группа текущей команды; None, если команда не успела запуститься.

        Поднимает CommandHostRestarted.
        """
        if process_group_id is not None:
            kill_process_group(process_group_id = process_group_id)

        with self._lock:
            # хозяина уже перезапустил другой вызов
            if self._connection is connection and not connection.is_alive():
                logger.warning("процесс-хозяин команд агента упал: перезапуск, фоновые процессы агента остановлены")
                self._processes.kill_all()
                if connection.is_keeper_alive():
                    connection.restart_host()
                else:
                    connection.close()
                    self._connection = self._start_connection()

        raise CommandHostRestarted("процесс-хозяин команд перезапущен, фоновые процессы агента остановлены")


class _HostConnection:
    """
    Соединение со сторожем песочницы: запросы процессу-хозяину и сторожу, раздача ответов ждущим вызовам.
    """

    def __init__(self, *, argv: list[str]) -> None:
        """
        Запускает сторожа с процессом-хозяином и поток чтения их ответов.

            argv: запуск сторожа, уже под песочницей.
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
        self._keeper_replies: dict[int, queue.Queue] = {}
        self._next_request_id = 0
        # хозяин завершился: новые команды сразу получают метку _HOST_GONE, пока сторож не запустит нового
        self._is_host_gone = False
        # сторож закрыл вывод: новые запросы сразу получают метку _HOST_GONE
        self._is_keeper_gone = False
        threading.Thread(target = self._read_replies, daemon = True).start()

    def is_alive(self) -> bool:
        """
        Проверяет, работают ли сторож и процесс-хозяин.

        Возвращает: True, если сторож не завершился и хозяин не падал после последнего запуска.
        """
        with self._lock:
            return self.is_keeper_alive() and not self._is_host_gone

    def is_keeper_alive(self) -> bool:
        """
        Проверяет, работает ли сторож.

        Возвращает: True, если процесс сторожа не завершился и не закрыл вывод.
        """
        return self._process.poll() is None and not self._is_keeper_gone

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
            if self._is_host_gone or self._is_keeper_gone:
                replies.put(_HOST_GONE)
                return request_id, replies

            if not self._write(message = {host_process.REQUEST_ID_FIELD: request_id, **request}):
                replies.put(_HOST_GONE)

        return request_id, replies

    def ask_keeper(self, *, action: str, process_ids: list[int]) -> list[int] | None:
        """
        Отправляет действие сторожу и ждёт ответа.

            action: действие сторожа.
            process_ids: номера процессов для действия.

        Возвращает: Номера процессов из ответа сторожа; None, если сторож завершился.
        """
        replies: queue.Queue = queue.Queue()
        with self._lock:
            request_id = self._next_request_id
            self._next_request_id += 1
            if self._is_keeper_gone:
                return None

            self._keeper_replies[request_id] = replies
            sent = self._write(message = {
                sandbox_keeper.ACTION_FIELD: action,
                sandbox_keeper.KEEPER_REQUEST_ID_FIELD: request_id,
                sandbox_keeper.PROCESS_IDS_FIELD: process_ids,
            })

        reply = replies.get() if sent else _HOST_GONE
        with self._lock:
            self._keeper_replies.pop(request_id, None)
        if reply is _HOST_GONE:
            return None

        return reply[sandbox_keeper.PROCESS_IDS_FIELD]

    def restart_host(self) -> None:
        """
        Просит сторожа запустить нового процесса-хозяина в той же песочнице.
        """
        if self.ask_keeper(action = sandbox_keeper.RESTART_HOST_ACTION, process_ids = []) is None:
            return

        with self._lock:
            self._is_host_gone = False

    def forget(self, *, request_id: int) -> None:
        """
        Перестаёт ждать ответы на запрос: поздний ответ отбрасывается.

            request_id: номер запроса.
        """
        with self._lock:
            self._replies.pop(request_id, None)

    def close(self) -> None:
        """
        Закрывает ввод сторожа и ждёт его завершения; не дождавшись, снимает его.
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

    def _write(self, *, message: dict) -> bool:
        """
        Пишет запрос сторожу строкой JSON; вызывается под self._lock.

            message: запрос.

        Возвращает: True, если запрос записан; False, если сторож закрыл ввод.
        """
        try:
            self._process.stdin.write(json.dumps(message) + "\n")
            self._process.stdin.flush()
        except (BrokenPipeError, ValueError):
            return False

        return True

    def _read_replies(self) -> None:
        """
        Читает ответы хозяина и сторожа и раздаёт их по очередям запросов. О падении хозяина кладёт метку
        _HOST_GONE во все очереди команд; когда сторож завершился — во все очереди.
        """
        for line in self._process.stdout:
            reply = json.loads(line)
            event = reply.get(sandbox_keeper.EVENT_FIELD)
            with self._lock:
                if event == sandbox_keeper.HOST_GONE_EVENT:
                    self._is_host_gone = True
                    for replies in self._replies.values():
                        replies.put(_HOST_GONE)
                    continue

                if event == sandbox_keeper.REPLY_EVENT:
                    replies = self._keeper_replies.get(reply[sandbox_keeper.KEEPER_REQUEST_ID_FIELD])
                else:
                    replies = self._replies.get(reply[host_process.REQUEST_ID_FIELD])
            if replies is not None:
                replies.put(reply)

        with self._lock:
            self._is_keeper_gone = True
            self._is_host_gone = True
            for replies in (*self._replies.values(), *self._keeper_replies.values()):
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

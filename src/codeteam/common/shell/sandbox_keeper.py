"""Сторож песочницы агента: первый процесс в песочнице, держит её до конца работы агента.

Запуск: python -I sandbox_keeper.py [SANDBOXED_OPTION] <запуск хозяина команд>

Запускает хозяина команд (host_process.py), передаёт ему строки из stdin, его ответы пишет в stdout без
изменений. Строки с полем ACTION_FIELD выполняет сам и отвечает строкой с полем EVENT_FIELD:
- MEMBERS_ACTION — какие из номеров процессов работают в песочнице агента: сигнал 0 ядро пропускает только
  процессам этой песочницы и вложенных в неё;
- KILL_ACTION — снять группы процессов песочницы с этими номерами: чужим процессам ядро сигнал не пропустит;
- RESTART_HOST_ACTION — запустить нового хозяина команд после падения прежнего.
Когда хозяин завершился, пишет строку с событием HOST_GONE_EVENT. Когда stdin закрылся, снимает хозяина,
а в песочнице — все её процессы, и завершается. Без песочницы (нет SANDBOXED_OPTION) номера процессов не
проверяет: в ответах на MEMBERS_ACTION и KILL_ACTION их нет.

Процесс называется KEEPER_PROCESS_NAME: команды агента вроде pkill -f python его не находят.
Использует только стандартную библиотеку: песочница ставится до его запуска.
"""

import json
import os
import signal
import subprocess
import sys
import threading

# Имя процесса сторожа.
KEEPER_PROCESS_NAME = "codeteam-sandbox-keeper"

# Признак запуска в песочнице: первый аргумент сторожа.
SANDBOXED_OPTION = "--sandboxed"

# Поля запроса сторожу: действие, номер запроса, номера процессов.
ACTION_FIELD = "keeper_action"
KEEPER_REQUEST_ID_FIELD = "keeper_request_id"
PROCESS_IDS_FIELD = "process_ids"

# Действия сторожа: свои процессы среди номеров, снятие групп процессов, новый хозяин команд.
MEMBERS_ACTION = "members"
KILL_ACTION = "kill"
RESTART_HOST_ACTION = "restart_host"

# Поле события сторожа и его значения: ответ на запрос, хозяин команд завершился.
EVENT_FIELD = "keeper_event"
REPLY_EVENT = "reply"
HOST_GONE_EVENT = "host_gone"

# Сигналы остановки, которые сторож пропускает: команды агента вроде pkill его не снимают.
IGNORED_STOP_SIGNALS = (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)

_output_lock = threading.Lock()


def main() -> None:
    """
    Запускает хозяина команд и выполняет строки из stdin, пока stdin не закроется.
    """
    if sys.orig_argv[0] != KEEPER_PROCESS_NAME:
        os.execv(sys.executable, [KEEPER_PROCESS_NAME, *sys.orig_argv[1:]])

    for stop_signal in IGNORED_STOP_SIGNALS:
        signal.signal(stop_signal, _ignore_signal)

    sandboxed = sys.argv[1] == SANDBOXED_OPTION
    host_argv = sys.argv[2:] if sandboxed else sys.argv[1:]
    host = _start_host(host_argv = host_argv)
    for line in sys.stdin:
        request = json.loads(line)
        action = request.get(ACTION_FIELD)
        if action is None:
            _pass_to_host(host = host, line = line)
            continue

        process_ids: list[int] = []
        if action == RESTART_HOST_ACTION:
            host = _start_host(host_argv = host_argv)
        elif sandboxed and action == MEMBERS_ACTION:
            process_ids = [
                process_id
                for process_id in request[PROCESS_IDS_FIELD]
                if _is_member(process_id = process_id, host = host)
            ]
        elif sandboxed and action == KILL_ACTION:
            process_ids = [
                process_id
                for process_id in request[PROCESS_IDS_FIELD]
                if _kill_group_of(process_id = process_id, host = host)
            ]

        _send(line = json.dumps({
            EVENT_FIELD: REPLY_EVENT,
            KEEPER_REQUEST_ID_FIELD: request[KEEPER_REQUEST_ID_FIELD],
            PROCESS_IDS_FIELD: process_ids,
        }) + "\n")

    _stop(host = host, sandboxed = sandboxed)


def _ignore_signal(signal_number: int, frame: object) -> None:
    """
    Пропускает сигнал остановки.

        signal_number: номер сигнала.
        frame: кадр стека в момент сигнала.
    """


def _start_host(*, host_argv: list[str]) -> subprocess.Popen:
    """
    Запускает хозяина команд в своей группе процессов и поток, который передаёт его ответы в stdout.

        host_argv: запуск хозяина команд.

    Возвращает: Процесс хозяина.
    """
    host = subprocess.Popen(
        host_argv,
        stdin = subprocess.PIPE,
        stdout = subprocess.PIPE,
        start_new_session = True,
        text = True,
        encoding = "utf-8",
    )
    threading.Thread(target = _pass_from_host, kwargs = {"host": host}, daemon = True).start()

    return host


def _pass_to_host(*, host: subprocess.Popen, line: str) -> None:
    """
    Передаёт строку хозяину команд; упавшему хозяину не передаёт: о его падении сообщает _pass_from_host.

        host: процесс хозяина.
        line: строка запроса.
    """
    try:
        host.stdin.write(line)
        host.stdin.flush()
    except (BrokenPipeError, ValueError):
        pass


def _pass_from_host(*, host: subprocess.Popen) -> None:
    """
    Передаёт ответы хозяина команд в stdout; когда хозяин закрыл вывод, пишет событие HOST_GONE_EVENT.

        host: процесс хозяина.
    """
    for line in host.stdout:
        _send(line = line)

    host.wait()
    _send(line = json.dumps({EVENT_FIELD: HOST_GONE_EVENT}) + "\n")


def _is_member(*, process_id: int, host: subprocess.Popen) -> bool:
    """
    Проверяет, работает ли процесс в песочнице агента: сигнал 0 проходит только процессам этой песочницы.

        process_id: номер процесса.
        host: процесс хозяина: он и сторож своими не считаются.

    Возвращает: True, если процесс в песочнице и это не сторож и не хозяин.
    """
    if process_id in (os.getpid(), host.pid):
        return False

    try:
        os.kill(process_id, 0)
    except (ProcessLookupError, PermissionError):
        return False

    return True


def _kill_group_of(*, process_id: int, host: subprocess.Popen) -> bool:
    """
    Снимает группу процессов песочницы, в которой работает процесс; если это группа сторожа или хозяина —
    только сам процесс.

        process_id: номер процесса.
        host: процесс хозяина.

    Возвращает: True, если процесс в песочнице агента и сигнал отправлен.
    """
    if not _is_member(process_id = process_id, host = host):
        return False

    try:
        process_group_id = os.getpgid(process_id)
        if process_group_id in (os.getpgid(0), host.pid):
            os.kill(process_id, signal.SIGKILL)
        else:
            os.killpg(process_group_id, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        # PermissionError: на macOS так отвечает группа из одних завершённых процессов
        pass

    return True


def _stop(*, host: subprocess.Popen, sandboxed: bool) -> None:
    """
    Снимает хозяина команд, а в песочнице — все её процессы.

        host: процесс хозяина.
        sandboxed: сторож работает в песочнице.
    """
    if sandboxed:
        # сигнал всем процессам, которым он разрешён: в песочнице это только её процессы
        os.kill(-1, signal.SIGKILL)
        return

    try:
        os.killpg(host.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def _send(*, line: str) -> None:
    """
    Пишет строку в stdout.

        line: строка с переводом строки в конце.
    """
    with _output_lock:
        sys.stdout.write(line)
        sys.stdout.flush()


if __name__ == "__main__":
    main()

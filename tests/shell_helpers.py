"""Общие действия тестов команд оболочки: проверка и ожидание процессов и портов, тестовый сервер,
сторожа песочниц."""

import os
import shlex
import socket
import time

import psutil
import pytest

from codeteam.common.shell.sandbox import is_sandbox_available
from codeteam.common.shell.sandbox_keeper import KEEPER_PROCESS_NAME

# Сколько ждать исчезновения снятого процесса, секунды.
PROCESS_GONE_TIMEOUT_SECONDS = 5

# Пауза между проверками процесса, секунды.
PROCESS_POLL_SECONDS = 0.05

# Тест только там, где есть песочница: свои процессы отбирает она.
requires_sandbox = pytest.mark.skipif(not is_sandbox_available(), reason = "нужна песочница: macOS или Linux с Landlock")

# Аргумент тестового сервера: уйти в фон в новой сессии.
DETACHED_ARGUMENT = "detached"

# Программа тестового сервера: слушает порт из первого аргумента и отвечает ошибкой 500, номер своего
# процесса пишет в вывод. С аргументом DETACHED_ARGUMENT сначала уходит в фон в новой сессии: двойной fork
# и setsid, родители завершаются.
ERROR_PAGE_SERVER_SCRIPT = f"""
import http.server
import os
import sys

if sys.argv[2:] == ["{DETACHED_ARGUMENT}"]:
    if os.fork():
        os._exit(0)
    os.setsid()
    if os.fork():
        os._exit(0)


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(500)
        self.end_headers()

    def log_message(self, format, *args):
        pass


server = http.server.HTTPServer(("127.0.0.1", int(sys.argv[1])), Handler)
print(os.getpid(), flush = True)
os.close(1)
os.close(2)
server.serve_forever()
"""


def free_port() -> int:
    """
    Находит порт на 127.0.0.1, который никто не слушает.

    Возвращает: Номер порта.
    """
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def error_page_server_command(*, port: int, detached: bool) -> str:
    """
    Собирает команду bash, которая запускает сервер ERROR_PAGE_SERVER_SCRIPT.

        port: порт сервера.
        detached: сервер уходит в фон в новой сессии; иначе команда запускает его в фоне через &.

    Возвращает: Команду bash; её вывод — номер процесса сервера.
    """
    server = f"python3 -c {shlex.quote(ERROR_PAGE_SERVER_SCRIPT)} {port}"
    if detached:
        return f"{server} {DETACHED_ARGUMENT}"

    return f"{server} &"


def keeper_process_ids() -> list[int]:
    """
    Находит сторожей песочниц, запущенных этим процессом.

    Возвращает: Номера процессов сторожей.
    """
    process_ids = []
    for child in psutil.Process().children():
        try:
            if child.cmdline()[:1] == [KEEPER_PROCESS_NAME]:
                process_ids.append(child.pid)
        except psutil.Error:
            continue

    return process_ids


def is_process_alive(*, process_id: int) -> bool:
    """
    Проверяет, работает ли процесс.

        process_id: номер процесса.

    Возвращает: True, если процесс есть.
    """
    try:
        os.kill(process_id, 0)
    except ProcessLookupError:
        return False

    return True


def wait_process_gone(*, process_id: int) -> bool:
    """
    Ждёт исчезновения процесса не дольше PROCESS_GONE_TIMEOUT_SECONDS.

        process_id: номер процесса.

    Возвращает: True, если процесс исчез.
    """
    deadline = time.monotonic() + PROCESS_GONE_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if not is_process_alive(process_id = process_id):
            return True
        time.sleep(PROCESS_POLL_SECONDS)

    return False


def wait_process_group_gone(*, process_group_id: int) -> bool:
    """
    Ждёт исчезновения всех процессов группы не дольше PROCESS_GONE_TIMEOUT_SECONDS.

        process_group_id: номер группы процессов.

    Возвращает: True, если в группе не осталось процессов.
    """
    deadline = time.monotonic() + PROCESS_GONE_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        try:
            os.killpg(process_group_id, 0)
        except ProcessLookupError:
            return True
        time.sleep(PROCESS_POLL_SECONDS)

    return False


def wait_port_open(*, port: int) -> bool:
    """
    Ждёт, пока порт на 127.0.0.1 начнёт принимать соединения, не дольше PROCESS_GONE_TIMEOUT_SECONDS.

        port: порт.

    Возвращает: True, если порт открылся.
    """
    deadline = time.monotonic() + PROCESS_GONE_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout = PROCESS_POLL_SECONDS):
                return True
        except OSError:
            time.sleep(PROCESS_POLL_SECONDS)

    return False

"""Процесс-хозяин команд агента: работает внутри песочницы и выполняет команды bash агента.

Читает запросы построчно в JSON из stdin, каждую команду выполняет в отдельном потоке как `bash -c`
в своей группе процессов и пишет ответы построчно в JSON в stdout: сначала номер группы команды,
по завершении — код возврата, вывод и коды цепочки через |. Все команды агента — дочерние процессы
хозяина и потому в одной песочнице: сигналы между ними разрешены.

Запускается как отдельная программа и использует только стандартную библиотеку: песочница ставится
до его запуска.
"""

import json
import os
import signal
import subprocess
import sys
import threading

# Поля запроса: номер запроса, команда bash, папка запуска.
REQUEST_ID_FIELD = "request_id"
COMMAND_FIELD = "command"
WORKING_DIR_FIELD = "working_dir"

# Поле вида ответа и его значения: команда запущена, команда завершилась.
EVENT_FIELD = "event"
STARTED_EVENT = "started"
FINISHED_EVENT = "finished"

# Поля ответов: номер группы процессов команды, код возврата, вывод, коды цепочки через |.
PROCESS_GROUP_ID_FIELD = "process_group_id"
EXIT_CODE_FIELD = "exit_code"
OUTPUT_FIELD = "output"
PIPE_EXIT_CODES_FIELD = "pipe_exit_codes"

# Строка после команды: отправляет коды команд последней цепочки через | в канал с номером
# {status_fd} и завершает bash с кодом самой команды.
PIPE_STATUS_SUFFIX = (
    '\n__ct_pipe_status="${{PIPESTATUS[*]}}" __ct_exit_code=$?; '
    'echo "$__ct_pipe_status" >&{status_fd}; exit "$__ct_exit_code"'
)

# Сколько байт кодов цепочки читать из канала: коды занимают одну короткую строку.
PIPE_STATUS_READ_LIMIT = 4096

# Сигналы остановки, которые хозяин пропускает: команда агента вроде pkill -f python не снимает его.
IGNORED_STOP_SIGNALS = (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)

_output_lock = threading.Lock()


def main() -> None:
    """
    Выполняет запросы из stdin, пока stdin не закроется.
    """
    for stop_signal in IGNORED_STOP_SIGNALS:
        # обработчик, а не SIG_IGN: при запуске команды обработчики сбрасываются,
        # и команды агента останавливаются этими сигналами как обычно
        signal.signal(stop_signal, _ignore_signal)

    for line in sys.stdin:
        request = json.loads(line)
        threading.Thread(target = _run_request, kwargs = {"request": request}, daemon = True).start()


def _ignore_signal(signal_number: int, frame: object) -> None:
    """
    Пропускает сигнал остановки.

        signal_number: номер сигнала.
        frame: кадр стека в момент сигнала.
    """


def _run_request(*, request: dict) -> None:
    """
    Выполняет команду запроса и отправляет ответы: о запуске и о завершении.

        request: запрос: номер, команда bash, папка запуска.
    """
    request_id = request[REQUEST_ID_FIELD]
    status_read_fd, status_write_fd = os.pipe()
    script = request[COMMAND_FIELD] + PIPE_STATUS_SUFFIX.format(status_fd = status_write_fd)
    process = subprocess.Popen(
        ["bash", "-c", script],
        cwd = request[WORKING_DIR_FIELD],
        stdin = subprocess.DEVNULL,
        stdout = subprocess.PIPE,
        stderr = subprocess.STDOUT,
        start_new_session = True,
        pass_fds = (status_write_fd,),
    )
    os.close(status_write_fd)
    _send(message = {REQUEST_ID_FIELD: request_id, EVENT_FIELD: STARTED_EVENT, PROCESS_GROUP_ID_FIELD: process.pid})

    raw_output, _ = process.communicate()
    _send(
        message = {
            REQUEST_ID_FIELD: request_id,
            EVENT_FIELD: FINISHED_EVENT,
            EXIT_CODE_FIELD: process.returncode,
            OUTPUT_FIELD: raw_output.decode("utf-8", errors = "replace"),
            PIPE_EXIT_CODES_FIELD: _read_pipe_exit_codes(status_read_fd = status_read_fd),
        }
    )


def _read_pipe_exit_codes(*, status_read_fd: int) -> list[int]:
    """
    Читает коды команд цепочки из канала и закрывает его.

    Канал читается без ожидания: команда уже завершилась, а её фоновый процесс может держать канал
    открытым.

        status_read_fd: конец канала для чтения.

    Возвращает: Коды команд цепочки; пустые, если команда их не отправила.
    """
    os.set_blocking(status_read_fd, False)
    try:
        raw_status = os.read(status_read_fd, PIPE_STATUS_READ_LIMIT)
    except BlockingIOError:
        raw_status = b""
    finally:
        os.close(status_read_fd)

    return [int(code) for code in raw_status.decode("ascii", errors = "replace").split() if code.isdigit()]


def _send(*, message: dict) -> None:
    """
    Пишет ответ строкой JSON в stdout.

        message: ответ.
    """
    with _output_lock:
        sys.stdout.write(json.dumps(message, ensure_ascii = False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()

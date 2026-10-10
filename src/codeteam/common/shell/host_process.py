"""Процесс-хозяин команд агента: работает внутри песочницы и выполняет команды bash агента.

Читает запросы построчно в JSON из stdin, каждую команду выполняет в отдельном потоке как `bash -c`
в своей группе процессов и пишет ответы построчно в JSON в stdout: сначала номер группы команды,
по завершении — код возврата, вывод, коды цепочки через | и номер последнего фонового процесса. Все команды агента — дочерние процессы
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

# Поля ответов: номер группы процессов команды, код возврата, вывод, коды цепочки через |,
# номер последнего фонового процесса команды.
PROCESS_GROUP_ID_FIELD = "process_group_id"
EXIT_CODE_FIELD = "exit_code"
OUTPUT_FIELD = "output"
PIPE_EXIT_CODES_FIELD = "pipe_exit_codes"
BACKGROUND_PROCESS_ID_FIELD = "background_process_id"

# Строка после команды: отправляет в канал с номером {status_fd} две строки — коды команд последней
# цепочки через | и номер последнего фонового процесса ($!), — и завершает bash с кодом самой команды.
STATUS_SUFFIX = (
    '\n__ct_pipe_status="${{PIPESTATUS[*]}}" __ct_exit_code=$?; '
    'echo "$__ct_pipe_status" >&{status_fd}; echo "$!" >&{status_fd}; exit "$__ct_exit_code"'
)

# Сколько байт итога команды читать из канала: итог занимает две короткие строки.
STATUS_READ_LIMIT = 4096

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
    script = request[COMMAND_FIELD] + STATUS_SUFFIX.format(status_fd = status_write_fd)
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
    pipe_exit_codes, background_process_id = _read_status(status_read_fd = status_read_fd)
    _send(
        message = {
            REQUEST_ID_FIELD: request_id,
            EVENT_FIELD: FINISHED_EVENT,
            EXIT_CODE_FIELD: process.returncode,
            OUTPUT_FIELD: raw_output.decode("utf-8", errors = "replace"),
            PIPE_EXIT_CODES_FIELD: pipe_exit_codes,
            BACKGROUND_PROCESS_ID_FIELD: background_process_id,
        }
    )


def _read_status(*, status_read_fd: int) -> tuple[list[int], int | None]:
    """
    Читает из канала итог команды, отправленный строкой STATUS_SUFFIX, и закрывает канал.

    Канал читается без ожидания: команда уже завершилась, а её фоновый процесс может держать канал
    открытым.

        status_read_fd: конец канала для чтения.

    Возвращает:
        Коды команд цепочки и номер последнего фонового процесса. Коды пустые и номер None, если
        команда их не отправила; номер None, если команда ничего не запускала в фоне.
    """
    os.set_blocking(status_read_fd, False)
    try:
        raw_status = os.read(status_read_fd, STATUS_READ_LIMIT)
    except BlockingIOError:
        raw_status = b""
    finally:
        os.close(status_read_fd)

    status_lines = raw_status.decode("ascii", errors = "replace").split("\n")
    pipe_line = status_lines[0]
    background_line = status_lines[1].strip() if len(status_lines) > 1 else ""
    pipe_exit_codes = [int(code) for code in pipe_line.split() if code.isdigit()]
    background_process_id = int(background_line) if background_line.isdigit() else None

    return pipe_exit_codes, background_process_id


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

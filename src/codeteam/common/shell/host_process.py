"""Процесс-хозяин команд агента: работает внутри песочницы и выполняет команды bash агента.

Читает запросы построчно в JSON из stdin, каждую команду выполняет в отдельном потоке как `bash -c`
в своей группе процессов и пишет ответы построчно в JSON в stdout: сначала номер группы команды,
по завершении — код возврата, вывод, коды цепочки через | и номер последнего фонового процесса.
Команда завершена, когда завершилась её оболочка: фоновые процессы команды хозяин не ждёт. Все команды
агента — дочерние процессы хозяина и потому в одной песочнице: сигналы между ними разрешены.

Запускается как отдельная программа и использует только стандартную библиотеку: песочница ставится
до его запуска.
"""

import json
import os
import select
import signal
import subprocess
import sys
import threading
import time

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

# После завершения оболочки вывод дочитывается, пока не закроется или не замолчит на
# OUTPUT_IDLE_SECONDS, но не дольше OUTPUT_DRAIN_LIMIT_SECONDS: фоновые процессы команды могут
# держать вывод открытым. Значения взяты из oh-my-pi (crates/pi-shell/src/shell.rs).
OUTPUT_IDLE_SECONDS = 0.25
OUTPUT_DRAIN_LIMIT_SECONDS = 2

# Как часто проверять, завершилась ли оболочка, пока вывод молчит, секунды.
EXIT_POLL_SECONDS = 0.05

# Сколько байт вывода читать за раз.
OUTPUT_READ_SIZE = 65536

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

    raw_output = _collect_output(process = process)
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


def _collect_output(*, process: subprocess.Popen) -> bytes:
    """
    Читает вывод команды, пока работает её оболочка, и дочитывает после её завершения: до закрытия
    вывода, затишья на OUTPUT_IDLE_SECONDS, не дольше OUTPUT_DRAIN_LIMIT_SECONDS. Затем закрывает
    вывод и ждёт код возврата оболочки.

        process: оболочка команды с выводом в канал.

    Возвращает: Вывод команды.
    """
    output_fd = process.stdout.fileno()
    chunks: list[bytes] = []
    exit_time: float | None = None
    last_output_time = 0.0
    while True:
        now = time.monotonic()
        if exit_time is None and process.poll() is not None:
            exit_time = now
            last_output_time = now

        if exit_time is None:
            wait_seconds = EXIT_POLL_SECONDS
        else:
            idle_deadline = last_output_time + OUTPUT_IDLE_SECONDS
            drain_deadline = exit_time + OUTPUT_DRAIN_LIMIT_SECONDS
            wait_seconds = min(idle_deadline, drain_deadline) - now
            if wait_seconds <= 0:
                break

        readable, _, _ = select.select([output_fd], [], [], wait_seconds)
        if not readable:
            continue

        chunk = os.read(output_fd, OUTPUT_READ_SIZE)
        # вывод закрыли все процессы команды
        if not chunk:
            break

        chunks.append(chunk)
        last_output_time = time.monotonic()

    process.stdout.close()
    process.wait()

    return b"".join(chunks)


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

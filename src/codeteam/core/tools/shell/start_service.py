"""
Инструмент агента start_service: запуск долго работающей программы в фоне с ожиданием готовности.

Зачем отдельный инструмент: сервер, запущенный в bash через &, возвращает код 0 сразу, даже если
программа тут же упала. Ошибку старта агент видит, только если сам прочитает лог, а до этого
обращается к неработающему приложению. По журналам разработчика такой запуск занимал десятки шагов.
start_service ждёт готовности по порту или строке лога и сразу показывает ошибку старта.
"""

import re
import shlex
import socket
import time
from pathlib import Path

from langchain_core.tools import BaseTool, StructuredTool, ToolException
from pydantic import BaseModel, Field

from codeteam.common.shell import CommandHost, CommandHostRestarted, ShellProcesses
from codeteam.common.shell.processes import is_process_group_alive
from codeteam.core.agent.workspace import Workspace
from codeteam.core.tools.shell.bash import BASH_HOST_RESTARTED_REFUSAL
from codeteam.core.tools.shell._internal.output_file import new_output_file

# Имя инструмента запуска служб.
START_SERVICE_TOOL_NAME = "start_service"

# Предел ожидания готовности, если агент его не задал, секунды.
READY_TIMEOUT_SECONDS = 30

# Наибольший предел ожидания готовности, который может задать агент, секунды.
READY_TIMEOUT_LIMIT_SECONDS = 120

# Предел времени команды запуска: она только отправляет службу в фон, секунды.
LAUNCH_TIMEOUT_SECONDS = 10

# Пауза между проверками готовности, секунды.
CHECK_INTERVAL_SECONDS = 0.5

# Сколько ждать, пока остановленная прежняя служба освободит порт, секунды.
PORT_RELEASE_TIMEOUT_SECONDS = 5

# Адрес, на котором проверяется порт службы.
SERVICE_HOST = "127.0.0.1"

# Папка логов служб внутри папки временных файлов проверки CHECK_DIR.
SERVICE_LOG_DIR_NAME = "services"

# Сколько последних строк лога показывать агенту.
LOG_TAIL_LINES = 20

START_SERVICE_DESCRIPTION = """Запускает долго работающую программу (сервер, службу) в фоне и ждёт, пока она будет готова.

Пример: start_service(command = "uv run python app.py", port = 8050)

Команда запускается так же, как в bash: в папке проекта, с теми же правами. Вывод пишется в файл лога.
Готовность проверяется по port (порт открыт на 127.0.0.1) или по log_pattern (в выводе появилась
строка под это регулярное выражение). Укажи хотя бы одно; если указаны оба — ждём оба.
Если служба слушает порт — всегда указывай port: инструмент проверит, что порт свободен.
Повторный запуск с тем же port останавливает прежнюю службу и запускает новую: так перезапускай службу после правки кода.
Служба работает между вызовами и останавливается, когда ты закончишь работу.

Обращайся к службе по 127.0.0.1. Остановить — инструментом stop_process с номером процесса.
Лог читай инструментом read: путь к нему — в ответе."""


class StartServiceArguments(BaseModel):
    """
    Аргументы start_service.
    """

    command: str = Field(
        description = "команда запуска службы, без перенаправления вывода (> файл): вывод в лог пишет сам инструмент"
    )
    port: int | None = Field(default = None, description = "порт, который служба откроет на 127.0.0.1")
    log_pattern: str | None = Field(
        default = None,
        description = "регулярное выражение строки вывода, после которой служба готова",
    )
    timeout_seconds: int | None = Field(
        default = None,
        description = f"сколько ждать готовности в секундах, по умолчанию {READY_TIMEOUT_SECONDS}, не больше {READY_TIMEOUT_LIMIT_SECONDS}",
    )


def build_start_service_tool(*, workspace: Workspace, processes: ShellProcesses, host: CommandHost) -> BaseTool:
    """
    Собирает инструмент запуска служб для рабочего места вызова.

    Запуск на порту, где работает служба, запущенная этим инструментом раньше, останавливает
    прежнюю службу и запускает новую.

        workspace: рабочее место вызова: папка запуска и права записи те же, что у bash.
        processes: учёт фоновых процессов; служба попадает в него, её видит и останавливает stop_process.
        host: хозяин команд агента, общий с bash: служба работает в песочнице агента.

    Возвращает: Инструмент start_service.
    """
    # номер группы процессов службы по её порту
    service_by_port: dict[int, int] = {}

    def start_service(
        *,
        command: str,
        port: int | None = None,
        log_pattern: str | None = None,
        timeout_seconds: int | None = None,
    ) -> str:
        """
        Запускает службу в фоне и ждёт её готовности.

            command: команда запуска службы.
            port: порт, который служба откроет на SERVICE_HOST.
            log_pattern: регулярное выражение строки вывода, после которой служба готова.
            timeout_seconds: предел ожидания готовности, секунды.

        Возвращает:
            Номер процесса и файл лога готовой службы; состояние условий готовности, если служба
            работает, но не стала готовой за отведённое время. Ошибку для агента поднимает ToolException.
        """
        timeout = READY_TIMEOUT_SECONDS if timeout_seconds is None else timeout_seconds
        if not 1 <= timeout <= READY_TIMEOUT_LIMIT_SECONDS:
            raise ToolException(f"Ошибка: timeout_seconds должен быть от 1 до {READY_TIMEOUT_LIMIT_SECONDS}")
        if port is None and not log_pattern:
            raise ToolException(
                "Ошибка: укажи, по чему понять, что служба готова: port — порт, который она откроет "
                "(например port = 8050; обычно этого достаточно), или log_pattern — регулярное выражение "
                "строки, которую служба выводит, когда готова."
            )
        try:
            pattern = re.compile(log_pattern) if log_pattern else None
        except re.error as error:
            raise ToolException(f"Ошибка: log_pattern — неверное регулярное выражение: {error}") from error
        if port is not None and port in service_by_port:
            # прежняя служба на этом порту заменяется новой
            processes.kill_group_of(process_id = service_by_port.pop(port))
            _wait_port_released(port = port)
        if port is not None and _is_port_open(port = port):
            raise ToolException(
                f"Ошибка: порт {port} уже занят другой программой, служба не запущена. "
                f"Запусти службу на другом порту."
            )

        log_path = new_output_file(workspace = workspace, dir_name = SERVICE_LOG_DIR_NAME, prefix = "service_")
        shown_log = workspace.display_path(path = log_path)
        try:
            result = host.run(
                command = f"( {command} ) > {shlex.quote(str(log_path))} 2>&1 &",
                working_dir = str(workspace.project_dir),
                timeout_seconds = LAUNCH_TIMEOUT_SECONDS,
            )
        except CommandHostRestarted as error:
            raise ToolException(BASH_HOST_RESTARTED_REFUSAL) from error
        processes.remember(
            process_group_id = result.process_group_id,
            background_process_id = result.background_process_id,
            command = command,
        )
        if result.exit_code != 0 or result.background_process_id is None:
            raise ToolException(f"Ошибка: служба не запущена.\n{result.output}")

        # номер, который видит агент: процесс службы, запущенный в фоне ($!)
        process_id = result.background_process_id
        # служба работает, пока жив любой процесс её группы, в том числе запущенный в фоне командой службы
        process_group_id = result.process_group_id
        if port is not None:
            service_by_port[port] = process_group_id
        deadline = time.monotonic() + timeout
        while True:
            if _is_ready(port = port, pattern = pattern, log_path = log_path):
                return (
                    f"Служба готова: процесс {process_id}, лог {shown_log}.\n"
                    f"Остановить: stop_process(pid = {process_id}).\n"
                    f"Последние строки лога:\n{_log_tail(log_path = log_path)}"
                )
            if not is_process_group_alive(process_group_id = process_group_id):
                raise ToolException(
                    f"Служба не запустилась — процесс {process_id} завершился. Лог {shown_log}.\n"
                    f"Последние строки лога:\n{_log_tail(log_path = log_path)}"
                )
            if time.monotonic() >= deadline:
                return _not_ready_answer(
                    timeout = timeout,
                    process_id = process_id,
                    port = port,
                    pattern = pattern,
                    log_path = log_path,
                    shown_log = shown_log,
                )
            time.sleep(CHECK_INTERVAL_SECONDS)

    return StructuredTool.from_function(
        func = start_service,
        name = START_SERVICE_TOOL_NAME,
        description = START_SERVICE_DESCRIPTION,
        args_schema = StartServiceArguments,
        handle_tool_error = True,
    )


def build_disabled_start_service_tool(*, refusal: str) -> BaseTool:
    """
    Собирает заглушку start_service: то же имя и описание, но любой запуск получает отказ.

        refusal: текст отказа для агента.

    Возвращает: Инструмент start_service, который ничего не запускает.
    """

    def start_service(
        *,
        command: str,
        port: int | None = None,
        log_pattern: str | None = None,
        timeout_seconds: int | None = None,
    ) -> str:
        """
        Отказывает в запуске службы.

            command: команда запуска службы.
            port: порт службы.
            log_pattern: регулярное выражение строки готовности.
            timeout_seconds: предел ожидания готовности, секунды.

        Возвращает: Ничего не возвращает: отказ для агента поднимает ToolException.
        """
        raise ToolException(refusal)

    return StructuredTool.from_function(
        func = start_service,
        name = START_SERVICE_TOOL_NAME,
        description = START_SERVICE_DESCRIPTION,
        args_schema = StartServiceArguments,
        handle_tool_error = True,
    )


def _is_ready(*, port: int | None, pattern: re.Pattern[str] | None, log_path: Path) -> bool:
    """
    Проверяет готовность службы по указанным условиям.

        port: порт, который должен быть открыт на SERVICE_HOST; None — не проверяется.
        pattern: регулярное выражение строки лога; None — не проверяется.
        log_path: файл лога службы.

    Возвращает: True, если выполнены все указанные условия.
    """
    if port is not None and not _is_port_open(port = port):
        return False
    if pattern is not None and pattern.search(log_path.read_text(encoding = "utf-8", errors = "replace")) is None:
        return False

    return True


def _not_ready_answer(
    *,
    timeout: int,
    process_id: int,
    port: int | None,
    pattern: re.Pattern[str] | None,
    log_path: Path,
    shown_log: str,
) -> str:
    """
    Собирает ответ агенту о службе, которая не стала готовой за отведённое время.

        timeout: предел ожидания готовности, секунды.
        process_id: номер процесса службы.
        port: порт службы; None — не проверялся.
        pattern: регулярное выражение строки лога; None — не проверялось.
        log_path: файл лога службы.
        shown_log: путь к логу в том виде, в каком его видит агент.

    Возвращает: Состояние условий готовности, где искать вывод службы и как её остановить.
    """
    log_text = log_path.read_text(encoding = "utf-8", errors = "replace")
    lines = [f"Процесс {process_id} работает, но за {timeout} с условия готовности не выполнены."]

    if port is not None:
        if _is_port_open(port = port):
            lines.append(f"Порт {port} открыт.")
        else:
            lines.append(f"Порт {port} закрыт.")

    if not log_text:
        lines.append("Лог пуст: если в command есть перенаправление вывода (> файл), вывод ушёл в этот файл — читай его.")
    else:
        if pattern is not None and pattern.search(log_text) is None:
            lines.append("Строка log_pattern в логе не найдена.")
        lines.append(f"Лог {shown_log}.")
        lines.append(f"Последние строки лога:\n{_log_tail(log_path = log_path)}")

    lines.append(f"Остановить: stop_process(pid = {process_id}).")

    return "\n".join(lines)


def _is_port_open(*, port: int) -> bool:
    """
    Проверяет, принимает ли порт соединения на SERVICE_HOST.

        port: порт.

    Возвращает: True, если соединение установлено.
    """
    try:
        with socket.create_connection((SERVICE_HOST, port), timeout = CHECK_INTERVAL_SECONDS):
            return True
    except OSError:
        return False


def _wait_port_released(*, port: int) -> None:
    """
    Ждёт, пока порт перестанет принимать соединения, не дольше PORT_RELEASE_TIMEOUT_SECONDS.

        port: порт.
    """
    deadline = time.monotonic() + PORT_RELEASE_TIMEOUT_SECONDS
    while _is_port_open(port = port) and time.monotonic() < deadline:
        time.sleep(CHECK_INTERVAL_SECONDS)


def _log_tail(*, log_path: Path) -> str:
    """
    Берёт последние строки лога службы.

        log_path: файл лога.

    Возвращает: Последние LOG_TAIL_LINES строк; пометку, если лог пуст.
    """
    lines = log_path.read_text(encoding = "utf-8", errors = "replace").splitlines()
    if not lines:
        return "(лог пуст)"

    return "\n".join(lines[-LOG_TAIL_LINES:])

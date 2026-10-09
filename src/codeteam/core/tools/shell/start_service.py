"""
Инструмент агента start_service: запуск долго работающей программы в фоне с ожиданием готовности.

Зачем отдельный инструмент: сервер, запущенный в bash через &, возвращает код 0 сразу, даже если
программа тут же упала. Ошибку старта агент видит, только если сам прочитает лог, а до этого
обращается к неработающему приложению. По журналам разработчика такой запуск занимал десятки шагов.
start_service ждёт готовности по порту или строке лога и сразу показывает ошибку старта.
"""

import os
import re
import shlex
import socket
import tempfile
import time
from pathlib import Path

from langchain_core.tools import BaseTool, StructuredTool, ToolException
from pydantic import BaseModel, Field

from codeteam.common.shell import CommandHost, CommandHostRestarted, ShellProcesses
from codeteam.common.shell.processes import is_process_group_alive
from codeteam.core.agent.workspace import CHECK_DIR, PathOutsideWorkspace, Workspace
from codeteam.core.tools.shell.bash import BASH_HOST_RESTARTED_REFUSAL

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

Команда запускается так же, как в bash: в папке проекта, с теми же правами. Вывод пишется в файл лога.
Готовность проверяется по port (порт открыт на 127.0.0.1) или по log_pattern (в выводе появилась
строка под это регулярное выражение). Укажи хотя бы одно; если указаны оба — ждём оба.
Если служба слушает порт — всегда указывай port: инструмент проверит, что порт свободен.
Служба работает между вызовами и останавливается, когда ты закончишь работу.

Ответ:
- готово — номер процесса и файл лога;
- порт port уже занят другой программой — ошибка, служба не запускается: выбери другой порт;
- процесс завершился или не стал готов за timeout_seconds — ошибка с последними строками лога.

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
        description = "сколько ждать готовности в секундах, по умолчанию 30, не больше 120",
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
    # номер процесса службы по её порту
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

        Возвращает: Номер процесса и файл лога готовой службы. Ошибку для агента поднимает ToolException.
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

        log_path = _new_log_path(workspace = workspace)
        shown_log = workspace.display_path(path = log_path)
        try:
            result = host.run(
                command = f"( {command} ) > {shlex.quote(str(log_path))} 2>&1 &",
                working_dir = str(workspace.project_dir),
                timeout_seconds = LAUNCH_TIMEOUT_SECONDS,
            )
        except CommandHostRestarted as error:
            raise ToolException(BASH_HOST_RESTARTED_REFUSAL) from error
        processes.remember(process_group_id = result.process_group_id)
        if result.exit_code != 0:
            raise ToolException(f"Ошибка: служба не запущена.\n{result.output}")

        # номер группы процессов службы: группа жива, пока жив любой её процесс, в том числе
        # запущенный в фоне командой службы
        process_id = result.process_group_id
        if port is not None:
            service_by_port[port] = process_id
        deadline = time.monotonic() + timeout
        while True:
            if _is_ready(port = port, pattern = pattern, log_path = log_path):
                return (
                    f"Служба готова: процесс {process_id}, лог {shown_log}.\n"
                    f"Остановить: stop_process(pid = {process_id}).\n"
                    f"Последние строки лога:\n{_log_tail(log_path = log_path)}"
                )
            if not is_process_group_alive(process_group_id = process_id):
                raise ToolException(
                    f"Ошибка: служба не запустилась — процесс {process_id} завершился. Лог {shown_log}.\n"
                    f"Последние строки лога:\n{_log_tail(log_path = log_path)}"
                )
            if time.monotonic() >= deadline:
                raise ToolException(
                    f"Ошибка: служба не готова за {timeout} с, процесс {process_id} работает. Лог {shown_log}.\n"
                    f"Остановить: stop_process(pid = {process_id}).\n"
                    f"Последние строки лога:\n{_log_tail(log_path = log_path)}"
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


def _new_log_path(*, workspace: Workspace) -> Path:
    """
    Создаёт пустой файл лога службы: в папке CHECK_DIR/SERVICE_LOG_DIR_NAME проекта, если туда разрешена
    запись, иначе во временной папке системы.

        workspace: рабочее место вызова.

    Возвращает: Путь файла лога.
    """
    log_dir = workspace.project_dir / CHECK_DIR / SERVICE_LOG_DIR_NAME
    try:
        workspace.resolve_writable(path = str(log_dir))
    except PathOutsideWorkspace:
        log_dir = Path(tempfile.gettempdir())

    log_dir.mkdir(parents = True, exist_ok = True)
    log_descriptor, log_name = tempfile.mkstemp(prefix = "service_", suffix = ".log", dir = log_dir)
    os.close(log_descriptor)

    return Path(log_name)


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

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
import subprocess
import time
from pathlib import Path

from langchain_core.tools import BaseTool, StructuredTool, ToolException
from pydantic import BaseModel, Field

from codeteam.common.shell import CommandHost, CommandHostRestarted, ShellProcesses
from codeteam.common.shell.processes import is_process_group_alive
from codeteam.core.agent.workspace import Workspace
from codeteam.core.tools.shell.common_prompts import HOST_RESTARTED_REFUSAL, TIMEOUT_RANGE_ERROR
from codeteam.core.tools.shell.start_service_prompts import (
    START_SERVICE_COMMAND_DESCRIPTION,
    START_SERVICE_DESCRIPTION,
    START_SERVICE_EMPTY_LOG_NOTE,
    START_SERVICE_EMPTY_LOG_TAIL,
    START_SERVICE_EXITED_ERROR,
    START_SERVICE_LAUNCH_ERROR,
    START_SERVICE_LOG_PATH,
    START_SERVICE_LOG_PATTERN_DESCRIPTION,
    START_SERVICE_LOG_PATTERN_ERROR,
    START_SERVICE_LOG_TAIL,
    START_SERVICE_NO_READY_CONDITION_ERROR,
    START_SERVICE_NOT_READY,
    START_SERVICE_PATTERN_NOT_FOUND,
    START_SERVICE_PORT_BUSY_ERROR,
    START_SERVICE_PORT_CLOSED,
    START_SERVICE_PORT_DESCRIPTION,
    START_SERVICE_PORT_OPEN,
    START_SERVICE_READY,
    START_SERVICE_STOP_HINT,
    START_SERVICE_STOPPED_OWN_NOTE,
    START_SERVICE_TIMEOUT_DESCRIPTION,
)
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

# Предел времени команды lsof, которая ищет процессы на порту, секунды.
LSOF_TIMEOUT_SECONDS = 5

# Адрес, на котором проверяется порт службы.
SERVICE_HOST = "127.0.0.1"

# Папка логов служб внутри папки временных файлов проверки CHECK_DIR.
SERVICE_LOG_DIR_NAME = "services"

# Сколько последних строк лога показывать агенту.
LOG_TAIL_LINES = 20

class StartServiceArguments(BaseModel):
    """
    Аргументы start_service.
    """

    command: str = Field(description = START_SERVICE_COMMAND_DESCRIPTION)
    port: int | None = Field(default = None, description = START_SERVICE_PORT_DESCRIPTION)
    log_pattern: str | None = Field(default = None, description = START_SERVICE_LOG_PATTERN_DESCRIPTION)
    timeout_seconds: int | None = Field(
        default = None,
        description = START_SERVICE_TIMEOUT_DESCRIPTION.format(
            default_seconds = READY_TIMEOUT_SECONDS,
            limit_seconds = READY_TIMEOUT_LIMIT_SECONDS,
        ),
    )


def build_start_service_tool(*, workspace: Workspace, processes: ShellProcesses, host: CommandHost) -> BaseTool:
    """
    Собирает инструмент запуска служб для рабочего места вызова.

    Запуск на порту, занятом процессом агента (запущенным через bash или start_service), останавливает
    этот процесс и запускает службу.

        workspace: рабочее место вызова: папка запуска и права записи те же, что у bash.
        processes: учёт фоновых процессов; служба попадает в него, её видит и останавливает stop_process.
        host: хозяин команд агента, общий с bash: служба работает в песочнице агента.

    Возвращает: Инструмент start_service.
    """
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
            raise ToolException(TIMEOUT_RANGE_ERROR.format(limit = READY_TIMEOUT_LIMIT_SECONDS))
        if port is None and not log_pattern:
            raise ToolException(START_SERVICE_NO_READY_CONDITION_ERROR)
        try:
            pattern = re.compile(log_pattern) if log_pattern else None
        except re.error as error:
            raise ToolException(START_SERVICE_LOG_PATTERN_ERROR.format(error = error)) from error
        stopped_notice = ""
        if port is not None and _is_port_open(port = port):
            stopped_notice = _stop_own_listeners(port = port, processes = processes)
        if port is not None and _is_port_open(port = port):
            raise ToolException(START_SERVICE_PORT_BUSY_ERROR.format(port = port))

        log_path = new_output_file(workspace = workspace, dir_name = SERVICE_LOG_DIR_NAME, prefix = "service_")
        shown_log = workspace.display_path(path = log_path)
        try:
            result = host.run(
                command = f"( {command} ) > {shlex.quote(str(log_path))} 2>&1 &",
                working_dir = str(workspace.project_dir),
                timeout_seconds = LAUNCH_TIMEOUT_SECONDS,
            )
        except CommandHostRestarted as error:
            raise ToolException(HOST_RESTARTED_REFUSAL) from error
        processes.remember(
            process_group_id = result.process_group_id,
            background_process_id = result.background_process_id,
            command = command,
        )
        if result.exit_code != 0 or result.background_process_id is None:
            raise ToolException(stopped_notice + START_SERVICE_LAUNCH_ERROR.format(output = result.output))

        # номер, который видит агент: процесс службы, запущенный в фоне ($!)
        process_id = result.background_process_id
        # служба работает, пока жив любой процесс её группы, в том числе запущенный в фоне командой службы
        process_group_id = result.process_group_id
        deadline = time.monotonic() + timeout
        while True:
            if _is_ready(port = port, pattern = pattern, log_path = log_path):
                return stopped_notice + "\n".join([
                    START_SERVICE_READY.format(process_id = process_id, shown_log = shown_log),
                    START_SERVICE_STOP_HINT.format(process_id = process_id),
                    START_SERVICE_LOG_TAIL.format(log_tail = _log_tail(log_path = log_path)),
                ])
            if not is_process_group_alive(process_group_id = process_group_id):
                raise ToolException(stopped_notice + "\n".join([
                    START_SERVICE_EXITED_ERROR.format(process_id = process_id, shown_log = shown_log),
                    START_SERVICE_LOG_TAIL.format(log_tail = _log_tail(log_path = log_path)),
                ]))
            if time.monotonic() >= deadline:
                return stopped_notice + _not_ready_answer(
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
    lines = [START_SERVICE_NOT_READY.format(process_id = process_id, timeout = timeout)]

    if port is not None:
        if _is_port_open(port = port):
            lines.append(START_SERVICE_PORT_OPEN.format(port = port))
        else:
            lines.append(START_SERVICE_PORT_CLOSED.format(port = port))

    if not log_text:
        lines.append(START_SERVICE_EMPTY_LOG_NOTE)
    else:
        if pattern is not None and pattern.search(log_text) is None:
            lines.append(START_SERVICE_PATTERN_NOT_FOUND)
        lines.append(START_SERVICE_LOG_PATH.format(shown_log = shown_log))
        lines.append(START_SERVICE_LOG_TAIL.format(log_tail = _log_tail(log_path = log_path)))

    lines.append(START_SERVICE_STOP_HINT.format(process_id = process_id))

    return "\n".join(lines)


def _stop_own_listeners(*, port: int, processes: ShellProcesses) -> str:
    """
    Останавливает процессы агента, которые слушают порт, и ждёт, пока порт освободится.

        port: порт службы.
        processes: учёт фоновых процессов агента; чужие процессы не трогаются.

    Возвращает: Строки об остановленных процессах агента; пустую строку, если таких не было.
    """
    stopped_notice = ""
    for listener_id in _port_listener_ids(port = port):
        own_process = processes.process_of(process_id = listener_id)
        if own_process is None:
            continue

        processes.kill_group_of(process_id = listener_id)
        stopped_notice += START_SERVICE_STOPPED_OWN_NOTE.format(
            port = port,
            process_id = own_process.process_id,
            command = own_process.command,
        )

    if stopped_notice:
        _wait_port_released(port = port)

    return stopped_notice


def _port_listener_ids(*, port: int) -> list[int]:
    """
    Находит процессы, которые слушают порт, системной командой lsof.

        port: порт.

    Возвращает: Номера процессов; пустой список, если lsof нет или порт никто не слушает.
    """
    try:
        result = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
            capture_output = True,
            text = True,
            timeout = LSOF_TIMEOUT_SECONDS,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []

    return [int(line) for line in result.stdout.split() if line.isdigit()]


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
        return START_SERVICE_EMPTY_LOG_TAIL

    return "\n".join(lines[-LOG_TAIL_LINES:])

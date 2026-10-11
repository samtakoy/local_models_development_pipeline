"""Инструмент check_in_browser: агент просит помощника с браузером пройти сценарии в запущенном приложении."""

import itertools
import logging
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from langchain_core.tools import BaseTool, StructuredTool, ToolException
from pydantic import BaseModel, Field

from codeteam.core.roles.browser_checker.config import BROWSER_CHECKER_ROLE, OBSERVATIONS_FILE_NAME
from codeteam.common.shell import ShellProcesses
from codeteam.core.agent.workspace import helpers_dir
from codeteam.core.roles.browser_checker.prompts import (
    APP_NOT_OWN_ERROR,
    APP_NOT_RESPONDING_ERROR,
    BROWSER_CHECK_LIMIT_ERROR,
    BROWSER_CHECK_TASK,
    HELPER_FAILED_ERROR,
    CHECK_IN_BROWSER_DESCRIPTION,
    CHECK_IN_BROWSER_SCENARIOS_DESCRIPTION,
    CHECK_IN_BROWSER_URL_DESCRIPTION,
    NO_OBSERVATIONS_ERROR,
    NOT_LOCAL_URL_ERROR,
    OBSERVATIONS_TRUNCATED_NOTE,
)
from codeteam.core.roles.common import CallerContext, reserve_private_dir_name, run_role

logger = logging.getLogger(__name__)

# Имя инструмента вызова помощника с браузером.
CHECK_IN_BROWSER_TOOL_NAME = "check_in_browser"

# Наибольшее число вызовов помощника за одну работу агента: защита от зацикливания.
BROWSER_CHECK_CALL_LIMIT = 20

# Наибольшая длина ответа помощника, которая возвращается в историю агента, знаков.
OBSERVATIONS_LENGTH_LIMIT = 10000

# Имена этого компьютера, на которые можно направить помощника.
LOCAL_HOSTS = ("127.0.0.1", "localhost")

# Сколько ждать ответа приложения при проверке адреса перед запуском помощника, секунды.
URL_CHECK_TIMEOUT_SECONDS = 3

# Сколько ждать, пока приложение начнёт принимать соединения: оно могло только что запуститься, секунды.
APP_START_WAIT_SECONDS = 15

# Пауза между попытками соединиться с приложением, секунды.
APP_START_POLL_SECONDS = 1

# Порт адреса без явного порта по протоколу.
DEFAULT_PORTS = {"http": 80, "https": 443}


class CheckInBrowserArguments(BaseModel):
    """
    Аргументы check_in_browser.
    """

    url: str = Field(description = CHECK_IN_BROWSER_URL_DESCRIPTION)
    scenarios: str = Field(description = CHECK_IN_BROWSER_SCENARIOS_DESCRIPTION)


def build_check_in_browser_tool(caller_context: CallerContext) -> BaseTool | None:
    """
    Собирает инструмент check_in_browser для вызывающего агента.

    Каждый вызов запускает помощника в своей личной папке внутри папки помощников вызывающего агента:
    <папка вызывающего>.helpers/bro_check_r<номер>; журнал помощника — <журнал вызывающего>.bro_check_r<номер>.
    Помощник не читает проект и не запускает команды: у него только браузер и свой черновик.
    Вызовы выполняются по очереди: следующий помощник запускается, когда закончит предыдущий.

        caller_context: агент, который будет просить проверку в браузере.

    Возвращает: Инструмент check_in_browser; None, если проверка в браузере выключена в файле состава.
    """
    if not caller_context.cfg.browser_check:
        return None

    project_dir = Path(caller_context.cfg.project_path).resolve()
    # номера вызовов для предела BROWSER_CHECK_CALL_LIMIT: next() выдаёт номер атомарно
    call_numbers = itertools.count(1)
    # один помощник за раз: параллельные вызовы из одного ответа модели ждут друг друга
    helper_lock = threading.Lock()

    def check_in_browser(*, url: str, scenarios: str) -> str:
        """
        Проверяет, что приложение отвечает по адресу, запускает помощника и возвращает его наблюдения.

            url: адрес запущенного приложения.
            scenarios: сценарии проверки по шагам.

        Возвращает: Наблюдения помощника; длиннее OBSERVATIONS_LENGTH_LIMIT — начало ответа и путь к файлу.
            Ошибку для агента поднимает ToolException.
        """
        check_app_url(url = url, processes = caller_context.shell_processes)
        call_number = next(call_numbers)
        if call_number > BROWSER_CHECK_CALL_LIMIT:
            raise ToolException(BROWSER_CHECK_LIMIT_ERROR.format(limit = BROWSER_CHECK_CALL_LIMIT))

        with helper_lock:
            return _run_helper(caller_context = caller_context, project_dir = project_dir, url = url, scenarios = scenarios)

    return StructuredTool.from_function(
        func = check_in_browser,
        name = CHECK_IN_BROWSER_TOOL_NAME,
        description = CHECK_IN_BROWSER_DESCRIPTION,
        args_schema = CheckInBrowserArguments,
        handle_tool_error = True,
    )


def _run_helper(*, caller_context: CallerContext, project_dir: Path, url: str, scenarios: str) -> str:
    """
    Запускает помощника в новой личной папке внутри папки помощников вызывающего и читает его наблюдения.

        caller_context: агент, который просит проверку.
        project_dir: папка проекта.
        url: адрес запущенного приложения.
        scenarios: сценарии проверки по шагам.

    Возвращает: Наблюдения помощника; длиннее OBSERVATIONS_LENGTH_LIMIT — начало ответа и путь к файлу.
        Ошибку для агента поднимает ToolException.
    """
    private_dir_name = reserve_private_dir_name(
        project_dir = project_dir,
        parent = helpers_dir(private_dir = caller_context.caller_private_dir_name),
        role_name = BROWSER_CHECKER_ROLE.name,
        preserve_draft = False,
        preserve_context = False,
    )
    try:
        observations_dir = run_role(
            cfg = caller_context.cfg,
            role = BROWSER_CHECKER_ROLE,
            journal_name = f"{caller_context.caller_journal_name}.{private_dir_name.name}",
            task = BROWSER_CHECK_TASK.format(caller_name = caller_context.caller_name, url = url, scenarios = scenarios),
            input_dirs = (),
            private_dir_name = private_dir_name,
            extra_readable_dirs = (),
            extra_writable_dirs = (),
            extra_command_writable_dirs = (),
        )
    except Exception as error:
        # падение помощника не прерывает спросившего: он получает ошибку и продолжает работу
        logger.error(f"[{CHECK_IN_BROWSER_TOOL_NAME}] помощник прервал работу: {type(error).__name__}: {error}")
        raise ToolException(HELPER_FAILED_ERROR.format(error = type(error).__name__)) from error
    observations_path = observations_dir / OBSERVATIONS_FILE_NAME
    if not observations_path.is_file():
        raise ToolException(NO_OBSERVATIONS_ERROR.format(draft_dir = observations_dir.relative_to(project_dir)))

    observations = observations_path.read_text(encoding = "utf-8", errors = "replace")
    if len(observations) <= OBSERVATIONS_LENGTH_LIMIT:
        return observations

    return (
        observations[:OBSERVATIONS_LENGTH_LIMIT]
        + "\n\n"
        + OBSERVATIONS_TRUNCATED_NOTE.format(
            length = len(observations),
            observations_file = observations_path.relative_to(project_dir),
        )
    )


def check_app_url(*, url: str, processes: ShellProcesses) -> None:
    """
    Проверяет адрес приложения: он на этом компьютере, приложение по нему отвечает и порт адреса слушает
    процесс агента. Любой ответ, в том числе с кодом ошибки, значит, что приложение работает. Пока
    соединиться нельзя, ждёт до APP_START_WAIT_SECONDS: приложение могло только что запуститься.
    Ошибку для агента поднимает ToolException.

        url: адрес приложения от агента.
        processes: учёт фоновых процессов агента.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or parsed.hostname not in LOCAL_HOSTS:
        raise ToolException(NOT_LOCAL_URL_ERROR.format(url = url))

    # без прокси из окружения: адрес локальный
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    deadline = time.monotonic() + APP_START_WAIT_SECONDS
    while True:
        try:
            with opener.open(url, timeout = URL_CHECK_TIMEOUT_SECONDS):
                break
        except urllib.error.HTTPError:
            break
        except ValueError as error:
            raise ToolException(APP_NOT_RESPONDING_ERROR.format(url = url)) from error
        except (urllib.error.URLError, OSError) as error:
            if time.monotonic() >= deadline:
                raise ToolException(APP_NOT_RESPONDING_ERROR.format(url = url)) from error
            time.sleep(APP_START_POLL_SECONDS)

    port = parsed.port or DEFAULT_PORTS[parsed.scheme]
    if not processes.port_listeners(port = port):
        raise ToolException(APP_NOT_OWN_ERROR.format(url = url, port = port))

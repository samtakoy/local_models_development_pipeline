"""Инструмент check_in_browser: агент просит помощника с браузером пройти сценарии в запущенном приложении."""

import itertools
import threading
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from langchain_core.tools import BaseTool, StructuredTool, ToolException
from pydantic import BaseModel, Field

from codeteam.core.roles.browser_checker.config import BROWSER_CHECKER_ROLE, OBSERVATIONS_FILE_NAME
from codeteam.core.roles.browser_checker.prompts import (
    APP_NOT_RESPONDING_ERROR,
    BROWSER_CHECK_LIMIT_ERROR,
    BROWSER_CHECK_TASK,
    CHECK_IN_BROWSER_DESCRIPTION,
    CHECK_IN_BROWSER_SCENARIOS_DESCRIPTION,
    CHECK_IN_BROWSER_URL_DESCRIPTION,
    NO_OBSERVATIONS_ERROR,
    NOT_LOCAL_URL_ERROR,
    OBSERVATIONS_TRUNCATED_NOTE,
)
from codeteam.core.roles.common import CallerContext, reserve_private_dir_name, run_role

# Имя инструмента вызова помощника с браузером.
CHECK_IN_BROWSER_TOOL_NAME = "check_in_browser"

# Наибольшее число вызовов помощника за одну работу агента: защита от зацикливания.
BROWSER_CHECK_CALL_LIMIT = 5

# Наибольшая длина ответа помощника, которая возвращается в историю агента, знаков.
OBSERVATIONS_LENGTH_LIMIT = 10000

# Имена этого компьютера, на которые можно направить помощника.
LOCAL_HOSTS = ("127.0.0.1", "localhost")

# Сколько ждать ответа приложения при проверке адреса перед запуском помощника, секунды.
URL_CHECK_TIMEOUT_SECONDS = 3


class CheckInBrowserArguments(BaseModel):
    """
    Аргументы check_in_browser.
    """

    url: str = Field(description = CHECK_IN_BROWSER_URL_DESCRIPTION)
    scenarios: str = Field(description = CHECK_IN_BROWSER_SCENARIOS_DESCRIPTION)


def build_check_in_browser_tool(caller_context: CallerContext) -> BaseTool:
    """
    Собирает инструмент check_in_browser для вызывающего агента.

    Каждый вызов запускает помощника в своей личной папке внутри личной папки вызывающего агента:
    <папка вызывающего>/browser_checker_r<номер>; журнал помощника — <журнал вызывающего>.browser_checker_r<номер>.
    Помощник не читает проект и не запускает команды: у него только браузер и свой черновик.
    Вызовы выполняются по очереди: следующий помощник запускается, когда закончит предыдущий.

        caller_context: агент, который будет просить проверку в браузере.

    Возвращает: Инструмент check_in_browser.
    """
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
        check_app_url(url = url)
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
    Запускает помощника в новой личной папке и читает его наблюдения.

        caller_context: агент, который просит проверку.
        project_dir: папка проекта.
        url: адрес запущенного приложения.
        scenarios: сценарии проверки по шагам.

    Возвращает: Наблюдения помощника; длиннее OBSERVATIONS_LENGTH_LIMIT — начало ответа и путь к файлу.
        Ошибку для агента поднимает ToolException.
    """
    private_dir_name = reserve_private_dir_name(
        project_dir = project_dir,
        parent = caller_context.caller_private_dir_name,
        role_name = BROWSER_CHECKER_ROLE.name,
        preserve_draft = False,
        preserve_context = False,
    )
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


def check_app_url(*, url: str) -> None:
    """
    Проверяет адрес приложения: он на этом компьютере и приложение по нему отвечает.
    Любой ответ, в том числе с кодом ошибки, значит, что приложение работает. Ошибку для агента поднимает ToolException.

        url: адрес приложения от агента.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or parsed.hostname not in LOCAL_HOSTS:
        raise ToolException(NOT_LOCAL_URL_ERROR.format(url = url))

    # без прокси из окружения: адрес локальный
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url, timeout = URL_CHECK_TIMEOUT_SECONDS):
            return
    except urllib.error.HTTPError:
        return
    except (urllib.error.URLError, OSError, ValueError) as error:
        raise ToolException(APP_NOT_RESPONDING_ERROR.format(url = url)) from error

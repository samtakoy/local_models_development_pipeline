"""Сервер браузера Playwright MCP для ролей, которые проверяют приложение в браузере."""

import logging
import subprocess
from functools import partial
from pathlib import Path

from langchain_core.messages import ToolMessage

from codeteam.core.agent.workspace import CHECK_DIR
from codeteam.core.roles.common.errors import PipelineError
from codeteam.core.roles.common.external_tools import CallerContext
from codeteam.core.roles.common.npx import NPX_COMMAND, npx_args
from codeteam.core.roles.common.prompts import PLAYWRIGHT_FILENAME_ERROR
from codeteam.core.tools.mcp import McpServer, McpTools

# Пакет Playwright MCP с закреплённой версией.
PLAYWRIGHT_MCP_PACKAGE = "@playwright/mcp@0.0.83"

# Аргументы запуска Playwright MCP: браузер с профилем только в памяти.
PLAYWRIGHT_ARGS = (PLAYWRIGHT_MCP_PACKAGE, "--isolated")

# Предел ожидания скачивания Playwright MCP при прогреве, секунды.
PLAYWRIGHT_DOWNLOAD_TIMEOUT_SECONDS = 600

# Инструменты Playwright MCP, которые агент не получает: код Playwright на стороне сервера
# и скрипты на странице.
PLAYWRIGHT_EXCLUDED_TOOL_NAMES = ("browser_run_code_unsafe", "browser_evaluate")

# Инструмент Playwright MCP, которым прогрев открывает браузер, и адрес пустой страницы.
PLAYWRIGHT_NAVIGATE_TOOL_NAME = "browser_navigate"
BLANK_PAGE_URL = "about:blank"

# Строка ответа browser_navigate, когда браузер открыл пустую страницу.
BLANK_PAGE_OPENED = f"Page URL: {BLANK_PAGE_URL}"

logger = logging.getLogger(__name__)


def playwright_server(caller_context: CallerContext) -> McpServer:
    """
    Собирает сервер Playwright MCP для запуска агента.

        caller_context: агент, которому нужен браузер.

    Возвращает: Сервер MCP из своего кэша npm: работает в папке проекта, файлы с именем из вызова агента пишет
        только в папку CHECK_DIR проекта; снимки страниц и журналы консоли без имени — в папке
        <журнал агента>.playwright рядом с журналом; без окна, если так задано в настройках.
    """
    project_dir = Path(caller_context.cfg.project_path)
    output_dir = caller_context.cfg.run_dir / f"{caller_context.caller_journal_name}.playwright"
    args = npx_args(
        npm_cache_dir = caller_context.cfg.settings.npm_cache_dir,
        package_args = (*PLAYWRIGHT_ARGS, "--output-dir", str(output_dir)),
    )
    if caller_context.cfg.settings.browser_headless:
        args = (*args, "--headless")

    return McpServer(
        name = "playwright",
        command = NPX_COMMAND,
        args = args,
        cwd = project_dir,
        env = {},
        check_call = partial(check_playwright_filename, project_dir = project_dir),
        excluded_tool_names = PLAYWRIGHT_EXCLUDED_TOOL_NAMES,
    )


def warm_up_browser(*, work_dir: Path, npm_cache_dir: Path) -> None:
    """
    Скачивает Playwright MCP в свой кэш npm, запускает сервер и открывает в браузере пустую страницу.
    Ошибку поднимает PipelineError.

        work_dir: рабочая папка сервера и папка его файлов; создаётся, если её нет.
        npm_cache_dir: свой кэш npm.
    """
    logger.info(f"[браузер] прогрев {PLAYWRIGHT_MCP_PACKAGE}: скачивание и запуск браузера")
    download_command = [
        NPX_COMMAND,
        *npx_args(npm_cache_dir = npm_cache_dir, package_args = ("--yes", PLAYWRIGHT_MCP_PACKAGE, "--version")),
    ]
    try:
        result = subprocess.run(
            download_command,
            capture_output = True,
            text = True,
            timeout = PLAYWRIGHT_DOWNLOAD_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as error:
        raise PipelineError(f"нет программы {NPX_COMMAND}: для проверки в браузере нужен Node.js") from error
    except subprocess.TimeoutExpired as error:
        raise PipelineError(
            f"Playwright MCP не скачался за {PLAYWRIGHT_DOWNLOAD_TIMEOUT_SECONDS} с: {' '.join(download_command)}"
        ) from error

    if result.returncode != 0:
        raise PipelineError(
            f"Playwright MCP не скачался, код {result.returncode}: {' '.join(download_command)}\n"
            f"{result.stdout}{result.stderr}"
        )

    work_dir.mkdir(parents = True, exist_ok = True)
    server = McpServer(
        name = "playwright",
        command = NPX_COMMAND,
        args = npx_args(
            npm_cache_dir = npm_cache_dir,
            package_args = (*PLAYWRIGHT_ARGS, "--output-dir", str(work_dir), "--headless"),
        ),
        cwd = work_dir,
        env = {},
        check_call = None,
        excluded_tool_names = PLAYWRIGHT_EXCLUDED_TOOL_NAMES,
    )
    try:
        with McpTools(servers = (server,)) as tools:
            navigate = next((tool for tool in tools if tool.name == PLAYWRIGHT_NAVIGATE_TOOL_NAME), None)
            if navigate is None:
                failure = f"у Playwright MCP нет инструмента {PLAYWRIGHT_NAVIGATE_TOOL_NAME}"
            else:
                answer: ToolMessage = navigate.invoke({
                    "type": "tool_call",
                    "id": "warm_up",
                    "name": PLAYWRIGHT_NAVIGATE_TOOL_NAME,
                    "args": {"url": BLANK_PAGE_URL},
                })
                opened = answer.status != "error" and BLANK_PAGE_OPENED in answer.text
                failure = None if opened else answer.text
    except (RuntimeError, TimeoutError) as error:
        failure = str(error)

    if failure is not None:
        raise PipelineError(f"браузер не открылся через Playwright MCP: {failure}")

    logger.info("[браузер] готов")


def check_playwright_filename(tool_name: str, arguments: dict, *, project_dir: Path) -> str | None:
    """
    Пропускает вызов, только если файл из filename лежит в папке CHECK_DIR проекта.

        tool_name: имя инструмента браузера.
        arguments: аргументы вызова.
        project_dir: папка проекта: рабочая папка сервера.

    Возвращает: Текст отказа агенту; None, если filename не задан или лежит в CHECK_DIR.
    """
    filename = arguments.get("filename")
    if filename is None:
        return None

    files_dir = (project_dir / CHECK_DIR).resolve()
    if (project_dir / filename).resolve().is_relative_to(files_dir):
        return None

    return PLAYWRIGHT_FILENAME_ERROR.format(filename = filename, check_dir = CHECK_DIR, file_name = Path(filename).name)

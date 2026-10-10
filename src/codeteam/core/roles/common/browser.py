"""Сервер браузера Playwright MCP для ролей, которые проверяют приложение в браузере."""

from functools import partial
from pathlib import Path

from codeteam.core.agent.workspace import CHECK_DIR
from codeteam.core.roles.common.external_tools import CallerContext
from codeteam.core.roles.common.prompts import PLAYWRIGHT_FILENAME_ERROR
from codeteam.core.tools.mcp import McpServer

# Команда запуска Playwright MCP: браузер с профилем только в памяти.
PLAYWRIGHT_COMMAND = "npx"
PLAYWRIGHT_ARGS = ("@playwright/mcp@latest", "--isolated")


def playwright_server(caller_context: CallerContext) -> McpServer:
    """
    Собирает сервер Playwright MCP для запуска агента.

        caller_context: агент, которому нужен браузер.

    Возвращает: Сервер MCP: работает в папке проекта, файлы с именем из вызова агента пишет только
        в папку CHECK_DIR проекта; снимки страниц и журналы консоли без имени — в папке
        <журнал агента>.playwright рядом с журналом; без окна, если так задано в настройках.
    """
    project_dir = Path(caller_context.cfg.project_path)
    output_dir = caller_context.cfg.run_dir / f"{caller_context.caller_journal_name}.playwright"
    args = (*PLAYWRIGHT_ARGS, "--output-dir", str(output_dir))
    if caller_context.cfg.settings.browser_headless:
        args = (*args, "--headless")

    return McpServer(
        name = "playwright",
        command = PLAYWRIGHT_COMMAND,
        args = args,
        cwd = project_dir,
        check_call = partial(check_playwright_filename, project_dir = project_dir),
    )


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

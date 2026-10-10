"""Описание роли веб-тестировщика: промпт, модель, инструменты, сервер браузера, проверки сдачи."""

from functools import partial
from pathlib import Path

from codeteam.common.llm import ReasoningLevel
from codeteam.core.agent.workspace import CHECK_DIR
from codeteam.core.roles.common import ACCEPTED_VERDICT, REWORK_VERDICT, VERDICT_FILE_NAME, CallerContext, \
    RoleSettings, check_verdict_file
from codeteam.core.tools.files import DELETE_TOOL_NAME, EDIT_TOOL_NAME, GLOB_TOOL_NAME, GREP_TOOL_NAME, \
    READ_TOOL_NAME, WRITE_TOOL_NAME
from codeteam.core.tools.mcp import McpServer
from codeteam.core.tools.shell import START_SERVICE_TOOL_NAME, STOP_PROCESS_TOOL_NAME

# Инструменты веб-тестировщика: без bash — приложение он запускает только через start_service.
WEB_TESTER_TOOL_NAMES = (
    READ_TOOL_NAME,
    GLOB_TOOL_NAME,
    GREP_TOOL_NAME,
    WRITE_TOOL_NAME,
    EDIT_TOOL_NAME,
    DELETE_TOOL_NAME,
    START_SERVICE_TOOL_NAME,
    STOP_PROCESS_TOOL_NAME,
)

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

    return (
        f"Ошибка: filename {filename} вне папки {CHECK_DIR}/ проекта. "
        f"Сохраняй файлы в {CHECK_DIR}/, например {CHECK_DIR}/{Path(filename).name}."
    )


WEB_TESTER_ROLE = RoleSettings(
    name = "web_tester",
    system_prompt_path = Path(__file__).parent / "system_prompt.md",
    prompt_fields = {
        "verdict_file": VERDICT_FILE_NAME,
        "accepted_verdict": ACCEPTED_VERDICT,
        "rework_verdict": REWORK_VERDICT,
        "check_dir": CHECK_DIR.as_posix(),
    },
    model_name = None,
    reasoning_level = ReasoningLevel.LOW,
    tool_names = WEB_TESTER_TOOL_NAMES,
    step_hooks = (),
    step_checks = (),
    answer_checks = (check_verdict_file,),
    helper_tools = (),
    mcp_servers = (playwright_server,),
)

"""Описание роли тестировщика: промпт, модель, инструменты, сервер браузера, проверки сдачи."""

from pathlib import Path

from codeteam.common.llm import ReasoningLevel
from codeteam.core.agent.workspace import CHECK_DIR
from codeteam.core.roles.common import ACCEPTED_VERDICT, PROJECT_TOOL_NAMES, REWORK_VERDICT, VERDICT_FILE_NAME, \
    CallerContext, RoleSettings, check_verdict_file
from codeteam.core.tools.mcp import McpServer

# Команда запуска Playwright MCP: браузер с профилем только в памяти.
PLAYWRIGHT_COMMAND = "npx"
PLAYWRIGHT_ARGS = ("@playwright/mcp@latest", "--isolated")


def playwright_server(caller_context: CallerContext) -> McpServer:
    """
    Собирает сервер Playwright MCP для запуска агента.

        caller_context: агент, которому нужен браузер.

    Возвращает: Сервер MCP: снимки страниц и журналы консоли — в папке <журнал агента>.playwright
        рядом с журналом; без окна, если так задано в настройках.
    """
    output_dir = caller_context.cfg.run_dir / f"{caller_context.caller_journal_name}.playwright"
    args = (*PLAYWRIGHT_ARGS, "--output-dir", str(output_dir))
    if caller_context.cfg.settings.browser_headless:
        args = (*args, "--headless")

    return McpServer(name = "playwright", command = PLAYWRIGHT_COMMAND, args = args)


TESTER_ROLE = RoleSettings(
    name = "tester",
    system_prompt_path = Path(__file__).parent / "system_prompt.md",
    prompt_fields = {
        "verdict_file": VERDICT_FILE_NAME,
        "accepted_verdict": ACCEPTED_VERDICT,
        "rework_verdict": REWORK_VERDICT,
        "check_dir": CHECK_DIR.as_posix(),
    },
    model_name = None,
    reasoning_level = ReasoningLevel.LOW,
    tool_names = PROJECT_TOOL_NAMES,
    step_hooks = (),
    step_checks = (),
    answer_checks = (check_verdict_file,),
    helper_tools = (),
    mcp_servers = (playwright_server,),
)

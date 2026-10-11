"""Описание роли тестировщика: промпт, модель, инструменты, помощник с браузером, проверки сдачи."""

from pathlib import Path

from codeteam.common.llm import ReasoningLevel
from codeteam.core.agent.workspace import CHECK_DIR, CONTEXT_FILE_NAME
from codeteam.core.roles.browser_checker import CHECK_IN_BROWSER_TOOL_NAME, build_check_in_browser_tool
from codeteam.core.roles.common import ACCEPTED_VERDICT, PROJECT_TOOL_NAMES, REWORK_VERDICT, VERDICT_FILE_NAME, \
    VERDICT_LINE_HOOK, RoleSettings, check_verdict_file
from codeteam.core.roles.common.final_check import REPORT_FILE_NAME
from codeteam.core.tools.shell import BASH_TOOL_NAME, START_SERVICE_TOOL_NAME, STOP_PROCESS_TOOL_NAME

TESTER_ROLE = RoleSettings(
    name = "tester",
    system_prompt_path = Path(__file__).parent / "system_prompt.md",
    prompt_fields = {
        "verdict_file": VERDICT_FILE_NAME,
        "accepted_verdict": ACCEPTED_VERDICT,
        "rework_verdict": REWORK_VERDICT,
        "check_dir": CHECK_DIR.as_posix(),
        "context_file": CONTEXT_FILE_NAME,
        "report_file": REPORT_FILE_NAME,
        "bash_tool": BASH_TOOL_NAME,
        "start_service_tool": START_SERVICE_TOOL_NAME,
        "stop_process_tool": STOP_PROCESS_TOOL_NAME,
        "check_in_browser_tool": CHECK_IN_BROWSER_TOOL_NAME,
    },
    model_name = None,
    reasoning_level = ReasoningLevel.LOW,
    tool_names = PROJECT_TOOL_NAMES,
    step_hooks = (VERDICT_LINE_HOOK,),
    step_checks = (),
    answer_checks = (check_verdict_file,),
    answer_file_names = (VERDICT_FILE_NAME, REPORT_FILE_NAME),
    only_answer_files = False,
    work_refusal_hints = (),
    helper_tools = (build_check_in_browser_tool,),
    mcp_servers = (),
)
